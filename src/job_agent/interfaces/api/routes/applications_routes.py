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


@router.get("/applications-old", response_model=None)
async def applications_page(request: Request) -> HTMLResponse | RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login")

    container = request.app.state.container
    user = await container.user_repo.get_by_id(user_id)
    if not user:
        return RedirectResponse("/auth/login")

    applied = await container.application_repo.list_applied(user_id)

    match_scores: dict[uuid.UUID, float] = {}
    for match, *_ in await container.match_repo.list_top(user_id, limit=500):
        match_scores[match.job_id] = match.final_score

    return _templates(request).TemplateResponse(
        request,
        "applications.html",
        {
            "user": user,
            "applied": applied,
            "match_scores": match_scores,
        },
    )
