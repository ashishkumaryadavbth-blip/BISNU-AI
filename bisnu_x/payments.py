from __future__ import annotations

import hashlib
import hmac
import math
import time
from typing import Any

import requests
from fastapi import HTTPException

from bisnu_x import db
from bisnu_x.config import settings
from bisnu_x.db import get_user, set_plan


PLAN_IDS = {
    "PREMIUM": settings.razorpay_premium_plan_id,
    "ULTRA": settings.razorpay_ultra_plan_id,
}

PLANS = {
    "FREE": {
        "id": "FREE",
        "currency": "INR",
        "scanner": False,
        "video": False,
        "available": True,
    },
    "PREMIUM": {
        "id": "PREMIUM",
        "currency": "INR",
        "scanner": True,
        "video": False,
        "available": bool(settings.razorpay_premium_plan_id),
    },
    "ULTRA": {
        "id": "ULTRA",
        "currency": "INR",
        "scanner": True,
        "video": False,
        "available": bool(settings.razorpay_ultra_plan_id),
    },
}

CANCELLED_EVENTS = {"subscription.cancelled", "subscription.completed"}
PAUSED_EVENTS = {"subscription.halted", "subscription.paused"}
PLAN_LEVELS = {"FREE": 0, "PREMIUM": 1, "ULTRA": 2}

def qr_file_path() -> Path:
    configured = str(getattr(settings, "payment_qr_path", "") or "").strip()
    path = Path(configured)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def qr_configured() -> bool:
    path = qr_file_path()
    return path.is_file() and path.stat().st_size > 0


def gateway_configured() -> bool:
    return bool(
        settings.razorpay_key_id
        and settings.razorpay_key_secret
        and settings.razorpay_webhook_secret
    )


def plan_available(plan: str) -> bool:
    plan = plan.upper()
    if plan == "PREMIUM":
        return gateway_configured() and qr_configured() and bool(settings.razorpay_premium_plan_id)
    if plan == "ULTRA":
        return gateway_configured() and qr_configured() and bool(settings.razorpay_ultra_plan_id)
    return True


def payment_status() -> dict[str, Any]:
    return {
        "gateway_configured": gateway_configured(),
        "qr_configured": qr_configured(),
        "premium_available": plan_available("PREMIUM"),
        "ultra_available": plan_available("ULTRA"),
        "premium_plan_configured": bool(settings.razorpay_premium_plan_id),
        "ultra_plan_configured": bool(settings.razorpay_ultra_plan_id),
        "qr_path": str(qr_file_path().relative_to(settings.project_root))
        if qr_file_path().is_relative_to(settings.project_root)
        else "configured",
    }


def entitlement(user_id: str) -> dict[str, Any]:
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    current = str(user.get("plan", "FREE")).upper()
    expiry = user.get("plan_expires")
    try:
        expiry_value = float(expiry) if expiry is not None else None
    except (TypeError, ValueError, OverflowError):
        expiry_value = None
    active = current == "FREE" or (
        expiry_value is not None and math.isfinite(expiry_value) and expiry_value > time.time()
    )
    if current != "FREE" and not active:
        set_plan(user_id, "FREE", None)
        current = "FREE"
        expiry_value = None
    sub = db.get_user_subscription(user_id)
    return {
        "plan": current,
        "plan_expires": expiry_value,
        "subscription": sub,
        "premium": current in {"PREMIUM", "ULTRA"},
        "ultra": current == "ULTRA",
    }



def _require_razorpay(*, webhook: bool = False) -> None:
    required = [
        settings.razorpay_key_id,
        settings.razorpay_key_secret,
    ]
    if webhook:
        required.append(settings.razorpay_webhook_secret)

    if not all(required):
        raise HTTPException(
            status_code=503,
            detail=(
                "Razorpay is not configured. Set the server-side "
                "Razorpay keys and webhook secret."
            ),
        )


def require_plan(user_id: str, required_plan: str) -> dict[str, Any]:
    required = required_plan.upper()
    if required not in PLAN_LEVELS:
        raise ValueError("Unknown subscription plan.")

    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    current_plan = str(user.get("plan", "FREE")).upper()
    expiry = user.get("plan_expires")
    try:
        expiry_value = float(expiry) if expiry is not None else None
    except (TypeError, ValueError, OverflowError):
        expiry_value = None
    if (
        current_plan != "FREE"
        and (
            expiry_value is None
            or not math.isfinite(expiry_value)
            or expiry_value <= time.time()
        )
    ):
        set_plan(user_id, "FREE", None)
        current_plan = "FREE"

    if PLAN_LEVELS.get(current_plan, 0) < PLAN_LEVELS[required]:
        raise HTTPException(
            status_code=403,
            detail=f"An active {required} plan is required.",
        )
    return user


