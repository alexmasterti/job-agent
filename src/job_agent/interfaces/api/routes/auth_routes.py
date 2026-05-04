from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from job_agent.domain.exceptions import UserNotAllowedError
from job_agent.interfaces.api.middleware.auth import _COOKIE_NAME, create_session_cookie

log = structlog.get_logger()
router = APIRouter()


@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html")  # type: ignore[no-any-return]


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

    log.info("oauth.callback.start", state_in_url=state, session_keys=list(request.session.keys()))
    saved_state = request.session.pop("oauth_state", None)
    log.info(
        "oauth.callback.state_check",
        saved=saved_state,
        received=state,
        match=(saved_state == state),
    )
    if not saved_state or saved_state != state:
        log.warning("oauth.state_mismatch", saved=saved_state, received=state)
        return RedirectResponse("/auth/login")

    log.info("oauth.callback.exchanging_code")
    try:
        user = await oauth.exchange_code(code)
        log.info("oauth.callback.exchange_ok", user_id=str(user.id), email=user.email)
    except UserNotAllowedError as exc:
        log.warning("oauth.callback.not_allowed", error=str(exc))
        return RedirectResponse("/auth/denied")
    except Exception as exc:
        log.error(
            "oauth.callback_error", error=str(exc), error_type=type(exc).__name__, exc_info=True
        )
        return RedirectResponse("/auth/login")

    token = create_session_cookie(user.id, settings)
    response = RedirectResponse("/?toast_msg=Welcome+back!&toast_type=success")
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
