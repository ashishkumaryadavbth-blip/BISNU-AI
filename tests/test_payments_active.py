from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import ANY, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from bisnu_x import db, payments
from bisnu_x.app import app
from bisnu_x.brain import brain_answer
from bisnu_x.config import settings
from bisnu_x.inference import ModelManager
from bisnu_x.security import create_token


class RazorpayWebhookTests(TestCase):
    def setUp(self):
        self.secret_patch = patch.object(
            settings,
            "razorpay_webhook_secret",
            "test-webhook-secret-that-is-long-enough",
        )
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)


    def _signed(self, payload: dict) -> tuple[bytes, str]:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(
            settings.razorpay_webhook_secret.encode(),
            raw,
            hashlib.sha256,
        ).hexdigest()
        return raw, signature

    def _payload(
        self,
        *,
        event: str = "subscription.activated",
        status: str = "active",
        current_end: int | None = None,
    ) -> dict:
        return {
            "event": event,
            "payload": {
                "subscription": {
                    "entity": {
                        "id": "sub_server_created",
                        "plan_id": "plan_server_created",
                        "status": status,
                        "current_end": current_end
                        if current_end is not None
                        else int(time.time()) + 3600,
                    }
                },
                "payment": {
                    "entity": {
                        "id": "pay_captured",
                        "status": "captured",
                        "amount": 49900,
                        "currency": "INR",
                    }
                },
            },
        }

    def test_invalid_signature_is_rejected(self):
        payload = self._payload()
        raw, _ = self._signed(payload)
        with self.assertRaises(HTTPException) as raised:
            payments.process_razorpay_webhook(
                payload,
                raw,
                "invalid",
                "event-1",
            )
        self.assertEqual(raised.exception.status_code, 401)

    def test_activation_requires_a_server_created_matching_subscription(self):
        payload = self._payload()
        raw, signature = self._signed(payload)
        with (
            patch.object(db, "webhook_event_exists", return_value=False),
            patch.object(
                db,
                "get_subscription",
                return_value={
                    "user_id": "user-1",
                    "provider_plan_id": "plan_server_created",
                    "plan": "PREMIUM",
                    "expected_amount": 49900,
                    "currency": "INR",
                },
            ),
            patch.object(
                db,
                "apply_subscription_webhook",
                return_value={"duplicate": False, "status": "authorized"},
            ) as apply_event,
        ):
            result = payments.process_razorpay_webhook(
                payload,
                raw,
                signature,
                "event-1",
            )
        self.assertEqual(result["status"], "authorized")
        self.assertEqual(apply_event.call_args.args[0:4][0], "event-1")

    def test_plan_mismatch_is_rejected(self):
        payload = self._payload()
        payload["payload"]["subscription"]["entity"]["plan_id"] = "other_plan"
        raw, signature = self._signed(payload)
        with (
            patch.object(db, "webhook_event_exists", return_value=False),
            patch.object(
                db,
                "get_subscription",
                return_value={
                    "user_id": "user-1",
                    "provider_plan_id": "plan_server_created",
                    "plan": "PREMIUM",
                    "expected_amount": 49900,
                    "currency": "INR",
                },
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                payments.process_razorpay_webhook(
                    payload,
                    raw,
                    signature,
                    "event-2",
                )
        self.assertEqual(raised.exception.status_code, 400)

    def test_non_monthly_provider_plan_cannot_be_sold_as_monthly(self):
        with (
            patch.dict(payments.PLAN_IDS, {"PREMIUM": "plan_test"}),
            patch.object(
                payments,
                "get_user",
                return_value={"id": "user-1"},
            ),
            patch.object(
                payments,
                "_provider_request",
                return_value={
                    "id": "plan_test",
                    "period": "yearly",
                    "interval": 1,
                    "item": {"amount": 49900, "currency": "INR"},
                },
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                payments.create_subscription("user-1", "PREMIUM")
        self.assertEqual(raised.exception.status_code, 503)

    def test_payment_availability_requires_complete_gateway_and_plan_secrets(self):
        with (
            patch.object(settings, "razorpay_key_id", "key"),
            patch.object(settings, "razorpay_key_secret", "secret"),
            patch.object(settings, "razorpay_webhook_secret", "webhook"),
            patch.object(settings, "razorpay_premium_plan_id", "premium"),
            patch.object(settings, "razorpay_ultra_plan_id", ""),
        ):
            self.assertFalse(payments.payments_available())

        with (
            patch.object(settings, "razorpay_key_id", "key"),
            patch.object(settings, "razorpay_key_secret", "secret"),
            patch.object(settings, "razorpay_webhook_secret", "webhook"),
            patch.object(settings, "razorpay_premium_plan_id", "premium"),
            patch.object(settings, "razorpay_ultra_plan_id", "ultra"),
        ):
            self.assertTrue(payments.payments_available())

    def test_monthly_inr_plan_can_create_a_checkout_without_granting_access(self):
        with (
            patch.dict(payments.PLAN_IDS, {"PREMIUM": "plan_test"}),
            patch.object(
                payments,
                "get_user",
                return_value={"id": "user-1"},
            ),
            patch.object(
                payments,
                "_provider_request",
                side_effect=[
                    {
                        "id": "plan_test",
                        "period": "monthly",
                        "interval": 1,
                        "item": {"amount": 49900, "currency": "INR"},
                    },
                    {
                        "id": "sub_test",
                        "short_url": "https://rzp.io/i/test",
                        "status": "created",
                    },
                ],
            ),
            patch.object(db, "create_subscription") as save_subscription,
        ):
            result = payments.create_subscription("user-1", "PREMIUM")
        self.assertEqual(result["status"], "created")
        save_subscription.assert_called_once_with(
            "user-1",
            "sub_test",
            "plan_test",
            "PREMIUM",
            "created",
            49900,
            "INR",
        )

    def test_charge_without_paid_through_date_is_rejected(self):
        payload = self._payload(
        event="subscription.charged",
        current_end=0,
        )
        raw, signature = self._signed(payload)
        with (
            patch.object(db, "webhook_event_exists", return_value=False),
            patch.object(
                db,
                "get_subscription",
                return_value={
                    "user_id": "user-1",
                    "provider_plan_id": "plan_server_created",
                    "plan": "PREMIUM",
                    "expected_amount": 49900,
                    "currency": "INR",
                },
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                payments.process_razorpay_webhook(
                    payload,
                    raw,
                    signature,
                    "event-3",
                )
        self.assertEqual(raised.exception.status_code, 400)

    def test_webhook_updates_plan_atomically_and_bounds_entitlement(self):
        with tempfile.TemporaryDirectory() as directory:
            database_patch = patch.object(
                db,
                "DB_PATH",
                Path(directory) / "test.sqlite3",
            )
            database_patch.start()
            self.addCleanup(database_patch.stop)
            db.init_db()
            user = db.create_user("member@example.test", "Member")
            db.create_subscription(
                user["id"],
                "sub_server_created",
                "plan_server_created",
                "PREMIUM",
                "created",
                49900,
                "INR",
            )

            expiry = time.time() + 3600
            authorized = db.apply_subscription_webhook(
                "event-authorized",
                "sub_server_created",
                "authorized",
                expiry,
            )
            self.assertEqual(authorized["plan"], "FREE")
            self.assertEqual(db.get_user(user["id"])["plan"], "FREE")

            applied = db.apply_subscription_webhook(
                "event-active",
                "sub_server_created",
                "active",
                expiry,
                ("pay_captured", "PREMIUM", 49900, "INR"),
            )
            self.assertEqual(applied["plan"], "PREMIUM")
            self.assertEqual(db.get_user(user["id"])["plan"], "PREMIUM")

            cancelled = db.apply_subscription_webhook(
                "event-cancelled",
                "sub_server_created",
                "cancelled",
                None,
            )
            self.assertEqual(cancelled["plan"], "PREMIUM")

            duplicate = db.apply_subscription_webhook(
                "event-active",
                "sub_server_created",
                "active",
                expiry,
            )
            self.assertTrue(duplicate["duplicate"])

            db.apply_subscription_webhook(
                "event-paused",
                "sub_server_created",
                "paused",
                expiry,
            )
            self.assertEqual(db.get_user(user["id"])["plan"], "FREE")

    def test_webhook_charge_requires_matching_captured_payment(self):
        payload = self._payload(event="subscription.charged")
        raw, signature = self._signed(payload)
        with (
            patch.object(db, "webhook_event_exists", return_value=False),
            patch.object(
                db,
                "get_subscription",
                return_value={
                    "user_id": "user-1",
                    "provider_plan_id": "plan_server_created",
                    "plan": "PREMIUM",
                    "expected_amount": 49900,
                    "currency": "INR",
                },
            ),
            patch.object(
                db,
                "apply_subscription_webhook",
                return_value={"duplicate": False, "status": "active"},
            ) as apply_event,
        ):
            result = payments.process_razorpay_webhook(
                payload,
                raw,
                signature,
                "event-charged",
            )

        self.assertEqual(result["status"], "active")
        self.assertEqual(
            apply_event.call_args.args[4],
            ("pay_captured", "PREMIUM", 49900, "INR"),
        )

    def test_webhook_rejects_a_charge_with_the_wrong_amount(self):
        payload = self._payload(event="subscription.charged")
        payload["payload"]["payment"]["entity"]["amount"] = 50000
        raw, signature = self._signed(payload)
        with (
            patch.object(db, "webhook_event_exists", return_value=False),
            patch.object(
                db,
                "get_subscription",
                return_value={
                    "user_id": "user-1",
                    "provider_plan_id": "plan_server_created",
                    "plan": "PREMIUM",
                    "expected_amount": 49900,
                    "currency": "INR",
                },
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                payments.process_razorpay_webhook(
                    payload,
                    raw,
                    signature,
                    "event-wrong-amount",
                )
        self.assertEqual(raised.exception.status_code, 400)

    def test_scanner_access_is_locked_until_premium_is_paid(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"),
                patch.object(settings, "jwt_secret", "j" * 32),
                patch.object(payments.settings, "razorpay_key_id", ""),
            ):
                db.init_db()
                with TestClient(app) as client:
                    user = db.create_user("scanner@example.test", "Scanner")
                    token = create_token(user["id"])
                    headers = {"Authorization": f"Bearer {token}"}

                    allowed = client.get(
                        "/v1/scanner/access",
                        headers=headers,
                    )
                    self.assertEqual(allowed.status_code, 200)
                    self.assertFalse(allowed.json()["allowed"])
                    self.assertFalse(allowed.json()["premium_available"])
                    self.assertIn("coming soon", allowed.json()["detail"].lower())

    def test_subscription_status_reports_payments_coming_soon_without_config(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"),
                patch.object(settings, "jwt_secret", "j" * 32),
                patch.object(payments.settings, "razorpay_key_id", ""),
            ):
                db.init_db()
                with TestClient(app) as client:
                    user = db.create_user("plans@example.test", "Plans")
                    headers = {
                        "Authorization": f"Bearer {create_token(user['id'])}",
                    }
                    response = client.get(
                        "/v1/me/subscription",
                        headers=headers,
                    )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])

    def test_subscription_creation_returns_coming_soon_without_payment_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"),
                patch.object(settings, "jwt_secret", "j" * 32),
                patch.object(payments.settings, "razorpay_key_id", ""),
            ):
                db.init_db()
                with TestClient(app) as client:
                    user = db.create_user("subscribe@example.test", "Subscribe")
                    response = client.post(
                        "/v1/subscriptions",
                        headers={
                            "Authorization": f"Bearer {create_token(user['id'])}",
                        },
                        json={"plan": "PREMIUM"},
                    )

        self.assertEqual(response.status_code, 503)
        self.assertIn("coming soon", response.json()["detail"].lower())

    def test_scanner_upload_is_forbidden_without_paid_premium(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"),
                patch.object(settings, "jwt_secret", "j" * 32),
                patch("bisnu_x.app.save_image") as save_image,
            ):
                db.init_db()
                with TestClient(app) as client:
                    user = db.create_user("scan-upload@example.test", "Scanner")
                    response = client.post(
                        "/v1/scanner",
                        headers={
                            "Authorization": f"Bearer {create_token(user['id'])}",
                        },
                        files={"file": ("scan.png", b"image", "image/png")},
                    )

        self.assertEqual(response.status_code, 403)
        save_image.assert_not_called()

    def test_razorpay_webhook_route_passes_raw_body_and_headers(self):
        raw_body = b'{"event":"subscription.activated"}'
        with patch(
            "bisnu_x.app.payments.process_razorpay_webhook",
            return_value={"ok": True},
        ) as process:
            with TestClient(app) as client:
                response = client.post(
                    "/v1/payment/webhook",
                    content=raw_body,
                    headers={
                        "content-type": "application/json",
                        "x-razorpay-signature": "signed",
                        "x-razorpay-event-id": "event-1",
                    },
                )

        self.assertEqual(response.status_code, 200)
        process.assert_called_once_with(
            {"event": "subscription.activated"},
            raw_body,
            "signed",
            "event-1",
        )

    def test_chat_uses_the_active_authenticated_api_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"),
                patch.object(settings, "jwt_secret", "j" * 32),
                patch.object(settings, "live_search_enabled", False),
                patch.object(settings, "max_new_tokens", 128),
                patch(
                    "bisnu_x.app.brain",
                    return_value={
                        "answer": "Test response",
                        "model": "qwen",
                        "models_used": ["qwen"],
                        "verified": True,
                    },
                ) as brain,
            ):
                with TestClient(app) as client:
                    db.init_db()
                    user = db.create_user("chat@example.test", "Chat")
                    token = create_token(user["id"])
                    response = client.post(
                        "/v1/chat",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "message": "Hello",
                            "model": "qwen",
                            "use_search": False,
                            "memory_enabled": False,
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["answer"], "Test response")
                    self.assertTrue(body["conversation_id"])
                    self.assertEqual(
                        brain.call_args.kwargs["user_message"],
                        "Hello",
                    )
                    self.assertEqual(
                        brain.call_args.kwargs["max_new_tokens"],
                        128,
                    )

    def test_android_profile_memory_and_conversation_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"),
                patch.object(settings, "jwt_secret", "j" * 32),
            ):
                db.init_db()
                with TestClient(app) as client:
                    user = db.create_user(
                        "mobile@example.test",
                        "Mobile User",
                    )
                    headers = {
                        "Authorization": f"Bearer {create_token(user['id'])}",
                    }

                    profile = client.patch(
                        "/v1/auth/profile",
                        headers=headers,
                        json={"name": "Android User", "username": "android_user"},
                    )
                    self.assertEqual(profile.status_code, 200)
                    self.assertEqual(
                        profile.json()["profile"]["username"],
                        "android_user#bisnu-x.com",
                    )

                    rejected_memory = client.post(
                        "/v1/memory",
                        headers=headers,
                        json={"text": "Prefers Hindi answers", "approved": False},
                    )
                    self.assertEqual(rejected_memory.status_code, 400)

                    added_memory = client.post(
                        "/v1/memory",
                        headers=headers,
                        json={"text": "Prefers Hindi answers", "approved": True},
                    )
                    self.assertEqual(added_memory.status_code, 200)
                    memory_id = added_memory.json()["id"]

                    memories = client.get(
                        "/v1/memory",
                        headers=headers,
                        params={"query": "Hindi"},
                    )
                    self.assertEqual(memories.status_code, 200)
                    self.assertEqual(len(memories.json()["items"]), 1)

                    created = client.post(
                        "/v1/conversations",
                        headers=headers,
                        json={"title": "Android chat"},
                    )
                    self.assertEqual(created.status_code, 200)
                    conversation_id = created.json()["conversation_id"]

                    conversations = client.get(
                        "/v1/conversations",
                        headers=headers,
                    )
                    self.assertEqual(conversations.status_code, 200)
                    self.assertEqual(
                        conversations.json()["conversations"][0]["id"],
                        conversation_id,
                    )

                    detail = client.get(
                        f"/v1/conversations/{conversation_id}",
                        headers=headers,
                    )
                    self.assertEqual(detail.status_code, 200)
                    self.assertEqual(detail.json()["messages"], [])

                    deleted_memory = client.delete(
                        f"/v1/memory/{memory_id}",
                        headers=headers,
                    )
                    self.assertEqual(deleted_memory.status_code, 200)

    def test_generation_limit_reaches_direct_and_ensemble_models(self):
        with (
            patch.object(settings, "llm_gateway_enabled", False),
            patch.object(settings, "qwen_enabled", True),
            patch.object(settings, "llama_enabled", True),
            patch.object(settings, "ensemble_enabled", True),
            patch.object(settings, "verifier_enabled", True),
            patch.object(settings, "synthesis_enabled", True),
            patch(
                "bisnu_x.brain.model_manager.generate",
                return_value="test answer",
            ) as generate,
        ):
            brain_answer(
                "Explain this.",
                max_new_tokens=73,
            )
            self.assertEqual(
                [call.kwargs["max_new_tokens"] for call in generate.call_args_list],
                [73, 73, 73],
            )

            generate.reset_mock()
            brain_answer(
                "Explain this.",
                requested_model="qwen",
                max_new_tokens=41,
            )

        generate.assert_called_once_with(
            "qwen",
            ANY,
            "Explain this.",
            max_new_tokens=41,
        )


class LLMGatewayTests(TestCase):
    def test_gateway_configuration_is_reported_as_ready_without_local_weights(self):
        manager = ModelManager()
        with (
            patch.object(settings, "llm_gateway_enabled", True),
            patch.object(settings, "llm_api_base_url", "https://gateway.example/v1"),
            patch.object(settings, "llm_api_key", "private-test-key"),
            patch.object(settings, "llm_model", "test-model"),
        ):
            status = manager.status()

        self.assertTrue(status["ready"])
        self.assertFalse(status["loaded"])
        self.assertTrue(status["gateway"]["configured"])

    def test_enabled_but_incomplete_gateway_is_not_ready(self):
        manager = ModelManager()
        with (
            patch.object(settings, "llm_gateway_enabled", True),
            patch.object(settings, "llm_api_base_url", ""),
            patch.object(settings, "llm_api_key", ""),
            patch.object(settings, "llm_model", ""),
        ):
            status = manager.status()

        self.assertFalse(status["ready"])
        self.assertFalse(status["gateway"]["configured"])

    def test_openai_compatible_gateway_uses_backend_key_and_returns_answer(self):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {"message": {"content": "Gateway response"}}
            ]
        }

        with (
            patch.object(
                settings,
                "llm_api_base_url",
                "https://gateway.example/v1",
            ),
            patch.object(settings, "llm_api_key", "private-test-key"),
            patch.object(settings, "llm_model", "test-model"),
            patch("bisnu_x.inference.requests.post", return_value=response) as post,
        ):
            answer = ModelManager._generate_gateway(
                "system prompt",
                "user prompt",
                max_new_tokens=37,
            )

        self.assertEqual(answer, "Gateway response")
        self.assertEqual(
            post.call_args.args[0],
            "https://gateway.example/v1/chat/completions",
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer private-test-key",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["model"],
            "test-model",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["max_tokens"],
            37,
        )

    def test_gateway_rejects_non_https_remote_endpoint(self):
        with (
            patch.object(settings, "llm_api_base_url", "http://gateway.example/v1"),
            patch.object(settings, "llm_api_key", "private-test-key"),
            patch.object(settings, "llm_model", "test-model"),
            patch("bisnu_x.inference.requests.post") as post,
        ):
            with self.assertRaisesRegex(RuntimeError, "must use HTTPS"):
                ModelManager._generate_gateway("system", "user")

        post.assert_not_called()

    def test_gateway_mode_uses_one_remote_completion_instead_of_local_ensemble(self):
        with (
            patch.object(settings, "llm_gateway_enabled", True),
            patch.object(settings, "llm_model", "test-model"),
            patch.object(settings, "ensemble_enabled", True),
            patch.object(settings, "verifier_enabled", True),
            patch.object(settings, "synthesis_enabled", True),
            patch(
                "bisnu_x.brain.model_manager.generate",
                return_value="Gateway answer",
            ) as generate,
        ):
            result = brain_answer(
                "Explain this.",
                max_new_tokens=43,
            )

        self.assertEqual(result["answer"], "Gateway answer")
        self.assertEqual(result["model"], "test-model")
        generate.assert_called_once_with(
            "gateway",
            ANY,
            "Explain this.",
            max_new_tokens=43,
        )


class PostgresCompatibilityTests(TestCase):
    def test_translates_sqlite_specific_database_queries(self):
        self.assertEqual(
            db.PostgresConnection._translate(
                "SELECT * FROM user_memories "
                "WHERE user_id=? AND instr(lower(text), lower(?)) > 0"
            ),
            "SELECT * FROM user_memories "
            "WHERE user_id=%s AND POSITION(LOWER(%s) IN LOWER(text)) > 0",
        )
        self.assertEqual(
            db.PostgresConnection._translate(
                "INSERT OR IGNORE INTO payment_webhook_events "
                "(event_id, created_at) VALUES (?, ?)"
            ),
            "INSERT INTO payment_webhook_events "
            "(event_id, created_at) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
        )
        self.assertEqual(
            db.PostgresConnection._translate(
                "INSERT OR REPLACE INTO revoked_tokens "
                "(token_hash, expires_at) VALUES (?, ?)"
            ),
            "INSERT INTO revoked_tokens "
            "(token_hash, expires_at) VALUES (%s, %s) "
            "ON CONFLICT (token_hash) DO UPDATE "
            "SET expires_at = EXCLUDED.expires_at",
        )

    def test_persistent_deployment_refuses_sqlite_fallback(self):
        with (
            patch.object(db, "DATABASE_URL", ""),
            patch.object(db, "REQUIRE_PERSISTENT_DATABASE", True),
        ):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                db.connection()

    def test_postgres_startup_applies_additive_schema_migrations(self):
        class RecordingConnection:
            def __init__(self):
                self.statements = []
                self.committed = False
                self.closed = False

            def execute(self, statement, parameters=()):
                self.statements.append(statement)

            def commit(self):
                self.committed = True

            def rollback(self):
                raise AssertionError("Unexpected rollback.")

            def close(self):
                self.closed = True

        connection = RecordingConnection()
        with (
            patch.object(db, "DATABASE_URL", "postgresql://test"),
            patch.object(db, "connection", return_value=connection),
        ):
            db.init_db()

        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)
        self.assertTrue(
            any(
                "ADD COLUMN IF NOT EXISTS username" in statement
                for statement in connection.statements
            )
        )
        self.assertTrue(
            any(
                "ADD COLUMN IF NOT EXISTS expected_amount" in statement
                for statement in connection.statements
            )
        )
