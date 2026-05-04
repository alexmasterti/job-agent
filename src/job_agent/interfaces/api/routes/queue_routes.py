from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from job_agent.config import Settings
from job_agent.interfaces.api.middleware.auth import _COOKIE_NAME, decode_session

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



@router.get("/api/queue/rows", response_model=None)
async def queue_rows(request: Request) -> HTMLResponse:
    """HTMX poll target — returns only the table rows."""
    user_id = _get_user_id(request)
    if not user_id:
        return HTMLResponse("")

    container = request.app.state.container
    applying = await container.application_repo.list_applying(user_id)

    match_scores: dict[uuid.UUID, float] = {}
    for match, *_ in await container.match_repo.list_top(user_id, limit=500):
        match_scores[match.job_id] = match.final_score

    if not applying:
        return HTMLResponse(
            '<tr><td colspan="3" style="padding:2rem;text-align:center;color:var(--text-muted)">'
            'Nothing applying right now. <a href="/applications" style="color:var(--accent-light)">See Applied</a></td></tr>'
        )

    rows = ""
    for app, title, company, location, url in applying:
        score = match_scores.get(app.job_id, 0)
        rows += (
            f'<tr style="border-bottom:1px solid var(--border)">'
            f'<td style="padding:var(--space-3) var(--space-4)">'
            f'<div style="font-weight:600;font-size:14px">{title}</div>'
            f'<div style="font-size:12px;color:var(--text-muted)">{company}'
            + (f' · {location}' if location else '') +
            f'</div></td>'
            f'<td style="padding:var(--space-3) var(--space-4)">'
            f'<span style="font-weight:700;color:var(--accent-light)">{int(score)}</span></td>'
            f'<td style="padding:var(--space-3) var(--space-4)">'
            f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted)">'
            f'<span class="spinner"></span> Tailoring &amp; applying...</span></td>'
            f'</tr>'
        )
    return HTMLResponse(rows)
