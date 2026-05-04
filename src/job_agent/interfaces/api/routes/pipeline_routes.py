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
    total_to_score: int = 0
    scored: int = 0
    saved: int = 0
    filtered: int = 0
    skipped_low_embedding: int = 0
    status_detail: str = ""
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

        # ── Phase 2: Match (with per-job progress) ─────────────────
        state.stage = _STAGE_MATCHING
        state.status_detail = "Loading embedding model..."

        profile = await container.profile_repo.get_by_user(user_id)
        if not profile:
            state.status_detail = "No profile found — skipping matching"
            state.stage = _STAGE_DONE
            state.finished_at = datetime.now(UTC)
            return

        all_jobs = await container.job_repo.list_unmatched(user_id, limit=500)
        already_scored = await container.match_repo.get_scored_job_ids(user_id)
        jobs = [j for j in all_jobs if j.id not in already_scored]
        state.total_to_score = len(jobs)

        if not jobs:
            state.status_detail = "No new jobs to score"
            state.stage = _STAGE_DONE
            state.finished_at = datetime.now(UTC)
            return

        state.status_detail = f"Encoding {len(jobs)} jobs..."
        from job_agent.domain.services.matching import _profile_to_text

        profile_text = _profile_to_text(profile)
        profile_emb = container.encoder.encode(profile_text)
        job_texts = [f"{j.title} {j.description[:2000]}" for j in jobs]
        job_embs = container.encoder.encode_batch(job_texts)

        state.status_detail = "Scoring with LLM..."
        matching_svc = container.match_jobs._matching
        matches = []
        batch_unsaved: list[object] = []
        save_every = 10

        for job, job_emb in zip(jobs, job_embs, strict=False):
            try:
                result = await matching_svc.score(user_id, profile, job, job_emb, profile_emb)
            except Exception as exc:
                log.warning("pipeline.score_error", job_id=str(job.id), error=str(exc))
                result = None

            state.scored += 1
            if result is None:
                passes, _ = matching_svc.passes_hard_filters(profile, job)
                if not passes:
                    state.filtered += 1
                else:
                    state.skipped_low_embedding += 1
            else:
                matches.append(result)
                batch_unsaved.append(result)
                state.saved = len(matches)

            state.status_detail = f"Scored {state.scored}/{state.total_to_score}"

            # Save in batches so progress isn't lost on crash
            if len(batch_unsaved) >= save_every:
                await container.match_repo.save_many(batch_unsaved)  # type: ignore[arg-type]
                batch_unsaved.clear()

            # Small delay between LLM calls to respect rate limits
            if result is not None:
                await asyncio.sleep(0.3)

        # Save remaining
        if batch_unsaved:
            await container.match_repo.save_many(batch_unsaved)  # type: ignore[arg-type]

        state.stage = _STAGE_DONE
        state.finished_at = datetime.now(UTC)

    except Exception as exc:
        state.stage = _STAGE_ERROR
        state.error = str(exc)
        state.finished_at = datetime.now(UTC)
    finally:
        _pipeline_locks.pop(user_id, None)


