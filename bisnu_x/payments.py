from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import httpx

from bisnu_x.config import settings


RAZORPAY_API = "https://api.razorpay.com/v1"

PREMIUM_AMOUNT = 39900
PREMIUM_DAYS = 30
PREMIUM_CURRENCY = "INR"


def payments_available() -> bool:
    """
    True only when the server has the credentials required
    to create and verify Razorpay Payment Links.
    """
    return bool(
        getattr(settings, "razorpay_key_id", "")
        and getattr(settings, "razorpay_key_secret", "")
        and getattr(settings, "razorpay_webhook_secret", "")
    )


def require_payment_configuration() -> None:
    missing = []

    if not getattr(settings, "razorpay_key_id", ""):
        missing.append("RAZORPAY_KEY_ID")

    if not getattr(settings, "razorpay_key_secret", ""):
        missing.append("RAZORPAY_KEY_SECRET")

    if not getattr(settings, "razorpay_webhook_secret", ""):
        missing.append("RAZORPAY_WEBHOOK_SECRET")

    if missing:
        raise RuntimeError(
            "Razorpay configuration missing: " + ", ".join(missing)
        )


def _require_razorpay() -> tuple[str, str]:
    require_payment_configuration()

    return (
        str(settings.razorpay_key_id),
        str(settings.razorpay_key_secret),
    )


def _provider_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key_id, key_secret = _require_razorpay()

    url = f"{RAZORPAY_API}/{path.lstrip('/')}"

    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            method.upper(),
            url,
            auth=(key_id, key_secret),
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    try:
        data = response.json()
    except Exception:
        data = {
            "error": response.text,
        }

    if response.status_code >= 400:
        raise RuntimeError(
            f"Razorpay API error {response.status_code}: {data}"
        )

    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Razorpay API response")

    return data


def create_premium_payment_link(
    user_id: str,
    email: str | None = None,
    name: str | None = None,
    contact: str | None = None,
) -> dict[str, Any]:
    """
    Creates a unique Razorpay Payment Link for the authenticated BISNU-X user.

    Price:
        ₹399

    Validity after successful payment:
        30 days

    IMPORTANT:
    The Razorpay secret is used only on the backend.
    """

    require_payment_configuration()

    if not user_id:
        raise ValueError("user_id is required")

    # Razorpay reference_id has a max length of 40 characters.
    reference_id = (
        f"BISNUX-{str(user_id)[:20]}-{uuid.uuid4().hex[:10]}"
    )[:40]

    notes = {
        "product": "BISNU-X Premium",
        "user_id": str(user_id)[:256],
        "plan": "premium",
        "days": str(PREMIUM_DAYS),
    }

    payload: dict[str, Any] = {
        "amount": PREMIUM_AMOUNT,
        "currency": PREMIUM_CURRENCY,
        "accept_partial": False,
        "reference_id": reference_id,
        "description": "BISNU-X Premium - 30 Days",
        "reminder_enable": False,
        "notes": notes,
    }

    customer: dict[str, str] = {}

    if name:
        customer["name"] = str(name)[:100]

    if email:
        customer["email"] = str(email)[:100]

    if contact:
        customer["contact"] = str(contact)[:20]

    if customer:
        payload["customer"] = customer

    result = _provider_request(
        "POST",
        "/payment_links",
        payload,
    )

    payment_url = result.get("short_url")

    if not payment_url:
        raise RuntimeError(
            "Razorpay did not return a Payment Link URL"
        )

    return {
        "success": True,
        "payment_url": payment_url,
        "short_url": payment_url,
        "payment_link_id": result.get("id"),
        "reference_id": result.get("reference_id", reference_id),
        "amount": PREMIUM_AMOUNT,
        "currency": PREMIUM_CURRENCY,
        "days": PREMIUM_DAYS,
        "status": result.get("status"),
    }


def fetch_payment_link(payment_link_id: str) -> dict[str, Any]:
    """
    Fetch a Payment Link from Razorpay.
    """

    if not payment_link_id:
        raise ValueError("payment_link_id is required")

    return _provider_request(
        "GET",
        f"/payment_links/{payment_link_id}",
    )


