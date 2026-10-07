from __future__ import annotations

import threading
from typing import Any

from .config import settings


class BISNUEngine:

    def __init__(self) -> None:

        self.lock = threading.Lock()

        self.loaded_name: str | None = None

        self.model: Any = None
        self.tokenizer: Any = None

        self.error: str | None = None

    # -------------------------------------------------
    # MODEL NAME
    # -------------------------------------------------

    def model_name(self, name: str) -> str:

        if name == "qwen":
            return settings.qwen_model

        if name == "llama":
            return settings.llama_model

        if name == "bisnu":

            if not settings.bisnu_model:
                raise RuntimeError(
                    "BISNU-1.1 checkpoint is not configured."
                )

            return settings.bisnu_model

        raise ValueError(
            f"Unknown model: {name}"
        )

    # -------------------------------------------------
    # LOAD ONE MODEL
    # -------------------------------------------------

    def load(self, name: str) -> None:

        with self.lock:

            if self.loaded_name == name:
                return

            self.unload()

            source = self.model_name(name)

            try:

                import torch
                from transformers import (
                    AutoTokenizer,
                    AutoModelForCausalLM,
                )

                tokenizer = AutoTokenizer.from_pretrained(
                    source
                )

                model = AutoModelForCausalLM.from_pretrained(
                    source,
                    torch_dtype="auto",
                    device_map=settings.device,
                )

                if tokenizer.pad_token_id is None:
                    tokenizer.pad_token = tokenizer.eos_token

                model.eval()

                self.model = model
                self.tokenizer = tokenizer
                self.loaded_name = name
                self.error = None

            except Exception as exc:

                self.model = None
                self.tokenizer = None
                self.loaded_name = None

                self.error = str(exc)

                raise RuntimeError(
                    f"Could not load {name}: {exc}"
                ) from exc

    # -------------------------------------------------
    # UNLOAD
    # -------------------------------------------------

    def unload(self) -> None:

        if self.model is not None:
            del self.model

        if self.tokenizer is not None:
            del self.tokenizer

        self.model = None
        self.tokenizer = None
        self.loaded_name = None

        try:

            import gc
            gc.collect()

            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception:
            pass

    # -------------------------------------------------
    # GENERATE
    # -------------------------------------------------

    def generate(
        self,
        name: str,
        messages: list[dict[str, str]],
    ) -> str:

        self.load(name)

        if self.model is None or self.tokenizer is None:
            raise RuntimeError(
                "Model is not loaded."
            )

        tokenizer = self.tokenizer
        model = self.model

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=settings.max_context_length,
        )

        inputs = {
            key: value.to(model.device)
            for key, value in inputs.items()
        }

        import torch

        with torch.inference_mode():

            output = model.generate(
                **inputs,
                max_new_tokens=settings.max_new_tokens,
                temperature=settings.temperature,
                top_p=settings.top_p,
                do_sample=True,
                use_cache=True,
            )

        input_length = inputs["input_ids"].shape[-1]

        answer = tokenizer.decode(
            output[0][input_length:],
            skip_special_tokens=True,
        )

        return answer.strip()

    # -------------------------------------------------
    # HEALTH
    # -------------------------------------------------

    def health(self) -> dict:

        return {
            "loaded_model": self.loaded_name,
            "qwen": {
                "enabled": settings.qwen_enabled,
                "model": settings.qwen_model,
            },
            "llama": {
                "enabled": settings.llama_enabled,
                "model": settings.llama_model,
            },
            "bisnu": {
                "enabled": settings.bisnu_enabled,
                "model": settings.bisnu_model,
            },
            "device": settings.device,
            "error": self.error,
        }


engine = BISNUEngine()
