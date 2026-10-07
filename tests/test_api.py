import tempfile
import unittest
import os
import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from bisnu_x.api.server import create_app
from bisnu_x.auth.mobile_auth import MobileAuthStore
from bisnu_x.memory.memory_store import MemoryStore
from bisnu_x.tools.filesystem import WorkspaceFiles
from bisnu_x.vision.provider import TransformersVisionProvider


class ApiTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"MODEL_NAME": "", "CHECKPOINT_PATH": ""}):
            self.app = create_app()
        self.temp = tempfile.TemporaryDirectory()
        self.app.state.memory_store = MemoryStore(Path(self.temp.name) / "memory.sqlite3")
        self.app.state.mobile_memory_store = lambda user_id: MemoryStore(
            Path(self.temp.name) / f"{user_id}.sqlite3"
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_health_reports_unconfigured_model(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["model"]["model"])
        self.assertFalse(response.json()["model"]["loaded"])

    def test_mobile_otp_requires_real_provider_configuration(self):
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "",
            "TWILIO_VERIFY_SERVICE_SID": "", "BISNU_AUTH_SECRET": "",
        }):
            response = self.client.post("/auth/send-otp", json={"phone": "+14155552671"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("configure Twilio Verify", response.json()["detail"])

    def test_mobile_otp_verification_issues_a_signed_session(self):
        class ApprovedResponse:
            is_error = False

            @staticmethod
            def json():
                return {"status": "approved"}

        class TwilioClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def post(self, *_args, **_kwargs):
                return ApprovedResponse()

        store = MobileAuthStore(Path(self.temp.name) / "auth.sqlite3")
        with patch.dict(os.environ, {"BISNU_AUTH_SECRET": "x" * 48}), \
                patch.object(MobileAuthStore, "_provider_config", return_value=("AC-test", "secret", "VA-test")), \
                patch("bisnu_x.auth.mobile_auth.httpx.AsyncClient", return_value=TwilioClient()):
            user, token, expires_in = asyncio.run(store.verify_otp("+14155552674", "123456"))
            self.assertEqual(store.read_token(token), user["id"])
        self.assertEqual(user["phone"], "+14155552674")
        self.assertEqual(expires_in, 60 * 60 * 24 * 30)

    def test_mobile_memory_requires_a_valid_session_and_is_user_scoped(self):
        self.assertEqual(self.client.get("/mobile/memory").status_code, 401)
        self.assertEqual(self.client.get("/memory").status_code, 401)
        with patch.dict(os.environ, {"BISNU_AUTH_SECRET": "x" * 48}):
            first = self.app.state.mobile_auth._get_or_create("+14155552671")
            second = self.app.state.mobile_auth._get_or_create("+14155552672")
            first_token = self.app.state.mobile_auth._issue_token(first["id"], 600)
            second_token = self.app.state.mobile_auth._issue_token(second["id"], 600)
            first_headers = {"Authorization": f"Bearer {first_token}"}
            second_headers = {"Authorization": f"Bearer {second_token}"}
            saved = self.client.post("/mobile/memory", headers=first_headers, json={
                "text": "prefers concise answers", "approved": True,
            })
            self.assertEqual(saved.status_code, 200)
            first_items = self.client.get("/mobile/memory", headers=first_headers).json()["items"]
            second_items = self.client.get("/mobile/memory", headers=second_headers).json()["items"]
        self.assertEqual(len(first_items), 1)
        self.assertEqual(second_items, [])

    def test_profile_creation_requires_bearer_session(self):
        self.assertEqual(self.client.post("/auth/profile", json={
            "name": "BISNU User", "username": "bisnu_user",
        }).status_code, 401)
        with patch.dict(os.environ, {"BISNU_AUTH_SECRET": "x" * 48}):
            user = self.app.state.mobile_auth._get_or_create("+14155552673")
            token = self.app.state.mobile_auth._issue_token(user["id"], 600)
            response = self.client.post("/auth/profile", headers={"Authorization": f"Bearer {token}"}, json={
                "name": "BISNU User", "username": "bisnu_user",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["username"], "bisnu_user")

    def test_chat_uses_verified_calculator_without_model_weights(self):
        response = self.client.post("/v1/chat", json={
            "messages": [{"role": "user", "content": "What is 19 * 23?"}]
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "437")
        self.assertEqual(response.json()["tool_usage"], ["calculator"])
        self.assertTrue(response.json()["verification"]["passed"])

    def test_streaming_calculator_response_is_sse(self):
        response = self.client.post("/v1/chat", json={
            "messages": [{"role": "user", "content": "What is 19 * 23?"}],
            "stream": True,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn('"token": "437"', response.text)
        self.assertIn("event: done", response.text)

    def test_request_id_is_consistent_in_body_and_header(self):
        response = self.client.post("/v1/chat", headers={"X-Request-ID": "test-request"}, json={
            "messages": [{"role": "user", "content": "What is 2 + 2?"}]
        })
        self.assertEqual(response.headers["x-request-id"], "test-request")
        self.assertEqual(response.json()["request_id"], "test-request")

    def test_general_chat_does_not_fabricate_without_model(self):
        response = self.client.post("/v1/chat", json={
            "messages": [{"role": "user", "content": "Tell me a story."}]
        })
        self.assertEqual(response.status_code, 503)

    def test_memory_requires_explicit_approval(self):
        response = self.client.post("/v1/memory", json={"text": "likes concise answers"})
        self.assertEqual(response.status_code, 400)
        accepted = self.client.post("/v1/memory", json={
            "text": "likes concise answers", "approved": True,
        })
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(len(self.client.get("/v1/memory").json()["items"]), 1)
        filtered = self.client.get("/v1/memory", params={"query": "concise"})
        self.assertEqual(len(filtered.json()["items"]), 1)

    def test_relevant_approved_memory_is_supplied_to_chat_model(self):
        self.app.state.memory_store.add("prefers Hindi responses", approved=True)
        with patch.object(self.app.state.inference, "generate", return_value="Namaste") as generate:
            response = self.client.post("/v1/chat", json={
                "messages": [{"role": "user", "content": "Reply in Hindi"}]
            })
        self.assertEqual(response.status_code, 200)
        system_prompt = generate.call_args.args[0][0]["content"]
        self.assertIn("prefers Hindi responses", system_prompt)

    def test_document_qa_returns_retrieved_page_evidence(self):
        workspace = Path(self.temp.name)
        (workspace / "manual.md").write_text("The access code is KAPPA-48.", encoding="utf-8")
        self.app.state.workspace_files = WorkspaceFiles(workspace)
        with patch.object(self.app.state.inference, "generate", return_value="The code is KAPPA-48 (page 1)."):
            response = self.client.post("/v1/documents/ask", json={
                "path": "manual.md", "question": "What is the access code?",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"][0]["page"], 1)
        self.assertIn("KAPPA-48", response.json()["sources"][0]["excerpt"])

    def test_live_research_response_has_real_source_metadata(self):
        source = {"title": "Python downloads", "url": "https://www.python.org/downloads/",
                  "domain": "www.python.org", "retrieved_at": "2026-09-28T00:00:00+00:00",
                  "excerpt": "Stable releases are published here."}
        tool_trace = [{"name": "web_search", "ok": True, "metadata": {}, "error": None}]
        with patch("bisnu_x.api.routes.chat._research", return_value=([source], tool_trace)), \
                patch.object(self.app.state.inference, "generate",
                             return_value="See https://www.python.org/downloads/ for current releases."):
            response = self.client.post("/v1/chat", json={
                "messages": [{"role": "user", "content": "What is the latest Python version?"}]
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"][0]["domain"], "www.python.org")
        self.assertTrue(response.json()["verification"]["passed"])

    def test_vision_without_configured_model_returns_capability_error(self):
        self.app.state.vision_provider = TransformersVisionProvider()
        image = Path(self.temp.name) / "sample.png"
        image.write_bytes(b"not-decoded-because-no-vision-provider")
        self.app.state.workspace_files = WorkspaceFiles(self.temp.name)
        response = self.client.post("/v1/vision/analyze", json={"path": "sample.png"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("No vision-capable model", response.json()["detail"])

    def test_conversation_history_is_reused_for_single_turn_api_clients(self):
        conversation_id = "history-test"
        with patch.object(self.app.state.inference, "generate", side_effect=["first answer", "second answer"]) as generate:
            first = self.client.post("/v1/chat", json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "Remember the word orchid."}],
            })
            second = self.client.post("/v1/chat", json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "What word did I mention?"}],
            })
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        second_messages = generate.call_args_list[1].args[0]
        self.assertTrue(any(message["content"] == "Remember the word orchid." for message in second_messages))
        self.assertTrue(any(message["content"] == "first answer" for message in second_messages))


if __name__ == "__main__":
    unittest.main()