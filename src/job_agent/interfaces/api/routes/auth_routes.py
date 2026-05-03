from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from job_agent.domain.exceptions import UserNotAllowed
from job_agent.interfaces.api.middleware.auth import _COOKIE_NAME, create_session_cookie

log = structlog.get_logger()
router = APIRouter()


@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html")


@router.get("/auth/go")
async def login_start(request: Request) -> RedirectResponse:
    """Initiates the Google OAuth redirect."""
    oauth = request.app.state.container.oauth
    url, state = oauth.get_authorization_url()
    request.session["oauth_state"] = state
    return RedirectResponse(url)


@router.get("/auth/callback")
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    oauth = request.app.state.container.oauth
    settings = request.app.state.settings

    try:
        user = await oauth.exchange_code(code, state)
    except UserNotAllowed:
        return RedirectResponse("/auth/denied")

    token = create_session_cookie(user.id, settings)
    response = RedirectResponse("/")
    response.set_cookie(
        _COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


@router.get("/auth/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/auth/login")
    response.delete_cookie(_COOKIE_NAME)
    return response


@router.get("/auth/denied", response_class=HTMLResponse)
async def denied() -> HTMLResponse:
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;padding:2rem'>"
        "<h2>Access Denied</h2>"
        "<p>Your email is not in the authorized list. "
        "<a href='/auth/login'>Back to login</a></p></body></html>",
        status_code=403,
    )
