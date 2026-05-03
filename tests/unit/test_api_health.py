"""Smoke tests for the API layer using TestClient (no real DB needed for health)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked DB and settings."""
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars!!")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
    os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/callback")
    os.environ.setdefault("ALLOWED_GOOGLE_EMAILS", "test@example.com")
    os.environ.setdefault("APP_ENV", "test")

    # Patch build_engine to avoid real DB connection
    mock_factory = MagicMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_session

    with patch(
        "job_agent.infrastructure.persistence.database.build_engine",
        return_value=(mock_factory, mock_factory),
    ):
        from job_agent.interfaces.api.app import create_app
        app = create_app()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_liveness(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_page_renders(client: TestClient) -> None:
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200
    assert "Continue with Google" in resp.text
    assert "Job Agent" in resp.text


def test_dashboard_redirects_to_login(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/auth/login" in resp.headers["location"]
