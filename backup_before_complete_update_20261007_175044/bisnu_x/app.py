from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from bisnu_x.brain import brain
from bisnu_x.config import settings
from bisnu_x import db
from bisnu_x.inference import model_manager
from bisnu_x import payments
from bisnu_x.scanner import save_image
from bisnu_x.search import search as live_search
from bisnu_x.security import (
    admin_allowed,
    current_user,
    create_token,
    hash_password,
    public_user,
    revoke_token,
    verify_password,
)


APP_VERSION = "7.0.0"
logger = logging.getLogger(__name__)


app = FastAPI(
    title="BISNU-X",
    description="BISNU-X independent AI core",
    version=APP_VERSION,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:7357",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:7357",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# SIMPLE IN-MEMORY RATE LIMIT
# ============================================================

RATE_BUCKETS = defaultdict(deque)


def rate_allowed(key: str) -> bool:
    now = time.time()

    bucket = RATE_BUCKETS[key]

    while bucket and (
        now - bucket[0] > settings.rate_window
    ):
        bucket.popleft()

    if len(bucket) >= settings.rate_limit:
        return False

    bucket.append(now)

    return True


@app.middleware("http")
async def security_middleware(
    request: Request,
    call_next,
):
    client = (
        request.client.host
        if request.client
        else "unknown"
    )

    # Health/status should remain available even if a client
    # has exhausted the normal request bucket.
    bypass = request.url.path in {
        "/",
        "/health",
        "/api/status",
    }

    if not bypass:
        if not rate_allowed(client):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded."
                },
            )

    response = await call_next(request)

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return response


# ============================================================
# REQUEST MODELS
# ============================================================

class CredentialsRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=44,
        pattern=r"^[a-zA-Z0-9_]{3,32}(?:#bisnu-x\.com)?$",
    )
    password: str = Field(
        min_length=10,
        max_length=128,
    )


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=44,
        pattern=r"^[a-zA-Z0-9_]{3,32}(?:#bisnu-x\.com)?$",
    )
    password: str = Field(
        min_length=1,
        max_length=128,
    )


class ProfileRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )
    username: str = Field(
        min_length=3,
        max_length=44,
        pattern=r"^[a-zA-Z0-9_]{3,32}(?:#bisnu-x\.com)?$",
    )


class MemoryRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=2000,
    )
    approved: bool = False


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=12000,
    )

    conversation_id: str | None = None

    model: str = Field(
        default="auto",
        pattern=r"^(auto|qwen|llama|bisnu|bisnu-1\.1)$",
    )

    use_search: bool = False

    memory_enabled: bool = False

    max_new_tokens: int = Field(
        default=settings.max_new_tokens,
        ge=1,
        le=2048,
    )


class ConversationRequest(BaseModel):
    title: str = Field(
        default="New conversation",
        min_length=1,
        max_length=200,
    )


class SubscriptionRequest(BaseModel):
    plan: str = Field(
        pattern=r"^(PREMIUM|ULTRA)$",
    )


@app.patch("/v1/auth/profile")
def update_profile(
    payload: ProfileRequest,
    user=Depends(current_user),
):
    try:
        updated = db.update_user_profile(
            user["id"],
            payload.name.strip(),
            normalize_account_id(payload.username),
        )
    except db.UsernameTakenError as exc:
        raise HTTPException(
            status_code=409,
            detail="That username is already in use.",
        ) from exc
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="User profile not found.",
        )

    profile = db.get_user(user["id"])
    return {"profile": public_user(profile)}


@app.get("/v1/memory")
def get_memories(
    query: str = "",
    user=Depends(current_user),
):
    return {
        "items": db.list_user_memories(
            user["id"],
            query,
        ),
    }


@app.post("/v1/memory")
def save_memory(
    payload: MemoryRequest,
    user=Depends(current_user),
):
    if not payload.approved:
        raise HTTPException(
            status_code=400,
            detail="Explicit approval is required to save a memory.",
        )
    memory_id = db.add_user_memory(
        user["id"],
        payload.text.strip(),
    )
    return {"id": memory_id, "saved": True}


@app.delete("/v1/memory/{memory_id}")
def remove_memory(
    memory_id: str,
    user=Depends(current_user),
):
    if not db.delete_user_memory(
        user["id"],
        memory_id,
    ):
        raise HTTPException(
            status_code=404,
            detail="Memory not found.",
        )
    return {"deleted": True}


@app.get("/v1/conversations")
def get_conversations(
    user=Depends(current_user),
):
    return {
        "conversations": db.list_conversations(
            user["id"],
        ),
    }


