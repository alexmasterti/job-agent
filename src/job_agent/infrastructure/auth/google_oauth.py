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

    async def exchange_code(self, code: str) -> User:
        """Exchange the OAuth callback code for a user identity.

        Raises UserNotAllowed if the email is not in ALLOWED_GOOGLE_EMAILS.
        Creates or updates the user row on success.
        """
        log.info("oauth.fetch_token.start")
        async with self.build_client() as client:
            await client.fetch_token(_GOOGLE_TOKEN_URL, code=code)
            log.info("oauth.fetch_token.done")
            resp = await client.get(_GOOGLE_USERINFO_URL)
            log.info("oauth.userinfo.done", status=resp.status_code)
            resp.raise_for_status()
            info: dict[str, Any] = resp.json()
            log.info("oauth.userinfo.parsed", keys=list(info.keys()))

        email: str = info.get("email", "").lower()
        google_sub: str = info.get("sub", "")
        log.info("oauth.identity", email=email, has_sub=bool(google_sub))

        if email not in self._settings.allowed_emails:
            log.warning("oauth.not_allowed", email=email, allowed=self._settings.allowed_emails)
            raise UserNotAllowed(f"Email not in allowlist: {email}")

        log.info("oauth.db.lookup_start")
        existing = await self._user_repo.get_by_google_sub(google_sub)
        log.info("oauth.db.lookup_done", found=existing is not None)
        user = User(
            id=existing.id if existing else uuid.uuid4(),
            email=email,
            google_sub=google_sub,
            tier=existing.tier if existing else UserTier.pro,
            is_active=True,
            created_at=existing.created_at if existing else datetime.now(timezone.utc),
        )
        log.info("oauth.db.upsert_start")
        saved = await self._user_repo.upsert(user)
        log.info("oauth.login", user_id=str(saved.id), email=email)
        return saved
