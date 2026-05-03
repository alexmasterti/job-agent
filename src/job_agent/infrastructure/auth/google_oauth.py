"""Google OAuth 2.0 integration via Authlib."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client

from job_agent.config import Settings
from job_agent.domain.exceptions import UserNotAllowed
from job_agent.domain.models.user import User, UserTier
from job_agent.infrastructure.persistence.repositories.user_repo import UserRepository

log = structlog.get_logger()

_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthAdapter:
    """Handles the Google OAuth flow and maps the resulting identity to a User row."""

    def __init__(self, settings: Settings, user_repo: UserRepository) -> None:
        self._settings = settings
        self._user_repo = user_repo

    def build_client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self._settings.google_client_id,
            client_secret=self._settings.google_client_secret,
            redirect_uri=self._settings.google_redirect_uri,
            scope="openid email profile",
        )

    def get_authorization_url(self) -> tuple[str, str]:
        """Return (authorization_url, state) to redirect the user to."""
        client = self.build_client()
        url, state = client.create_authorization_url(
            _GOOGLE_AUTHORIZE_URL,
            access_type="offline",
            prompt="consent",
        )
        return str(url), str(state)

    async def exchange_code(self, code: str, state: str) -> User:
        """Exchange the OAuth callback code for a user identity.

        Raises UserNotAllowed if the email is not in ALLOWED_GOOGLE_EMAILS.
        Creates or updates the user row on success.
        """
        async with self.build_client() as client:
            token = await client.fetch_token(
                _GOOGLE_TOKEN_URL,
                code=code,
                state=state,
            )
            resp = await client.get(_GOOGLE_USERINFO_URL, token=token)
            resp.raise_for_status()
            info: dict[str, Any] = resp.json()

        email: str = info.get("email", "").lower()
        google_sub: str = info.get("sub", "")

        if email not in self._settings.allowed_emails:
            log.warning("oauth.not_allowed", email=email)
            raise UserNotAllowed(f"Email not in allowlist: {email}")

        existing = await self._user_repo.get_by_google_sub(google_sub)
        user = User(
            id=existing.id if existing else uuid.uuid4(),
            email=email,
            google_sub=google_sub,
            tier=existing.tier if existing else UserTier.pro,
            is_active=True,
            created_at=existing.created_at if existing else datetime.now(timezone.utc),
        )
        saved = await self._user_repo.upsert(user)
        log.info("oauth.login", user_id=str(saved.id), email=email)
        return saved