def cancel_payment_link(payment_link_id: str) -> dict[str, Any]:
    """
    Cancel an unpaid Payment Link.
    """

    if not payment_link_id:
        raise ValueError("payment_link_id is required")

    return _provider_request(
        "POST",
        f"/payment_links/{payment_link_id}/cancel",
    )


def verify_webhook_signature(
    raw_body: bytes,
    signature: str,
) -> bool:
    """
    Verify Razorpay webhook signature using HMAC SHA256.
    """

    secret = getattr(
        settings,
        "razorpay_webhook_secret",
        "",
    )

    if not secret:
        return False

    if not signature:
        return False

    expected = hmac.new(
        str(secret).encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected,
        signature,
    )


def process_razorpay_webhook(
    raw_body: bytes,
    signature: str,
) -> dict[str, Any]:
    """
    Verifies and parses a Razorpay webhook.

    Supported important event:
        payment_link.paid

    The caller is responsible for updating the application's
    user subscription/premium record transactionally.
    """

    if not verify_webhook_signature(
        raw_body,
        signature,
    ):
        raise ValueError("Invalid Razorpay webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid webhook JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid webhook payload")

    event = payload.get("event")

    if event != "payment_link.paid":
        return {
            "success": True,
            "handled": False,
            "event": event,
        }

    entity = (
        payload
        .get("payload", {})
        .get("payment_link", {})
        .get("entity", {})
    )

    if not isinstance(entity, dict):
        raise ValueError("Invalid payment_link entity")

    payment_link_id = entity.get("id")
    status = entity.get("status")
    amount = entity.get("amount")
    amount_paid = entity.get("amount_paid")
    currency = entity.get("currency")
    reference_id = entity.get("reference_id")
    notes = entity.get("notes") or {}
    payments = entity.get("payments") or []

    if status != "paid":
        raise ValueError(
            f"Payment Link is not paid: {status}"
        )

    if int(amount or 0) != PREMIUM_AMOUNT:
        raise ValueError(
            f"Invalid payment amount: {amount}"
        )

    if int(amount_paid or 0) < PREMIUM_AMOUNT:
        raise ValueError(
            f"Insufficient paid amount: {amount_paid}"
        )

    if str(currency).upper() != PREMIUM_CURRENCY:
        raise ValueError(
            f"Invalid currency: {currency}"
        )

    user_id = notes.get("user_id")

    if not user_id:
        raise ValueError(
            "Payment Link does not contain BISNU-X user_id"
        )

    captured_payment = None

    for payment in payments:
        if not isinstance(payment, dict):
            continue

        payment_status = str(
            payment.get("status", "")
        ).lower()

        if payment_status == "captured":
            captured_payment = payment
            break

    if payments and captured_payment is None:
        raise ValueError(
            "No captured Razorpay payment found"
        )

    payment_id = None

    if captured_payment:
        payment_id = (
            captured_payment.get("payment_id")
            or captured_payment.get("id")
        )

    return {
        "success": True,
        "handled": True,
        "event": event,
        "user_id": str(user_id),
        "payment_link_id": payment_link_id,
        "payment_id": payment_id,
        "reference_id": reference_id,
        "amount": PREMIUM_AMOUNT,
        "currency": PREMIUM_CURRENCY,
        "days": PREMIUM_DAYS,
        "paid": True,
        "notes": notes,
    }


def premium_expiry_timestamp(
    now: int | None = None,
) -> int:
    """
    Returns Unix timestamp for 30-day Premium expiry.
    """

    if now is None:
        now = int(time.time())

    return now + (
        PREMIUM_DAYS * 24 * 60 * 60
    )


# ---------------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------------
#
# The old project used recurring Razorpay subscriptions.
# These functions intentionally remain available so old imports do not
# immediately break. New Premium flow MUST use create_premium_payment_link.
# ---------------------------------------------------------------------


def require_plan(plan: str) -> str:
    normalized = str(plan).strip().upper()

    if normalized not in {"PREMIUM", "ULTRA"}:
        raise ValueError(
            f"Unsupported legacy plan: {plan}"
        )

    return normalized


def create_subscription(
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    raise RuntimeError(
        "Recurring subscriptions are disabled. "
        "Use create_premium_payment_link() for "
        "BISNU-X Premium ₹399 / 30 days."
    )


def cancel_subscription(
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    raise RuntimeError(
        "Recurring subscriptions are disabled for BISNU-X Premium."
    )
