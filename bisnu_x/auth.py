from __future__ import annotations

from fastapi import HTTPException

from bisnu_x.config import settings
from bisnu_x.db import get_or_create_user
from bisnu_x.security import create_token


def google_login(
    id_token: str
):
    if not settings.google_client_id:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google Login is not configured. "
                "Set GOOGLE_CLIENT_ID in .env."
            )
        )

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests

        info = google_id_token.verify_oauth2_token(
            id_token,
            requests.Request(),
            settings.google_client_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid Google ID token."
        ) from exc

    email = info.get("email")

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Google account email unavailable."
        )

    if info.get("email_verified") is not True:
        raise HTTPException(
            status_code=401,
            detail="Google account email is not verified.",
        )

    user = get_or_create_user(
        email=email,
        name=info.get("name"),
        picture=info.get("picture")
    )

    token = create_token(
        user["id"]
    )

    return {
        "ok": True,
        "token": token,
        "user": user
    }
