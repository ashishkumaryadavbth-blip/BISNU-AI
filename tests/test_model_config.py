import os
import unittest
from unittest.mock import patch

from bisnu_x.model.config import ModelConfig


class ModelConfigTests(unittest.TestCase):
    def test_reads_model_settings_from_environment(self):
        with patch.dict(os.environ, {
            "MODEL_NAME": "open-model",
            "MAX_NEW_TOKENS": "64",
            "QUANTIZATION": "4bit",
            "CHECKPOINT_PATH": "local-checkpoint",
            "MODEL_OFFLINE": "true",
        }, clear=True):
            config = ModelConfig.from_env()

        self.assertEqual(config.model_name, "open-model")
        self.assertEqual(config.max_new_tokens, 64)
        self.assertEqual(config.quantization, "4bit")
        self.assertEqual(config.checkpoint_path, "local-checkpoint")
        self.assertTrue(config.local_files_only)

    def test_rejects_invalid_sampling_configuration(self):
        with self.assertRaisesRegex(ValueError, "TOP_P"):
            ModelConfig(top_p=0).validate()


if __name__ == "__main__":
    unittest.main()