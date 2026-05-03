"""Session cookie auth middleware. Reads JWT from HTTP-only cookie."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Cookie, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from job_agent.config import Settings

_COOKIE_NAME = "session"
_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days


def make_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="session")


def create_session_cookie(user_id: uuid.UUID, settings: Settings) -> str:
    s = make_serializer(settings)
    return s.dumps({"user_id": str(user_id)})


def decode_session(token: str, settings: Settings) -> dict[str, Any]:
    s = make_serializer(settings)
    data: dict[str, Any] = s.loads(token, max_age=_MAX_AGE_SECONDS)
    return data


def get_current_user_id(request: Request) -> uuid.UUID:
    """FastAPI dependency — resolves the authenticated user_id from the session cookie.

    Raises 401 if the cookie is missing or invalid.
    """
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        settings: Settings = request.app.state.settings
        data = decode_session(token, settings)
        return uuid.UUID(data["user_id"])
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
