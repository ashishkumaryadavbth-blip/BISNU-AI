from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
import time

import jwt
from fastapi import Depends, Header, HTTPException

from bisnu_x.config import settings
from bisnu_x.db import (
    get_user,
    revoke_token_hash,
    is_token_revoked
)


ALGORITHM = "HS256"
PASSWORD_SCRYPT_N = 2**14
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1
PASSWORD_SALT_BYTES = 16
PASSWORD_HASH_BYTES = 64


def public_user(user: dict) -> dict:
    return {
        key: value
        for key, value in user.items()
        if key != "password_hash"
    }


def hash_password(password: str) -> str:
    if len(password) < 10 or len(password) > 128:
        raise ValueError("Password must be between 10 and 128 characters.")
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=PASSWORD_SCRYPT_R,
        p=PASSWORD_SCRYPT_P,
        dklen=PASSWORD_HASH_BYTES,
    )
    return "$".join(
        (
            "scrypt",
            str(PASSWORD_SCRYPT_N),
            str(PASSWORD_SCRYPT_R),
            str(PASSWORD_SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(derived).decode("ascii"),
        )
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not isinstance(stored_hash, str) or not stored_hash:
        return False
    parts = stored_hash.split("$")
    if len(parts) != 6:
        return False
    algorithm, n_value, r_value, p_value, salt_value, digest_value = parts
    if (algorithm, n_value, r_value, p_value) != (
        "scrypt",
        str(PASSWORD_SCRYPT_N),
        str(PASSWORD_SCRYPT_R),
        str(PASSWORD_SCRYPT_P),
    ):
        return False
    try:
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=PASSWORD_SCRYPT_N,
            r=PASSWORD_SCRYPT_R,
            p=PASSWORD_SCRYPT_P,
            dklen=PASSWORD_HASH_BYTES,
        )
    except (UnicodeEncodeError, ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def secret_key():
    if settings.jwt_secret:
        if len(settings.jwt_secret.encode("utf-8")) < 32:
            raise HTTPException(
                status_code=503,
                detail="BISNU_JWT_SECRET must contain at least 32 bytes.",
            )
        return settings.jwt_secret

    raise HTTPException(
        status_code=503,
        detail="Authentication is not configured. Set BISNU_JWT_SECRET.",
    )


def create_token(user_id: str):
    now = int(time.time())

    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + (
            settings.jwt_expire_hours * 3600
        )
    }

    return jwt.encode(
        payload,
        secret_key(),
        algorithm=ALGORITHM
    )


def token_hash(token: str):
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def decode_token(token: str):
    return jwt.decode(
        token,
        secret_key(),
        algorithms=[ALGORITHM]
    )


def current_user(
    authorization: str | None = Header(
        default=None
    )
):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization required."
        )

    if not authorization.lower().startswith(
        "bearer "
    ):
        raise HTTPException(
            status_code=401,
            detail="Bearer token required."
        )

    token = authorization[7:].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid token."
        )

    if is_token_revoked(
        token_hash(token)
    ):
        raise HTTPException(
            status_code=401,
            detail="Token revoked."
        )

    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token."
        ) from None

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token."
        )

    user = get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found."
        )

    # Expired premium/ultra automatically falls back.
    plan = user.get("plan")
    expires_at = user.get("plan_expires")
    try:
        expiry = float(expires_at) if expires_at is not None else None
    except (TypeError, ValueError, OverflowError):
        expiry = None
    if (
        plan in {"PREMIUM", "ULTRA"}
        and (
            expiry is None
            or not math.isfinite(expiry)
            or expiry <= time.time()
        )
    ):
        from bisnu_x.db import set_plan

        set_plan(
            user["id"],
            "FREE",
            None
        )

        user = get_user(
            user["id"]
        )

    return user


def revoke_token(
    token: str
):
    try:
        payload = decode_token(token)
        exp = float(
            payload.get(
                "exp",
                time.time()
            )
        )
    except Exception:
        exp = time.time() + 3600

    revoke_token_hash(
        token_hash(token),
        exp
    )


def admin_allowed(
    provided: str | None
):
    if not settings.admin_key:
        return False

    if not provided:
        return False

    return secrets.compare_digest(
        provided,
        settings.admin_key
    )