@app.get("/v1/scanner/access")
def scanner_access(
    user=Depends(current_user),
):
    try:
        payments.require_plan(user["id"], "PREMIUM")
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        return {
            "allowed": False,
            "premium_available": payments.payments_available(),
            "detail": (
                "An active Premium subscription is required."
                if payments.payments_available()
                else "Premium subscriptions are coming soon."
            ),
        }

    return {
        "allowed": True,
        "premium_available": payments.payments_available(),
    }


@app.get("/v1/me/subscription")
def subscription_status(
    user=Depends(current_user),
):
    return {
        "plan": user.get("plan", "FREE"),
        "subscription": db.get_user_subscription(
            user["id"],
        ),
        "available": payments.payments_available(),
    }


@app.post("/v1/subscriptions")
def create_user_subscription(
    payload: "SubscriptionRequest",
    user=Depends(current_user),
):
    payments.require_payment_configuration()
    return payments.create_subscription(
        user["id"],
        payload.plan,
    )


@app.post("/v1/subscriptions/cancel")
def cancel_user_subscription(
    user=Depends(current_user),
):
    payments.require_payment_configuration()
    return payments.cancel_subscription(
        user["id"],
    )


@app.post("/v1/payment/webhook")
async def razorpay_webhook(request: Request):
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Razorpay webhook payload must be valid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Razorpay webhook payload must be a JSON object.",
        )
    return payments.process_razorpay_webhook(
        payload,
        raw_body,
        request.headers.get("x-razorpay-signature"),
        request.headers.get("x-razorpay-event-id"),
    )


# ============================================================
# CREATOR RESPONSE
# ============================================================

CREATOR_TRIGGERS = [
    "who made you",
    "who created you",
    "who created u",
    "who built you",
    "who developed you",
    "who is your creator",
    "who is your developer",
    "who made u",
    "who built u",
    "kisne banaya",
    "kisne banaya hai",
    "tumhe kisne banaya",
    "tumhe kisne banaya hai",
    "aapko kisne banaya",
    "aapko kisne banaya hai",
    "tumhara creator kaun",
    "tumhare creator kaun",
    "tumhara developer kaun",
    "tumhe kisne develop kiya",
    "kisne develop kiya",
]


def is_creator_question(text: str) -> bool:
    normalized = (
        text.lower()
        .strip()
        .replace("?", "")
        .replace("!", "")
        .replace(".", "")
    )

    return any(
        trigger in normalized
        for trigger in CREATOR_TRIGGERS
    )


def creator_answer(text: str) -> str:
    lower = text.lower()

    # Hindi / Hinglish
    hindi_markers = [
        "tum",
        "aap",
        "kisne",
        "banaya",
        "banaye",
        "creator",
        "kaun",
        "develop",
        "kiya",
        "hai",
    ]

    if any(marker in lower for marker in hindi_markers):
        return "Mujhe YADAV BROTHERS ne banaya hai."

    # English
    return "I was created by YADAV BROTHERS."


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    runtime = model_manager.status()
    return {
        "name": "BISNU-X",
        "version": APP_VERSION,
        "status": "online",
        "product_mode": "FREE_CORE",
        "backend": "FastAPI",
        "ai": runtime["ready"],
        "model_runtime": runtime,
        "qwen": settings.qwen_model,
        "llama": settings.llama_model,
        "live_search": settings.live_search_enabled,
    }


# ============================================================
# HEALTH
# ============================================================

def database_status():
    try:
        return db.check_database()
    except db.DatabaseHealthError as exc:
        cause = exc.__cause__
        logger.warning(
            "Database health check failed (%s)",
            type(cause).__name__ if cause is not None else "unknown",
        )
        raise HTTPException(
            status_code=503,
            detail="Persistent database unavailable.",
        ) from exc


@app.get("/health")
def health():
    database = database_status()
    runtime = model_manager.status()
    gateway_configured = (
        runtime["gateway"]["enabled"]
        and runtime["gateway"]["configured"]
    )
    if db.REQUIRE_PERSISTENT_DATABASE and not gateway_configured:
        logger.warning("AI gateway configuration is incomplete.")
        raise HTTPException(
            status_code=503,
            detail="AI gateway is not configured.",
        )
    return {
        "status": "ok",
        "service": "BISNU-X",
        "version": APP_VERSION,
        "product_mode": "FREE_CORE",
        "database": True,
        "database_backend": database["backend"],
        "database_connected": database["connected"],
        "models": runtime,
        "ai_ready": runtime["ready"],
        "gateway_configured": gateway_configured,
        "features": {
            "chat": True,
            "authentication": True,
            "conversations": True,
            "live_search": settings.live_search_enabled,
            "llm_gateway": (
                runtime["gateway"]["enabled"]
                and runtime["gateway"]["configured"]
            ),
            "scanner_upload": True,
            "premium": payments.payments_available(),
            "payments": payments.payments_available(),
            "video_generation": False,
        },
    }


