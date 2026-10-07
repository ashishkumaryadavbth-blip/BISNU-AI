import unittest

from bisnu_x.model.config import ModelConfig
from bisnu_x.model.smoke_test import run_smoke_test


class ModelSmokeTests(unittest.TestCase):
    def test_unconfigured_model_is_not_tested_not_passed(self):
        result = run_smoke_test(ModelConfig(), "Test prompt")
        self.assertEqual(result["status"], "NOT TESTED")


if __name__ == "__main__":
    unittest.main()