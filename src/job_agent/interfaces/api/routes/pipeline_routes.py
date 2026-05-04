"""Dashboard-triggered discover + match pipeline with live progress."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from job_agent.interfaces.api.middleware.auth import _COOKIE_NAME, decode_session

if TYPE_CHECKING:
    from job_agent.composition_root import Container
    from job_agent.config import Settings

log = structlog.get_logger()

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
    """Background task: discover jobs source by source, then score them.

    Updates state.discovered / state.new_jobs live so the HTMX poller
    can show incremental progress to the user.
    """
    try:
        # ── Phase 1: Discover (per-source, live counter) ─────────────
        state.stage = _STAGE_DISCOVERING

        source_name = state.source
        sources_map = {
            "greenhouse": container.discover_jobs._sources.get("greenhouse"),
            "lever": container.discover_jobs._sources.get("lever"),
        }
        if source_name == "all":
            targets = [s for s in sources_map.values() if s is not None]
        else:
            s = sources_map.get(source_name)
            targets = [s] if s else []

        for source in targets:
            log.info("pipeline.discover.source", source=source.source_name)
            try:
                jobs = await source.discover(user_id, state.keyword)
                new, skipped = await container.job_repo.upsert_many(jobs)
                state.discovered += len(jobs)
                state.new_jobs += new
                state.skipped_jobs += skipped
            except Exception as exc:
                log.warning(
                    "pipeline.discover.source_error",
                    source=getattr(source, "source_name", "?"),
                    error=str(exc),
                )

        # ── Phase 2: Match ───────────────────────────────────────────
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
        return '<div id="pipeline-progress"></div>'

    is_active = state.stage in (_STAGE_DISCOVERING, _STAGE_MATCHING)
    poll_attr = (
        ' hx-get="/api/pipeline/status" hx-trigger="every 1s" hx-swap="outerHTML"'
        if is_active
        else ""
    )

    # Stage-specific content
    if state.stage == _STAGE_DISCOVERING:
        stage_num = "1/2"
        label = f"Discovering &ldquo;{state.keyword}&rdquo; from job boards..."
        counters = (
            f'<div style="display:flex;gap:var(--space-5);margin-top:var(--space-3)">'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--accent-light)">{state.discovered}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">fetched</div></div>'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--green,#22c55e)">{state.new_jobs}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">new</div></div>'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--text-dim)">{state.skipped_jobs}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">duplicates</div></div>'
            f"</div>"
        )
    elif state.stage == _STAGE_MATCHING:
        stage_num = "2/2"
        label = "Scoring jobs against your profile (embeddings + LLM)..."
        counters = (
            f'<div style="display:flex;gap:var(--space-5);margin-top:var(--space-3)">'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--accent-light)">{state.new_jobs}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">discovered</div></div>'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--green,#22c55e)">{state.scored}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">scored</div></div>'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--text-muted)">{state.saved}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">saved</div></div>'
            f"</div>"
        )
    elif state.stage == _STAGE_DONE:
        stage_num = ""
        label = "Pipeline complete!"
        counters = (
            f'<div style="display:flex;gap:var(--space-5);margin-top:var(--space-3)">'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--accent-light)">{state.discovered}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">fetched</div></div>'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--green,#22c55e)">{state.new_jobs}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">new jobs</div></div>'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--accent-light)">{state.scored}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">scored</div></div>'
            f'<div><span style="font-size:20px;font-weight:700;color:var(--green,#22c55e)">{state.saved}</span>'
            f'<div style="font-size:11px;color:var(--text-dim)">matches</div></div>'
            f"</div>"
        )
    elif state.stage == _STAGE_ERROR:
        stage_num = ""
        label = "Pipeline failed"
        counters = f'<div style="font-size:13px;color:var(--red,#ef4444);margin-top:var(--space-2)">{state.error[:200]}</div>'
    else:
        return '<div id="pipeline-progress"></div>'

    # Icon
    if is_active:
        icon = '<span class="spinner" style="width:20px;height:20px"></span>'
    elif state.stage == _STAGE_DONE:
        icon = '<span style="font-size:20px">&#9989;</span>'
    else:
        icon = '<span style="font-size:20px">&#10060;</span>'

    # Progress bar (indeterminate for active, full for done)
    if is_active:
        bar = (
            '<div style="margin-top:var(--space-3);height:4px;border-radius:2px;'
            'background:rgba(124,58,237,0.15);overflow:hidden">'
            '<div style="height:100%;width:30%;border-radius:2px;'
            'background:var(--accent-light,#7c3aed);animation:progress-slide 1.5s ease-in-out infinite"></div>'
            "</div>"
        )
    elif state.stage == _STAGE_DONE:
        bar = (
            '<div style="margin-top:var(--space-3);height:4px;border-radius:2px;'
            'background:rgba(34,197,94,0.15)">'
            '<div style="height:100%;width:100%;border-radius:2px;'
            'background:var(--green,#22c55e);transition:width 0.5s"></div>'
            "</div>"
        )
    else:
        bar = ""

    # Stage badge
    badge = ""
    if stage_num:
        badge = (
            f'<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;'
            f'background:var(--accent-soft,rgba(124,58,237,0.1));color:var(--accent-light,#7c3aed)">'
            f"Step {stage_num}</span>"
        )

    # Action link
    action = ""
    if state.stage == _STAGE_DONE and state.saved > 0:
        action = (
            '<a href="/jobs?tab=matched" class="btn btn-primary btn-sm" '
            'style="margin-top:var(--space-3)">View Matches &rarr;</a>'
        )
    elif state.stage == _STAGE_DONE and state.saved == 0 and state.new_jobs == 0:
        action = (
            '<div style="font-size:12px;color:var(--text-dim);margin-top:var(--space-2)">'
            "No new jobs found. Try a different keyword or check back later.</div>"
        )

    return (
        f'<div id="pipeline-progress" style="padding:var(--space-4);border-radius:var(--radius-sm);'
        f"border:1px solid var(--border);background:var(--bg-card-hover);"
        f'margin-top:var(--space-3)"{poll_attr}>'
        f'<div style="display:flex;align-items:center;gap:var(--space-3)">'
        f"{icon}"
        f'<div style="flex:1">'
        f'<div style="display:flex;align-items:center;gap:var(--space-2)">'
        f'<span style="font-size:14px;font-weight:600">{label}</span>'
        f"{badge}</div>"
        f"</div></div>"
        f"{bar}"
        f"{counters}"
        f"{action}"
        f"</div>"
        f"<style>"
        f"@keyframes progress-slide {{"
        f"0% {{ transform: translateX(-100%); }}"
        f"100% {{ transform: translateX(400%); }}"
        f"}}</style>"
    )