# ============================================================
# API STATUS
# ============================================================

@app.get("/api/status")
def api_status():
    database = database_status()
    runtime = model_manager.status()
    configured_models = model_manager.configured()
    return {
        "status": "online",
        "version": APP_VERSION,
        "product_mode": "FREE_CORE",
        "database_connected": database["connected"],
        "database_backend": database["backend"],

        "models": runtime,

        "configured_models": configured_models,

        "live_search": (
            settings.live_search_enabled
        ),

        "features": {
            "chat": True,
            "qwen": configured_models["qwen"]["enabled"],
            "llama": configured_models["llama"]["enabled"],
            "ai_ready": runtime["ready"],
            "llm_gateway": (
                runtime["gateway"]["enabled"]
                and runtime["gateway"]["configured"]
            ),
            "brain": True,
            "live_search": (
                settings.live_search_enabled
            ),
            "conversations": True,
            "database_backend": (
                "postgresql" if db.DATABASE_URL else "sqlite"
            ),
            "scanner_upload": True,
            "premium": payments.payments_available(),
            "ultra": payments.payments_available(),
            "payments": payments.payments_available(),
            "video_generation": False,
        },

        "creator": "YADAV BROTHERS",
    }


# ============================================================
# USERNAME AND PASSWORD AUTH
# ============================================================

ACCOUNT_ID_SUFFIX = "#bisnu-x.com"


def normalize_account_id(username: str) -> str:
    normalized = username.strip().lower()
    if normalized.endswith(ACCOUNT_ID_SUFFIX):
        local_name = normalized[: -len(ACCOUNT_ID_SUFFIX)]
    else:
        local_name = normalized
    return f"{local_name}{ACCOUNT_ID_SUFFIX}"


@app.post("/v1/auth/register")
def register_user(payload: CredentialsRequest):
    username = normalize_account_id(payload.username)
    password_hash = hash_password(payload.password)
    try:
        user = db.create_password_user(
            username,
            password_hash,
        )
    except db.UsernameTakenError as exc:
        raise HTTPException(
            status_code=409,
            detail="That username is already in use.",
        ) from exc

    return {
        "ok": True,
        "token": create_token(user["id"]),
        "user": public_user(user),
    }


@app.post("/v1/auth/login")
def login_user(payload: LoginRequest):
    requested_username = payload.username.strip().lower()
    username = normalize_account_id(requested_username)
    user = db.get_user_by_username(username)
    if not user and requested_username != username:
        user = db.get_user_by_username(requested_username)
    if not user or not verify_password(
        payload.password,
        user.get("password_hash"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        )

    return {
        "ok": True,
        "token": create_token(user["id"]),
        "user": public_user(user),
    }


@app.put("/v1/auth/credentials")
def link_credentials(
    payload: CredentialsRequest,
    user=Depends(current_user),
):
    try:
        updated = db.set_user_credentials(
            user["id"],
            normalize_account_id(payload.username),
            hash_password(payload.password),
        )
    except db.UsernameTakenError as exc:
        raise HTTPException(
            status_code=409,
            detail="That username is already in use.",
        ) from exc
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="User account not found.",
        )
    profile = db.get_user(user["id"])
    return {"user": public_user(profile)}


@app.get("/v1/auth/me")
def auth_me(
    user=Depends(current_user),
):
    return {
        "user": public_user(dict(user)),
        "product_mode": "FREE_CORE",
    }


@app.post("/v1/auth/logout")
def logout(
    authorization: str | None = Header(
        default=None,
    ),
    user=Depends(current_user),
):
    if (
        authorization
        and authorization.startswith("Bearer ")
    ):
        revoke_token(
            authorization[7:].strip()
        )

    db.audit(
        "logout",
        user["id"],
        None,
    )

    return {
        "ok": True,
    }


# ============================================================
# CONVERSATIONS
# ============================================================

@app.post("/v1/conversations")
def create_conversation(
    payload: ConversationRequest,
    user=Depends(current_user),
):
    conversation_id = (
        db.create_conversation(
            user["id"],
            payload.title,
        )
    )

    db.audit(
        "conversation_created",
        user["id"],
        {"conversation_id": conversation_id},
    )

    return {
        "conversation_id": conversation_id,
        "title": payload.title,
    }