def _progress_bar(pct: int, color: str = "var(--accent-light,#7c3aed)") -> str:
    """Render a percentage progress bar."""
    return (
        f'<div style="margin-top:var(--space-3)">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
        f'<span style="font-size:12px;font-weight:600;color:var(--text-muted)">{pct}%</span>'
        f"</div>"
        f'<div style="height:8px;border-radius:4px;background:rgba(124,58,237,0.1);overflow:hidden">'
        f'<div style="height:100%;width:{pct}%;border-radius:4px;background:{color};'
        f'transition:width 0.4s ease"></div>'
        f"</div></div>"
    )


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

    # Compute percentage
    if state.stage == _STAGE_DISCOVERING:
        pct = 0  # indeterminate — we don't know total companies
    elif state.stage == _STAGE_MATCHING:
        pct = int(state.scored / state.total_to_score * 100) if state.total_to_score > 0 else 0
    elif state.stage == _STAGE_DONE:
        pct = 100
    else:
        pct = 0

    # Build content per stage
    if state.stage == _STAGE_DISCOVERING:
        label = f"Step 1/2 — Discovering &ldquo;{state.keyword}&rdquo;..."
        sub = state.status_detail or "Querying job boards..."
        bar = _progress_bar(min(pct, 99), "var(--accent-light,#7c3aed)")
        counters = (
            f'<div style="display:flex;gap:var(--space-5);margin-top:var(--space-3)">'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--accent-light)">{state.discovered}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">fetched</span></div>'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--green,#22c55e)">{state.new_jobs}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">new</span></div>'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--text-dim)">{state.skipped_jobs}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">dupes</span></div>'
            f"</div>"
        )
    elif state.stage == _STAGE_MATCHING:
        label = f"Step 2/2 — Scoring {state.total_to_score} jobs..."
        sub = state.status_detail or "Initializing..."
        bar = _progress_bar(min(pct, 99), "var(--accent-light,#7c3aed)")
        counters = (
            f'<div style="display:flex;gap:var(--space-5);margin-top:var(--space-3)">'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--accent-light)">'
            f'{state.scored}</span><span style="font-size:13px;color:var(--text-dim)">/{state.total_to_score}'
            f'</span> <span style="font-size:12px;color:var(--text-dim)">scored</span></div>'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--green,#22c55e)">{state.saved}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">matches</span></div>'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--text-dim)">{state.filtered}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">filtered</span></div>'
            f"</div>"
        )
    elif state.stage == _STAGE_DONE:
        label = "Pipeline complete!"
        sub = ""
        bar = _progress_bar(100, "var(--green,#22c55e)")
        counters = (
            f'<div style="display:flex;gap:var(--space-5);margin-top:var(--space-3)">'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--accent-light)">{state.discovered}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">fetched</span></div>'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--green,#22c55e)">{state.new_jobs}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">new</span></div>'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--accent-light)">{state.scored}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">scored</span></div>'
            f'<div><span style="font-size:22px;font-weight:700;color:var(--green,#22c55e)">{state.saved}</span>'
            f' <span style="font-size:12px;color:var(--text-dim)">matches</span></div>'
            f"</div>"
        )
    elif state.stage == _STAGE_ERROR:
        label = "Pipeline failed"
        sub = state.error[:200]
        bar = ""
        counters = ""
    else:
        return '<div id="pipeline-progress"></div>'

    # Icon
    if is_active:
        icon = '<span class="spinner" style="width:18px;height:18px"></span>'
    elif state.stage == _STAGE_DONE:
        icon = '<span style="font-size:18px">&#9989;</span>'
    else:
        icon = '<span style="font-size:18px">&#10060;</span>'

    # Sub-status line
    sub_html = (
        f'<div style="font-size:12px;color:var(--text-dim);margin-top:2px">{sub}</div>'
        if sub
        else ""
    )

    # Action + toast
    action = ""
    toast_script = ""
    if state.stage == _STAGE_DONE and state.saved > 0:
        action = (
            '<a href="/jobs?tab=matched" class="btn btn-primary btn-sm" '
            'style="margin-top:var(--space-3);display:inline-block">View Matches &rarr;</a>'
        )
        toast_script = (
            f"<script>if(!window._pipelineToastShown){{window._pipelineToastShown=true;"
            f"showToast('Pipeline complete — {state.saved} matches found!','success');}}</script>"
        )
    elif state.stage == _STAGE_DONE and state.new_jobs == 0:
        action = (
            '<div style="font-size:12px;color:var(--text-dim);margin-top:var(--space-2)">'
            "No new jobs found. Try a different keyword or check back later.</div>"
        )
        toast_script = (
            "<script>if(!window._pipelineToastShown){window._pipelineToastShown=true;"
            "showToast('Pipeline complete — no new jobs found','info');}</script>"
        )
    elif state.stage == _STAGE_ERROR:
        toast_script = (
            "<script>if(!window._pipelineToastShown){window._pipelineToastShown=true;"
            "showToast('Pipeline failed — check logs','error');}</script>"
        )

    return (
        f'<div id="pipeline-progress" style="padding:var(--space-4);border-radius:var(--radius-sm);'
        f"border:1px solid var(--border);background:var(--bg-card-hover);"
        f'margin-top:var(--space-3)"{poll_attr}>'
        f'<div style="display:flex;align-items:center;gap:var(--space-3)">'
        f"{icon}"
        f'<div style="flex:1">'
        f'<div style="font-size:14px;font-weight:600">{label}</div>'
        f"{sub_html}"
        f"</div></div>"
        f"{bar}"
        f"{counters}"
        f"{action}"
        f"</div>"
        f"{toast_script}"
    )
