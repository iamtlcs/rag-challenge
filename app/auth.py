from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.settings import Settings


COOKIE_NAME = "session"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="rag-challenge-session")


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    return hmac.compare_digest(username, settings.app_username) and hmac.compare_digest(
        password, settings.app_password
    )


def set_session_cookie(response: Response, username: str, settings: Settings) -> None:
    token = _serializer(settings).dumps({"sub": username})
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_max_age_seconds,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def current_user(request: Request, settings: Settings) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = _serializer(settings).loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    username = payload.get("sub") if isinstance(payload, dict) else None
    return str(username) if username else None


def require_user(request: Request, settings: Settings) -> str:
    username = current_user(request, settings)
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    return username
