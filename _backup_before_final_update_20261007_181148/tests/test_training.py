import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bisnu_x.training.config import TrainingConfig
from bisnu_x.training.dataset import load_dataset
from bisnu_x.training.trainer import train


class TrainingTests(unittest.TestCase):
    def test_starter_dataset_has_provenance_and_split_ready_examples(self):
        bundle = load_dataset("training_data/starter/train.jsonl", "training_data/starter/metadata.json")
        self.assertEqual(len(bundle.examples), 8)
        self.assertEqual(bundle.provenance["license"], "CC0-1.0")
        self.assertEqual(bundle.provenance["sample_count"], 8)

    def test_training_rejects_missing_dataset_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "data.jsonl").write_text(
                '{"prompt":"a","response":"b"}\n{"prompt":"c","response":"d"}\n',
                encoding="utf-8",
            )
            (path / "metadata.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provenance"):
                load_dataset(path / "data.jsonl", path / "metadata.json")

    def test_training_config_rejects_invalid_split_and_qlora_requires_cuda(self):
        config = TrainingConfig(
            model_name="unused", dataset_path="training_data/starter/train.jsonl",
            dataset_metadata_path="training_data/starter/metadata.json", validation_fraction=1,
        )
        with self.assertRaisesRegex(ValueError, "validation_fraction"):
            config.validate()
        qlora_config = TrainingConfig(
            model_name="unused", dataset_path="training_data/starter/train.jsonl",
            dataset_metadata_path="training_data/starter/metadata.json", method="qlora",
        )
        with patch("torch.cuda.is_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "requires CUDA"):
                train(qlora_config)


if __name__ == "__main__":
    unittest.main()