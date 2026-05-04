from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from job_agent.interfaces.api.middleware.auth import _COOKIE_NAME, decode_session

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

    from job_agent.config import Settings

router = APIRouter()


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates  # type: ignore[no-any-return]


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
    jobs_count = await container.job_repo.count_by_user(user_id)
    matches_count = await container.match_repo.count_by_user(user_id)
    app_counts = await container.application_repo.counts(user_id)

    return _templates(request).TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "profile": profile,
            "today_spend": round(today_spend, 4),
            "daily_budget": container.settings.llm_daily_budget_usd,
            "jobs_count": jobs_count,
            "matches_count": matches_count,
            "app_counts": app_counts,
        },
    )
