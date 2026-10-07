from __future__ import annotations

import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from bisnu_x import db
from bisnu_x.app import app
from bisnu_x.config import settings
from bisnu_x.security import create_token


class UsernameAuthenticationTests(TestCase):
    def _isolated_client(self, directory: str):
        stack = ExitStack()
        stack.enter_context(
            patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3")
        )
        stack.enter_context(patch.object(db, "DATABASE_URL", ""))
        stack.enter_context(
            patch.object(db, "REQUIRE_PERSISTENT_DATABASE", False)
        )
        stack.enter_context(patch.object(settings, "jwt_secret", "j" * 32))
        return stack

    def test_register_login_duplicate_and_password_hash_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._isolated_client(directory):
                db.init_db()
                with TestClient(app) as client:
                    registered = client.post(
                        "/v1/auth/register",
                        json={"username": "Alice_1", "password": "long-password-123"},
                    )
                    self.assertEqual(registered.status_code, 200)
                    user = registered.json()["user"]
                    self.assertEqual(user["username"], "alice_1#bisnu-x.com")
                    self.assertNotIn("password_hash", user)

                    duplicate = client.post(
                        "/v1/auth/register",
                        json={
                            "username": "ALICE_1#bisnu-x.com",
                            "password": "long-password-456",
                        },
                    )
                    self.assertEqual(duplicate.status_code, 409)

                    logged_in = client.post(
                        "/v1/auth/login",
                        json={
                            "username": "ALICE_1#bisnu-x.com",
                            "password": "long-password-123",
                        },
                    )
                    self.assertEqual(logged_in.status_code, 200)
                    self.assertNotIn(
                        "password_hash",
                        logged_in.json()["user"],
                    )

                    rejected = client.post(
                        "/v1/auth/login",
                        json={
                            "username": "alice_1#bisnu-x.com",
                            "password": "wrong-password",
                        },
                    )
                    self.assertEqual(rejected.status_code, 401)

    def test_legacy_account_can_link_credentials_and_log_in(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._isolated_client(directory):
                db.init_db()
                with TestClient(app) as client:
                    legacy_user = db.create_user(
                        "legacy@example.test",
                        "Legacy",
                    )
                    response = client.put(
                        "/v1/auth/credentials",
                        headers={
                            "Authorization": (
                                f"Bearer {create_token(legacy_user['id'])}"
                            ),
                        },
                        json={
                            "username": "legacy_user",
                            "password": "legacy-password-123",
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertNotIn(
                        "password_hash",
                        response.json()["user"],
                    )

                    login = client.post(
                        "/v1/auth/login",
                        json={
                            "username": "legacy_user",
                            "password": "legacy-password-123",
                        },
                    )
                    self.assertEqual(login.status_code, 200)
                    self.assertEqual(
                        login.json()["user"]["id"],
                        legacy_user["id"],
                    )

    def test_conversation_history_is_restored_only_for_owning_user(self):
        with tempfile.TemporaryDirectory() as directory:
            with self._isolated_client(directory):
                db.init_db()
                with TestClient(app) as client:
                    first = client.post(
                        "/v1/auth/register",
                        json={"username": "first_user", "password": "first-password-123"},
                    ).json()
                    second = client.post(
                        "/v1/auth/register",
                        json={"username": "second_user", "password": "second-password-123"},
                    ).json()
                    conversation_id = db.create_conversation(
                        first["user"]["id"],
                        "Saved chat",
                    )
                    db.save_message(
                        conversation_id,
                        first["user"]["id"],
                        "user",
                        "Remember this question",
                    )

                    first_headers = {
                        "Authorization": f"Bearer {first['token']}",
                    }
                    second_headers = {
                        "Authorization": f"Bearer {second['token']}",
                    }
                    conversations = client.get(
                        "/v1/conversations",
                        headers=first_headers,
                    )
                    self.assertEqual(conversations.status_code, 200)
                    self.assertEqual(
                        [item["id"] for item in conversations.json()["conversations"]],
                        [conversation_id],
                    )

                    restored = client.get(
                        f"/v1/conversations/{conversation_id}",
                        headers=first_headers,
                    )
                    self.assertEqual(restored.status_code, 200)
                    self.assertEqual(
                        restored.json()["messages"][0]["content"],
                        "Remember this question",
                    )
                    forbidden = client.get(
                        f"/v1/conversations/{conversation_id}",
                        headers=second_headers,
                    )
                    self.assertEqual(forbidden.status_code, 404)