@app.get(
    "/v1/conversations/{conversation_id}"
)
def get_conversation(
    conversation_id: str,
    user=Depends(current_user),
):
    if not db.conversation_owned(
        conversation_id,
        user["id"],
    ):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    rows = db.get_messages(
        conversation_id,
        user["id"],
    )

    return {
        "conversation_id": conversation_id,
        "messages": [
            dict(row)
            for row in rows
        ],
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/v1/chat")
def chat(
    payload: ChatRequest,
    user=Depends(current_user),
):
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    conversation_id = (
        payload.conversation_id
    )

    if conversation_id:
        if not db.conversation_owned(
            conversation_id,
            user["id"],
        ):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

    else:
        conversation_id = (
            db.create_conversation(
                user["id"],
                message[:60],
            )
        )

    history = db.get_messages(
        conversation_id,
        user["id"],
    )

    sources = []
    if payload.use_search:
        try:
            sources = live_search(message)
        except (ImportError, OSError, RuntimeError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Live search is temporarily unavailable.",
            ) from exc

    memories = (
        db.list_user_memories(
            user["id"],
            message,
        )
        if payload.memory_enabled
        else []
    )

    db.save_message(
        conversation_id,
        user["id"],
        "user",
        message,
    )

    # --------------------------------------------------------
    # Deterministic creator identity
    # This prevents the model from inventing another creator.
    # --------------------------------------------------------

    if is_creator_question(message):
        answer = creator_answer(message)

        result = {
            "answer": answer,
            "model": "bisnu-identity",
            "responses": [],
            "evidence": "",
        }

    else:
        try:
            result = brain(
                user_message=message,
                sources=sources,
                requested_model=payload.model,
                history=history,
                memories=memories,
                max_new_tokens=min(
                    payload.max_new_tokens,
                    settings.max_new_tokens,
                ),
            )
        except (ImportError, OSError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail="The requested AI model is unavailable.",
            ) from exc

        answer = result["answer"]

    # Save assistant message
    db.save_message(
        conversation_id,
        user["id"],
        "assistant",
        answer,
        result.get("model"),
    )

    db.audit(
        "chat",
        user["id"],
        {"model": result.get("model", "")},
    )

    return {
        "ok": True,
        "conversation_id": conversation_id,
        "answer": answer,
        "model": result.get("model"),
        "responses": result.get(
            "responses",
            [],
        ),
        "evidence": result.get(
            "evidence",
            "",
        ),
    }


# ============================================================
# SCANNER
# ============================================================

@app.post("/v1/scanner")
async def scanner(
    file: UploadFile = File(...),
    user=Depends(current_user),
):
    payments.require_plan(user["id"], "PREMIUM")
    image_data = await file.read(
        settings.max_upload_mb * 1024 * 1024 + 1,
    )
    try:
        result = save_image(
            str(file.filename or "image"),
            image_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    db.audit(
        "scanner",
        user["id"],
        {"filename": str(file.filename)},
    )

    return result


# ============================================================
# ADMIN MODEL STATUS
# ============================================================

@app.get("/v1/admin/models")
def admin_models(
    x_admin_key: str | None = Header(
        default=None,
    ),
):
    if not admin_allowed(
        x_admin_key
    ):
        raise HTTPException(
            status_code=403,
            detail="Admin access denied.",
        )

    return {
        "runtime": model_manager.status(),
        "configured": model_manager.configured(),
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup():
    print("")
    print("=" * 64)
    print("                 BISNU-X CORE 7.0.0")
    print("=" * 64)

    print(
        "PRODUCT MODE :", 
        "FREE_CORE"
    )

    print(
        "QWEN         :",
        settings.qwen_model,
        settings.qwen_enabled,
    )

    print(
        "LLAMA        :",
        settings.llama_model,
        settings.llama_enabled,
    )

    print(
        "BISNU-1.1    :",
        settings.bisnu_model,
        settings.bisnu_enabled,
    )

    print(
        "LIVE SEARCH  :",
        settings.live_search_enabled,
    )

    print(
        "DATABASE     :",
        settings.database,
    )

    print(
        "PREMIUM      :",
        "AVAILABLE" if payments.payments_available() else "COMING SOON",
    )

    print(
        "PAYMENTS     :",
        "CONFIGURED" if payments.payments_available() else "COMING SOON",
    )

    print(
        "VIDEO        : DISABLED"
    )

    print(
        "CREATOR      : YADAV BROTHERS"
    )

    print("=" * 64)
    print("")
