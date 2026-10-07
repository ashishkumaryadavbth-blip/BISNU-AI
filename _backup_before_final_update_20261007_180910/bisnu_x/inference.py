from __future__ import annotations

import gc
import threading
from typing import Any
from urllib.parse import urlparse

import requests
from bisnu_x.config import settings


class ModelManager:
    """
    OpenAI-compatible gateway client and resource-safe local Transformers runtime.

    Only one model is kept loaded at a time on CPU.
    Qwen and Llama configuration is preserved.
    """

    def __init__(self):
        self.lock = threading.RLock()

        self.tokenizer = None
        self.model = None

        self.loaded_name = None
        self.active_device = None
        self.load_error = None

    def configured(self):
        return {
            "qwen": {
                "enabled": settings.qwen_enabled,
                "name": settings.qwen_model
            },
            "llama": {
                "enabled": settings.llama_enabled,
                "name": settings.llama_model
            },
            "bisnu": {
                "enabled": settings.bisnu_enabled,
                "name": settings.bisnu_model
            }
        }

    def status(self):
        gateway_ready = (
            settings.llm_gateway_enabled
            and bool(
                settings.llm_api_base_url
                and settings.llm_api_key
                and settings.llm_model
            )
        )
        ready = (
            gateway_ready
            if settings.llm_gateway_enabled
            else self.model is not None
        )
        return {
            "loaded": self.model is not None,
            "ready": ready,
            "runtime": (
                "gateway" if settings.llm_gateway_enabled else "local"
            ),
            "loaded_model": self.loaded_name,
            "load_error": self.load_error,
            "device": self.active_device or settings.device,
            "gateway": {
                "enabled": settings.llm_gateway_enabled,
                "configured": gateway_ready,
                "model": settings.llm_model or None,
            },
            "models": self.configured()
        }

    def unload(self):
        self.tokenizer = None
        self.model = None
        self.loaded_name = None
        self.active_device = None

        gc.collect()

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception:
            pass

    @staticmethod
    def _resolve_device():
        import torch

        requested = settings.device.strip().lower()
        if requested == "auto":
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("DEVICE=cuda was requested but CUDA is unavailable.")
        if requested == "mps" and not (
            hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        ):
            raise RuntimeError("DEVICE=mps was requested but MPS is unavailable.")
        if requested not in {"cpu", "cuda", "mps"}:
            raise ValueError("DEVICE must be auto, cpu, cuda, or mps.")
        return requested

    def _spec(self, name: str):
        name = name.lower()

        if name == "qwen":
            return (
                settings.qwen_model,
                settings.qwen_enabled
            )

        if name == "llama":
            return (
                settings.llama_model,
                settings.llama_enabled
            )

        if name in {
            "bisnu",
            "bisnu-1.1"
        }:
            return (
                settings.bisnu_model,
                settings.bisnu_enabled
            )

        raise ValueError(
            f"Unknown model: {name}"
        )

    def load(self, name: str):
        with self.lock:
            model_name, enabled = self._spec(
                name
            )

            if not enabled:
                raise RuntimeError(
                    f"{name} model is disabled."
                )

            if not model_name:
                raise RuntimeError(
                    f"{name} model is not configured."
                )

            if (
                self.model is not None
                and self.loaded_name == name
            ):
                return

            self.unload()

            try:
                from transformers import (
                    AutoModelForCausalLM,
                    AutoTokenizer
                )

                tokenizer = (
                    AutoTokenizer.from_pretrained(
                        model_name
                    )
                )

                model = (
                    AutoModelForCausalLM.from_pretrained(
                        model_name
                    )
                )

                model.to(self._resolve_device())

                model.eval()

                self.tokenizer = tokenizer
                self.model = model
                self.loaded_name = name
                self.active_device = str(model.device)
                self.load_error = None

            except Exception as exc:
                self.unload()
                self.load_error = (
                    f"{type(exc).__name__}: {exc}"
                )
                raise

    def generate(
        self,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int | None = None
    ):
        if settings.llm_gateway_enabled:
            return self._generate_gateway(
                system_prompt,
                user_prompt,
                max_new_tokens,
            )

        with self.lock:

            self.load(
                model_name
            )

            if self.tokenizer is None:
                raise RuntimeError(
                    "Tokenizer unavailable."
                )

            if self.model is None:
                raise RuntimeError(
                    "Model unavailable."
                )

            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]

            tokenizer = self.tokenizer

            if hasattr(
                tokenizer,
                "apply_chat_template"
            ):
                inputs = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt"
                )
            else:
                prompt = (
                    system_prompt
                    + "\n\nUSER:\n"
                    + user_prompt
                    + "\n\nASSISTANT:\n"
                )

                inputs = tokenizer(
                    prompt,
                    return_tensors="pt"
                )["input_ids"]

            inputs = inputs.to(
                self.model.device
            )

            max_tokens = (
                max_new_tokens
                or settings.max_new_tokens
            )

            with __import__(
                "torch"
            ).no_grad():

                output = self.model.generate(
                    inputs,
                    max_new_tokens=max_tokens,
                    temperature=settings.temperature,
                    top_p=settings.top_p,
                    do_sample=True,
                    pad_token_id=(
                        tokenizer.eos_token_id
                    )
                )

            generated = output[
                0,
                inputs.shape[-1]:
            ]

            answer = tokenizer.decode(
                generated,
                skip_special_tokens=True
            ).strip()

            return answer

    @staticmethod
    def _generate_gateway(
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int | None = None,
    ) -> str:
        if not (
            settings.llm_api_base_url
            and settings.llm_api_key
            and settings.llm_model
        ):
            raise RuntimeError(
                "LLM gateway is enabled but its base URL, API key, or model is missing."
            )

        parsed_url = urlparse(settings.llm_api_base_url)
        if not parsed_url.hostname or parsed_url.query or parsed_url.fragment:
            raise RuntimeError(
                "LLM_API_BASE_URL must be a valid base URL without query or fragment."
            )
        if (
            parsed_url.scheme != "https"
            and parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}
        ):
            raise RuntimeError(
                "LLM_API_BASE_URL must use HTTPS except for a local development gateway."
            )
        if parsed_url.username or parsed_url.password:
            raise RuntimeError(
                "LLM_API_BASE_URL must not contain embedded credentials."
            )

        try:
            response = requests.post(
                f"{settings.llm_api_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": (
                        max_new_tokens or settings.max_new_tokens
                    ),
                    "temperature": settings.temperature,
                    "top_p": settings.top_p,
                },
                timeout=(10, 120),
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else None
            )
            if status_code is not None:
                raise RuntimeError(
                    f"LLM gateway request failed with HTTP {status_code}."
                ) from exc
            raise RuntimeError(
                "LLM gateway request could not be completed."
            ) from exc

        try:
            payload = response.json()
            answer = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "LLM gateway returned an invalid chat-completions response."
            ) from exc

        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(
                "LLM gateway returned an empty answer."
            )

        return answer.strip()


model_manager = ModelManager()
