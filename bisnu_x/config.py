from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


class Settings:
    app_name = "BISNU-X"

    version = "7.0.0"

    project_root = ROOT

    host = os.getenv(
        "BISNU_HOST",
        "127.0.0.1"
    )

    port = env_int(
        "BISNU_PORT",
        8000
    )

    database = os.getenv(
        "BISNU_DATABASE",
        os.getenv("DB_PATH", "bisnu_x.db")
    )

    # --------------------------------------------------------
    # MODELS
    # --------------------------------------------------------

    qwen_model = os.getenv(
        "QWEN_MODEL",
        "Qwen/Qwen3-8B"
    )

    llama_model = os.getenv(
        "LLAMA_MODEL",
        "meta-llama/Llama-3.2-3B-Instruct"
    )

    bisnu_model = os.getenv(
        "BISNU_MODEL",
        ""
    )

    qwen_enabled = env_bool(
        "QWEN_ENABLED",
        True
    )

    llama_enabled = env_bool(
        "LLAMA_ENABLED",
        True
    )

    bisnu_enabled = env_bool(
        "BISNU_ENABLED",
        False
    )

    llm_gateway_enabled = env_bool(
        "LLM_GATEWAY_ENABLED",
        False
    )

    llm_api_base_url = os.getenv(
        "LLM_API_BASE_URL",
        ""
    ).strip().rstrip("/")

    llm_api_key = os.getenv(
        "LLM_API_KEY",
        ""
    ).strip()

    llm_model = os.getenv(
        "LLM_MODEL",
        ""
    ).strip()

    device = os.getenv(
        "DEVICE",
        os.getenv("BISNU_DEVICE", "auto")
    )

    max_context_length = env_int(
        "MAX_CONTEXT_LENGTH",
        env_int("BISNU_CONTEXT", 8192)
    )

    max_new_tokens = env_int(
        "MAX_NEW_TOKENS",
        env_int("BISNU_MAX_NEW_TOKENS", 512)
    )

    temperature = env_float(
        "TEMPERATURE",
        env_float("BISNU_TEMPERATURE", 0.7)
    )

    top_p = env_float(
        "TOP_P",
        env_float("BISNU_TOP_P", 0.9)
    )

    # --------------------------------------------------------
    # BRAIN
    # --------------------------------------------------------

    ensemble_enabled = env_bool(
        "ENSEMBLE_ENABLED",
        True
    )

    verifier_enabled = env_bool(
        "VERIFIER_ENABLED",
        True
    )

    synthesis_enabled = env_bool(
        "SYNTHESIS_ENABLED",
        True
    )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    live_search_enabled = env_bool(
        "LIVE_SEARCH",
        env_bool("LIVE_SEARCH_ENABLED", True)
    )

    search_results = env_int(
        "SEARCH_RESULTS",
        8
    )

    # --------------------------------------------------------
    # SECURITY
    # --------------------------------------------------------

    jwt_secret = (
        os.getenv("BISNU_JWT_SECRET")
        or os.getenv("BISNU_SECRET_KEY", "")
    )

    payment_webhook_secret = os.getenv(
        "PAYMENT_WEBHOOK_SECRET",
        ""
    )

    admin_key = os.getenv(
        "BISNU_ADMIN_KEY",
        ""
    )

    google_client_id = (
        os.getenv("GOOGLE_CLIENT_ID")
        or os.getenv("GOOGLE_WEB_CLIENT_ID", "")
    )

    android_api_url = os.getenv(
        "BISNU_API_URL",
        ""
    ).strip()

    cors_origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "BISNU_CORS_ORIGINS",
            "http://localhost:7357,http://127.0.0.1:7357"
        ).split(",")
        if origin.strip()
    )

    jwt_expire_hours = env_int(
        "JWT_EXPIRE_HOURS",
        168
    )

    rate_limit = env_int(
        "RATE_LIMIT",
        60
    )

    rate_window = env_int(
        "RATE_WINDOW",
        60
    )

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    upload_dir = os.getenv(
        "UPLOAD_DIR",
        "bisnu_x/uploads"
    )

    max_upload_mb = env_int(
        "MAX_UPLOAD_MB",
        15
    )

    # --------------------------------------------------------
    # PAYMENT
    # --------------------------------------------------------

    razorpay_key_id = os.getenv("RAZORPAY_KEY_ID", "")
    razorpay_key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    razorpay_webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    razorpay_premium_plan_id = os.getenv("RAZORPAY_PREMIUM_PLAN_ID", "")
    razorpay_ultra_plan_id = os.getenv("RAZORPAY_ULTRA_PLAN_ID", "")

    payment_qr_path = os.getenv(
        "RAZORPAY_PAYMENT_QR_PATH",
        "payment/razorpay-qr.png",
    ).strip()

    razorpay_subscription_total_count = env_int(
        "RAZORPAY_SUBSCRIPTION_TOTAL_COUNT",
        360,
    )


settings = Settings()
