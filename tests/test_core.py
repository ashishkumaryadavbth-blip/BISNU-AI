import tempfile
import unittest
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bisnu_x.agents.language_agent import LanguageAgent
from bisnu_x.agents.math_agent import MathAgent
from bisnu_x.live.freshness import classify_freshness, detect_temporal_intent, validate_live_source
from bisnu_x.memory.memory_store import MemoryStore
from bisnu_x.reasoning.router import route_request
from bisnu_x.reasoning.reasoning_engine import ReasoningEngine
from bisnu_x.reasoning.verifier import verify_json, verify_python_syntax, verify_sources, verify_tool_results
from bisnu_x.tools.calculator import calculate
from bisnu_x.tools.filesystem import WorkspaceFiles
from bisnu_x.tools.registry import RiskLevel, ToolRegistry, ToolSpec, registry
from bisnu_x.tools.web_fetch import fetch_page
from bisnu_x.vision.document_qa import chunk_document, retrieve_chunks


class CoreTests(unittest.TestCase):
    def test_calculator_evaluates_without_python_execution(self):
        self.assertEqual(calculate("(2 + 3) * 4"), 20)
        with self.assertRaises(ValueError):
            calculate("__import__('os').system('whoami')")
        with self.assertRaisesRegex(ValueError, "Complex-number"):
            calculate("(-1)**0.5")

    def test_web_fetch_blocks_private_destinations(self):
        with self.assertRaisesRegex(ValueError, "non-public"):
            asyncio.run(fetch_page("https://127.0.0.1/"))

    def test_router_uses_research_for_current_information(self):
        self.assertEqual(route_request("What is the latest Python version?")["task"], "research")

    def test_router_respects_explicit_modes_but_keeps_live_research(self):
        self.assertEqual(route_request("Help me write a function", "coding")["task"], "coding")
        self.assertEqual(route_request("What is the latest Python version?", "coding")["task"], "research")

    def test_live_data_requires_real_retrieval_and_freshness_metadata(self):
        self.assertTrue(detect_temporal_intent("What is happening in India today?"))
        now = datetime.now(timezone.utc)
        fetched = {
            "title": "India News",
            "url": "https://example.org/india-news",
            "retrieved_at": (now - timedelta(minutes=5)).isoformat(),
            "published_at": (now - timedelta(minutes=30)).isoformat(),
            "source_status": "retrieved",
            "excerpt": "India's government announced a new policy."
        }
        self.assertEqual(classify_freshness(fetched["retrieved_at"], fetched["published_at"]), "live")
        self.assertEqual(validate_live_source(fetched)["freshness"], "live")
        with self.assertRaises(ValueError):
            validate_live_source({"title": "Snippet", "url": "https://example.org", "source_status": "search_snippet"})

    def test_language_agent_handles_common_hindi_and_hinglish_prompts(self):
        agent = LanguageAgent(None)
        self.assertEqual(agent.translate("water", target="hindi"), "पानी")
        self.assertEqual(agent.translate("How are you?", target="hinglish"), "कैसे हो?")
        self.assertEqual(agent.translate("hello", target="hindi"), "नमस्ते")

    def test_math_agent_verifies_arithmetic_and_defers_symbolic_equations(self):
        agent = MathAgent(None)
        result = agent.solve_expression("What is 19 * 23?")
        self.assertEqual(result[0], "437")
        self.assertTrue(result[1].passed)
        self.assertIsNone(agent.solve_expression("Solve x^2 = 4"))

    def test_verifiers_check_structure_and_syntax(self):
        self.assertTrue(verify_json('{"answer": 1}', ["answer"]).passed)
        self.assertFalse(verify_json('{"answer": 1}', ["source"]).passed)
        self.assertFalse(verify_python_syntax("def broken(:").passed)

    def test_source_and_tool_verifiers_check_actual_metadata(self):
        self.assertTrue(verify_sources(
            "Evidence https://example.org/a", [{"url": "https://example.org/a"}]
        ).passed)
        self.assertFalse(verify_sources(
            "Evidence https://evil.example/a", [{"url": "https://example.org/a"}]
        ).passed)
        self.assertTrue(verify_tool_results([{"name": "calculator", "ok": True}]).passed)
        self.assertFalse(verify_tool_results([{"name": "web_fetch", "ok": False}]).passed)

    def test_reasoning_engine_retries_failed_json_check_once(self):
        class SequenceInference:
            def __init__(self):
                self.answers = iter(["not json", '{"ok": true}'])

            def generate(self, messages):
                return next(self.answers)

        result = ReasoningEngine(SequenceInference()).answer([
            {"role": "user", "content": "Return valid JSON with an ok field"}
        ])
        self.assertEqual(result["answer"], '{"ok": true}')
        self.assertTrue(result["verification"]["passed"])
        self.assertEqual(len(result["verification"]["attempts"]), 2)

    def test_document_chunk_retrieval_preserves_page_reference(self):
        document = {"pages": [
            {"page": 1, "text": "General notes. " * 80},
            {"page": 2, "text": "The access code is KAPPA-48."},
        ]}
        chunks = chunk_document(document, chunk_chars=180, overlap=20)
        matches = retrieve_chunks(chunks, "what is the access code")
        self.assertTrue(matches)
        self.assertEqual(matches[0]["page"], 2)

    def test_memory_requires_approval_and_can_be_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.sqlite3")
            with self.assertRaises(PermissionError):
                store.add("likes concise answers", approved=False)
            item = store.add("likes concise answers", approved=True, retention_days=30)
            self.assertEqual(store.search("concise"), [item])
            self.assertEqual(store.search("please answer concisely"), [])
            self.assertEqual(store.search("please answer concise"), [item])
            self.assertTrue(store.delete(item["id"]))
            self.assertEqual(store.list(), [])

    def test_workspace_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            files = WorkspaceFiles(directory)
            with self.assertRaises(PermissionError):
                files.resolve("../outside.txt")

    def test_dangerous_registry_tool_never_executes_by_default(self):
        registry = ToolRegistry()
        registry.register(ToolSpec("erase", "test", {}, RiskLevel.DANGEROUS,
                                   frozenset(), lambda: "executed"))
        with self.assertRaises(PermissionError):
            registry.execute("erase", {})

    def test_real_tools_are_registered_with_permissions_and_schemas(self):
        tools = {tool["name"]: tool for tool in registry.describe()}
        self.assertEqual(set(tools), {
            "calculator", "web_search", "web_fetch", "document_parser",
            "workspace_file_reader", "structured_json",
        })
        self.assertIn("output_schema", tools["web_fetch"])
        with self.assertRaises(PermissionError):
            registry.execute("calculator", {"expression": "2 + 2"})
        with self.assertRaisesRegex(ValueError, "expression must be string"):
            registry.execute("calculator", {"expression": 2}, {"calculator"})

    def test_tool_timeout_returns_structured_error_metadata(self):
        tools = ToolRegistry()
        tools.register(ToolSpec(
            "slow", "timeout check", {"type": "object"}, RiskLevel.READ_ONLY,
            frozenset({"slow"}), lambda: time.sleep(0.2),
            timeout_seconds=0.01,
        ))
        result = tools.execute("slow", {}, {"slow"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error["type"], "TimeoutError")
        self.assertIn("elapsed_seconds", result.metadata)


if __name__ == "__main__":
    unittest.main()