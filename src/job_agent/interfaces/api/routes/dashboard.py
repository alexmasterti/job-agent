from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from job_agent.interfaces.api.middleware.auth import decode_session, _COOKIE_NAME
from job_agent.config import Settings

router = APIRouter()


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _get_user_id(request: Request) -> uuid.UUID | None:
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        return None
    try:
        settings: Settings = request.app.state.settings
        data = decode_session(token, settings)
        return uuid.UUID(data["user_id"])
    except Exception:
        return None


@router.get("/", response_model=None)
async def dashboard(request: Request) -> HTMLResponse | RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login")

    container = request.app.state.container
    user = await container.user_repo.get_by_id(user_id)
    if not user:
        return RedirectResponse("/auth/login")

    profile = await container.profile_repo.get_by_user(user_id)
    today_spend = await container.llm_call_repo.today_spend(user_id)

    return _templates(request).TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "profile": profile,
            "today_spend": round(today_spend, 4),
            "daily_budget": container.settings.llm_daily_budget_usd,
        },
    )