def _provider_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_razorpay()
    try:
        response = requests.request(
            method,
            f"https://api.razorpay.com/v1/{path.lstrip('/')}",
            json=payload,
            auth=(
                settings.razorpay_key_id,
                settings.razorpay_key_secret,
            ),
            timeout=(5, 20),
        )
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="Razorpay request failed; subscription was not activated.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Razorpay returned an invalid response.",
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=502,
            detail="Razorpay returned an invalid response.",
        )
    return result


def create_subscription(user_id: str, plan: str) -> dict[str, Any]:
    plan = plan.upper()
    if plan not in PLAN_IDS:
        raise HTTPException(
            status_code=400,
            detail="Choose a paid subscription plan.",
        )

    provider_plan_id = PLAN_IDS[plan]
    if not provider_plan_id:
        raise HTTPException(
            status_code=503,
            detail=(
                f"The Razorpay {plan} recurring plan is not configured. "
                "Create the monthly plan in Razorpay and set its server-side plan ID."
            ),
        )
    if settings.razorpay_subscription_total_count < 1:
        raise HTTPException(
            status_code=503,
            detail="Razorpay subscription cycle count is invalid.",
        )
    if not get_user(user_id):
        raise HTTPException(status_code=401, detail="User not found.")

    provider_plan = _provider_request(
        "GET",
        f"plans/{provider_plan_id}",
    )
    item = provider_plan.get("item")
    interval = provider_plan.get("interval")
    if (
        provider_plan.get("id") != provider_plan_id
        or provider_plan.get("period") != "monthly"
        or not isinstance(interval, int)
        or isinstance(interval, bool)
        or interval != 1
        or not isinstance(item, dict)
        or item.get("currency") != "INR"
        or not isinstance(item.get("amount"), int)
        or isinstance(item.get("amount"), bool)
        or item["amount"] <= 0
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "The configured Razorpay plan must be an active monthly "
                "INR plan with a positive amount."
            ),
        )

    subscription = _provider_request(
        "POST",
        "subscriptions",
        payload={
            "plan_id": provider_plan_id,
            "total_count": settings.razorpay_subscription_total_count,
            "quantity": 1,
            "customer_notify": 1,
            "notes": {
                "bisnu_user_id": user_id,
                "bisnu_plan": plan,
            },
        },
    )

    subscription_id = subscription.get("id")
    checkout_url = subscription.get("short_url")
    if (
        not isinstance(subscription_id, str)
        or not subscription_id.startswith("sub_")
        or not isinstance(checkout_url, str)
        or not checkout_url.startswith("https://")
    ):
        raise HTTPException(
            status_code=502,
            detail="Razorpay did not return a valid subscription checkout.",
        )

    db.create_subscription(
        user_id,
        subscription_id,
        provider_plan_id,
        plan,
        str(subscription.get("status", "created")),
        item["amount"],
        item["currency"],
    )
    return {
        "subscription_id": subscription_id,
        "plan": plan,
        "status": str(subscription.get("status", "created")),
        "checkout_url": checkout_url,
    }


def cancel_subscription(user_id: str) -> dict[str, Any]:
    subscription = db.get_user_subscription(user_id)
    if not subscription:
        raise HTTPException(
            status_code=404,
            detail="No Razorpay subscription was found.",
        )
    if subscription["status"] in CANCELLED_EVENTS | {"cancelled", "completed"}:
        return {
            "ok": True,
            "status": subscription["status"],
            "current_end": subscription["current_end"],
        }

    result = _provider_request(
        "POST",
        f"subscriptions/{subscription['provider_subscription_id']}/cancel",
        payload={"cancel_at_cycle_end": 1},
    )
    status = str(result.get("status", ""))
    if status not in {"active", "cancelled", "completed"}:
        raise HTTPException(
            status_code=502,
            detail="Razorpay did not confirm the cancellation request.",
        )
    return {
        "ok": True,
        "status": status,
        "message": "Cancellation is scheduled with Razorpay.",
    }


def verify_webhook_signature(
    raw_body: bytes,
    signature: str | None,
) -> None:
    if not settings.razorpay_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Razorpay webhook secret is not configured.",
        )
    if not signature:
        raise HTTPException(
            status_code=401,
            detail="Missing Razorpay signature.",
        )

    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise HTTPException(
            status_code=401,
            detail="Invalid Razorpay signature.",
        )


