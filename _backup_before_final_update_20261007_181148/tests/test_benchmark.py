import unittest

from benchmarks.master_benchmark import evaluate, load_cases, summarize_progression


class BenchmarkTests(unittest.TestCase):
    def test_suite_covers_required_model_categories(self):
        cases = load_cases()
        categories = {case["category"].casefold() for case in cases}
        expected = {
            "reasoning", "math", "coding", "science", "knowledge", "english", "hindi",
            "hinglish", "multilingual", "long_context", "tool_use", "hallucination",
            "instruction_following", "agent_tasks", "source_consistency",
        }
        self.assertEqual(categories, expected)

    def test_category_evaluators_are_concrete(self):
        cases = {case["category"]: case for case in load_cases()}
        self.assertTrue(evaluate(cases["math"], "323"))
        self.assertTrue(evaluate(cases["coding"], "```python\ndef add(a, b):\n    return a + b\n```"))
        self.assertTrue(evaluate(cases["Hindi"], "पानी"))
        self.assertTrue(evaluate(cases["multilingual"], "hello नमस्ते hola"))
        self.assertIsNone(evaluate(cases["tool_use"], "24 * 37 is 888"))
        self.assertFalse(evaluate(cases["source_consistency"], "Latest is 3.14", []))
        self.assertIsNone(evaluate(cases["source_consistency"], "Latest is 3.14", None))

    def test_progression_tracks_score_delta_against_baseline(self):
        history = [
            {"run_id": "baseline", "summary": {"mean_score": 0.50}, "results": [
                {"category": "math", "score": 1.0},
                {"category": "math", "score": 0.0},
            ]},
            {"run_id": "v2", "summary": {"mean_score": 0.75}, "results": [
                {"category": "math", "score": 1.0},
                {"category": "math", "score": 1.0},
            ]},
        ]
        summary = summarize_progression(history)
        self.assertEqual(summary["baseline_run_id"], "baseline")
        self.assertEqual(summary["latest_run_id"], "v2")
        self.assertEqual(summary["delta"], 0.5)
        self.assertEqual(summary["direction"], "up")


if __name__ == "__main__":
    unittest.main()