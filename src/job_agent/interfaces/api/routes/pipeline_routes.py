"""Dashboard-triggered discover + match pipeline with live progress."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from job_agent.interfaces.api.middleware.auth import _COOKIE_NAME, decode_session

if TYPE_CHECKING:
    from job_agent.composition_root import Container
    from job_agent.config import Settings

router = APIRouter()

# ── In-memory pipeline state (per user) ─────────────────────────────────────

_STAGE_IDLE = "idle"
_STAGE_DISCOVERING = "discovering"
_STAGE_MATCHING = "matching"
_STAGE_DONE = "done"
_STAGE_ERROR = "error"


@dataclass
class PipelineState:
    stage: str = _STAGE_IDLE
    started_at: datetime | None = None
    keyword: str = ""
    source: str = "all"
    # Discovery progress
    discovered: int = 0
    new_jobs: int = 0
    skipped_jobs: int = 0
    # Matching progress
    scored: int = 0
    saved: int = 0
    filtered: int = 0
    skipped_low_embedding: int = 0
    # Completion
    error: str = ""
    finished_at: datetime | None = None


# keyed by user_id
_pipeline_states: dict[uuid.UUID, PipelineState] = {}
_pipeline_locks: dict[uuid.UUID, bool] = {}


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


@router.post("/api/pipeline/run", response_model=None)
async def run_pipeline(request: Request) -> HTMLResponse | RedirectResponse:
    """Kick off discover + match in the background."""
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login", status_code=303)

    # Don't allow concurrent runs for the same user
    if _pipeline_locks.get(user_id):
        return HTMLResponse(_render_progress(_pipeline_states.get(user_id, PipelineState())))

    form = await request.form()
    keyword = str(form.get("keyword", "software engineer")).strip() or "software engineer"
    source = str(form.get("source", "all")).strip() or "all"

    state = PipelineState(
        stage=_STAGE_DISCOVERING,
        started_at=datetime.now(UTC),
        keyword=keyword,
        source=source,
    )
    _pipeline_states[user_id] = state
    _pipeline_locks[user_id] = True

    container = request.app.state.container
    asyncio.create_task(_run_pipeline(user_id, container, state))

    return HTMLResponse(_render_progress(state))


@router.get("/api/pipeline/status", response_model=None)
async def pipeline_status(request: Request) -> HTMLResponse:
    """HTMX poll target — returns current pipeline progress HTML."""
    user_id = _get_user_id(request)
    if not user_id:
        return HTMLResponse("")

    state = _pipeline_states.get(user_id, PipelineState())
    html = _render_progress(state)

    # If done or error, stop polling (no hx-trigger)
    if state.stage in (_STAGE_DONE, _STAGE_ERROR):
        _pipeline_locks.pop(user_id, None)

    return HTMLResponse(html)


async def _run_pipeline(
    user_id: uuid.UUID,
    container: Container,
    state: PipelineState,
) -> None:
    """Background task: discover jobs, then score them."""
    try:
        # Phase 1: Discover
        state.stage = _STAGE_DISCOVERING
        results = await container.discover_jobs.execute(
            user_id=user_id,
            source_name=state.source,
            query=state.keyword,
            remote=False,
        )
        for r in results:
            state.discovered += r.fetched
            state.new_jobs += r.new
            state.skipped_jobs += r.skipped

        # Phase 2: Match
        state.stage = _STAGE_MATCHING
        match_result = await container.match_jobs.execute(
            user_id=user_id,
            limit=500,
        )
        state.scored = match_result.scored
        state.saved = match_result.saved
        state.filtered = match_result.filtered
        state.skipped_low_embedding = match_result.skipped_low_embedding

        state.stage = _STAGE_DONE
        state.finished_at = datetime.now(UTC)

    except Exception as exc:
        state.stage = _STAGE_ERROR
        state.error = str(exc)
        state.finished_at = datetime.now(UTC)
    finally:
        _pipeline_locks.pop(user_id, None)


def _render_progress(state: PipelineState) -> str:
    """Return an HTML fragment for the pipeline progress card."""
    if state.stage == _STAGE_IDLE:
        return ""

    poll_attr = ""
    if state.stage in (_STAGE_DISCOVERING, _STAGE_MATCHING):
        poll_attr = ' hx-get="/api/pipeline/status" hx-trigger="every 2s" hx-swap="outerHTML"'

    # Stage indicator
    if state.stage == _STAGE_DISCOVERING:
        icon = '<span class="spinner"></span>'
        label = f"Discovering jobs for &ldquo;{state.keyword}&rdquo;..."
        detail = f"Found {state.discovered} jobs ({state.new_jobs} new)"
    elif state.stage == _STAGE_MATCHING:
        icon = '<span class="spinner"></span>'
        label = "Scoring jobs against your profile..."
        detail = (
            f"Discovered {state.new_jobs} new jobs &middot; "
            f"Scored {state.scored} &middot; Saved {state.saved}"
        )
    elif state.stage == _STAGE_DONE:
        icon = '<span style="color:var(--green);font-size:18px">&#10003;</span>'
        label = "Pipeline complete!"
        detail = (
            f"Discovered {state.new_jobs} new jobs &middot; "
            f"Scored {state.scored} &middot; Saved {state.saved} matches &middot; "
            f"Filtered {state.filtered} &middot; Low-embedding {state.skipped_low_embedding}"
        )
    elif state.stage == _STAGE_ERROR:
        icon = '<span style="color:var(--red);font-size:18px">&#10007;</span>'
        label = "Pipeline failed"
        detail = state.error[:200]
    else:
        icon = ""
        label = ""
        detail = ""

    view_link = ""
    if state.stage == _STAGE_DONE and state.saved > 0:
        view_link = (
            ' <a href="/jobs?tab=matched" class="btn btn-primary btn-sm" '
            'style="margin-top:var(--space-3)">View Matches</a>'
        )

    return (
        f'<div id="pipeline-progress" style="padding:var(--space-4);border-radius:var(--radius-sm);'
        f"border:1px solid var(--border);background:var(--bg-card-hover);"
        f'margin-top:var(--space-3)"{poll_attr}>'
        f'<div style="display:flex;align-items:center;gap:var(--space-3)">'
        f"{icon}"
        f'<div style="flex:1">'
        f'<div style="font-size:14px;font-weight:600">{label}</div>'
        f'<div style="font-size:12px;color:var(--text-muted);margin-top:2px">{detail}</div>'
        f"</div>"
        f"</div>"
        f"{view_link}"
        f"</div>"
    )