def process_razorpay_webhook(
    payload: dict[str, Any],
    raw_body: bytes,
    signature: str | None,
    event_id: str | None,
) -> dict[str, Any]:
    verify_webhook_signature(raw_body, signature)
    if not event_id:
        raise HTTPException(
            status_code=400,
            detail="Missing Razorpay event ID.",
        )
    if db.webhook_event_exists(event_id):
        return {"ok": True, "idempotent": True}

    event = payload.get("event")
    if not isinstance(event, str):
        raise HTTPException(
            status_code=400,
            detail="Razorpay event name is missing.",
        )
    entities = payload.get("payload")
    subscription_payload = (
        entities.get("subscription")
        if isinstance(entities, dict)
        else None
    )
    sub = (
        subscription_payload.get("entity")
        if isinstance(subscription_payload, dict)
        else None
    )
    if not isinstance(sub, dict):
        raise HTTPException(
            status_code=400,
            detail="Razorpay subscription entity is missing.",
        )

    provider_id = sub.get("id")
    if not isinstance(provider_id, str):
        raise HTTPException(
            status_code=400,
            detail="Razorpay subscription ID is missing.",
        )
    stored = db.get_subscription(provider_id)
    if not stored:
        raise HTTPException(
            status_code=404,
            detail="Subscription was not created by this BISNU-X server.",
        )
    if sub.get("plan_id") != stored["provider_plan_id"]:
        raise HTTPException(
            status_code=400,
            detail="Razorpay subscription plan does not match the server record.",
        )

    status = str(sub.get("status", "")).lower()
    current_end_raw = sub.get("current_end")
    current_end = None
    if isinstance(current_end_raw, (int, float)) and not isinstance(
        current_end_raw, bool
    ):
        try:
            candidate = float(current_end_raw)
        except OverflowError:
            candidate = math.inf
        if math.isfinite(candidate):
            current_end = candidate

    if event == "subscription.activated":
        if status != "active":
            raise HTTPException(
                status_code=400,
                detail="Razorpay has not activated this subscription.",
            )
        update_status = "authorized"
    elif event == "subscription.charged":
        if status != "active":
            raise HTTPException(
                status_code=400,
                detail="Razorpay has not activated this subscription.",
            )
        if current_end is None or current_end <= time.time():
            raise HTTPException(
                status_code=400,
                detail="Razorpay subscription has no valid paid-through date.",
            )
        update_status = "active"
    elif event in CANCELLED_EVENTS:
        update_status = str(event).split(".")[-1]
    elif event in PAUSED_EVENTS:
        update_status = str(event).split(".")[-1]
    else:
        db.record_webhook_event(event_id)
        return {"ok": True, "ignored": True}

    payment_payload = (
        entities.get("payment")
        if isinstance(entities, dict)
        else None
    )
    payment = (
        payment_payload.get("entity")
        if isinstance(payment_payload, dict)
        else None
    )
    payment_record = None
    if event == "subscription.charged":
        if (
            not isinstance(payment, dict)
            or payment.get("status") != "captured"
        ):
            raise HTTPException(
                status_code=400,
                detail="Razorpay did not provide a valid captured subscription payment.",
            )
        payment_id = payment.get("id")
        amount = payment.get("amount")
        currency = payment.get("currency")
        if (
            not isinstance(payment_id, str)
            or not payment_id.startswith("pay_")
            or not isinstance(amount, int)
            or isinstance(amount, bool)
            or amount <= 0
            or amount != stored["expected_amount"]
            or currency != stored["currency"]
        ):
            raise HTTPException(
                status_code=400,
                detail="Razorpay payment does not match the server-verified plan amount.",
            )
        payment_record = (
            payment_id,
            stored["plan"],
            amount,
            currency,
        )

    applied = db.apply_subscription_webhook(
        event_id,
        provider_id,
        update_status,
        current_end,
        payment_record,
    )
    if applied is None:
        raise HTTPException(
            status_code=404,
            detail="Subscription was not created by this BISNU-X server.",
        )
    if applied["duplicate"]:
        return {"ok": True, "idempotent": True}
    if not applied.get("payment_valid", True):
        raise HTTPException(
            status_code=400,
            detail="Razorpay payment does not match the server-verified plan amount.",
        )
    return {
        "ok": True,
        "subscription_id": provider_id,
        "status": applied["status"],
    }

