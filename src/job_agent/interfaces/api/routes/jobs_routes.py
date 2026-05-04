from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from job_agent.infrastructure.geo.geocoder import is_within_radius
from job_agent.infrastructure.resume.builder import build_resume_docx
from job_agent.interfaces.api.middleware.auth import _COOKIE_NAME, decode_session

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

    from job_agent.config import Settings
    from job_agent.domain.models.profile import Profile

router = APIRouter()

_PAGE_SIZE = 20

_REMOTE_KEYWORDS = {"remote", "anywhere", "distributed", "work from home", "wfh", "worldwide"}


def _location_ok(job_location: str, job_remote: bool, profile: Profile | None) -> bool:
    """Return True if the job satisfies the user's location preferences."""
    if profile is None:
        return True
    pref = profile.remote_preference  # "remote_only" | "hybrid_ok" | "any"
    loc_lower = job_location.lower()
    is_remote = job_remote or any(kw in loc_lower for kw in _REMOTE_KEYWORDS)

    if pref == "remote_only":
        return is_remote

    # hybrid_ok or any: remote jobs always pass
    if is_remote:
        return True

    if not profile.preferred_locations:
        return True  # No on-site preferences set → pass everything

    return any(
        is_within_radius(job_location, pl.name, pl.radius_miles)
        for pl in profile.preferred_locations
    )


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


@router.get("/jobs", response_model=None)
async def jobs_page(
    request: Request,
    tab: str = "matched",
    page: int = 1,
    min_score: int = -1,
    ats: str = "all",
) -> HTMLResponse | RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login")

    container = request.app.state.container
    user = await container.user_repo.get_by_id(user_id)
    if not user:
        return RedirectResponse("/auth/login")

    # Use profile threshold as default if no explicit min_score in URL
    profile = await container.profile_repo.get_by_user(user_id)
    if min_score < 0:
        min_score = profile.min_match_score if profile else 0

    app_counts = await container.application_repo.counts(user_id)
    applying_count = app_counts.get("applying", 0)
    applied_count = sum(app_counts.get(s, 0) for s in ("applied_manual", "auto_applied"))

    ats_filter = ats if ats in ("all", "greenhouse", "lever") else "all"

    ctx: dict[str, object] = {
        "user": user,
        "tab": tab,
        "applying_count": applying_count,
        "applied_count": applied_count,
        "min_score": min_score,
        "ats_filter": ats_filter,
        "page": page,
    }

    if tab == "applying":
        rows = await container.application_repo.list_applying(user_id)
        match_scores: dict[uuid.UUID, float] = {}
        for m, *_ in await container.match_repo.list_top(user_id, limit=500):
            match_scores[m.job_id] = m.final_score
        ctx.update({"applying": rows, "match_scores": match_scores})

    elif tab == "applied":
        rows = await container.application_repo.list_applied(user_id)
        match_scores = {}
        for m, *_ in await container.match_repo.list_top(user_id, limit=500):
            match_scores[m.job_id] = m.final_score
        ctx.update({"applied": rows, "match_scores": match_scores})

    else:  # matched
        all_matches = await container.match_repo.list_top(user_id, limit=500)
        filtered = [
            (m, t, c, loc, u, r, a, posted)
            for m, t, c, loc, u, r, a, posted in all_matches
            if m.final_score >= min_score
            and _location_ok(loc, r, profile)
            and (ats_filter == "all" or a == ats_filter)
        ]
        total = len(filtered)
        page = max(1, page)
        offset = (page - 1) * _PAGE_SIZE
        page_matches = filtered[offset : offset + _PAGE_SIZE]
        total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)

        applied_ids: set[uuid.UUID] = set()
        applying_ids: set[uuid.UUID] = set()
        auto_applied_ids: set[uuid.UUID] = set()
        for match, *_ in page_matches:
            app = await container.application_repo.get_by_job(user_id, match.job_id)
            if app:
                if app.status == "applying":
                    applying_ids.add(match.job_id)
                elif app.status == "auto_applied":
                    auto_applied_ids.add(match.job_id)
                    applied_ids.add(match.job_id)
                else:
                    applied_ids.add(match.job_id)

        ctx.update(
            {
                "matches": page_matches,
                "applied_ids": applied_ids,
                "applying_ids": applying_ids,
                "auto_applied_ids": auto_applied_ids,
                "total": total,
                "total_pages": total_pages,
                "location_filter_active": bool(
                    profile and (profile.preferred_locations or profile.remote_preference != "any")
                ),
            }
        )

    return _templates(request).TemplateResponse(request, "jobs.html", ctx)


@router.get("/api/applications/{app_id}/resume/download", response_model=None)
async def download_tailored_resume(request: Request, app_id: uuid.UUID) -> Response:
    user_id = _get_user_id(request)
    if not user_id:
        return Response("Unauthorized", status_code=401)

    container = request.app.state.container
    app = await container.application_repo.get_by_id(app_id)
    if not app or app.user_id != user_id:
        return Response("Not found", status_code=404)

    tailored = (app.form_fields_snapshot or {}).get("tailored_resume", "")
    if not tailored:
        return Response("No tailored resume available", status_code=404)

    docx_bytes = build_resume_docx(tailored)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="resume-tailored-{app_id}.docx"'},
    )


@router.get("/api/applications/{app_id}/screenshot", response_model=None)
async def view_screenshot(request: Request, app_id: uuid.UUID) -> Response:
    user_id = _get_user_id(request)
    if not user_id:
        return Response("Unauthorized", status_code=401)

    container = request.app.state.container
    app = await container.application_repo.get_by_id(app_id)
    if not app or app.user_id != user_id:
        return Response("Not found", status_code=404)

    if not app.screenshot_path:
        return Response("No screenshot available", status_code=404)

    from pathlib import Path

    path = Path(app.screenshot_path)
    if not path.exists():
        return Response("Screenshot file missing", status_code=404)

    return Response(content=path.read_bytes(), media_type="image/png")


@router.get("/queue", response_model=None)
async def queue_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse("/jobs?tab=applying")


@router.get("/applications", response_model=None)
async def applications_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse("/jobs?tab=applied")


@router.post("/api/jobs/{job_id}/apply", response_model=None)
async def apply_job(request: Request, job_id: uuid.UUID) -> HTMLResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return HTMLResponse(
            '<button class="btn btn-secondary btn-sm" disabled>Login required</button>'
        )

    container = request.app.state.container

    # Idempotent — don't double-apply
    existing = await container.application_repo.get_by_job(user_id, job_id)
    if existing:
        if existing.status == "applying":
            label = "Applying..."
        elif existing.status == "auto_applied":
            label = "Auto-submitted"
        else:
            label = "Applied"
        return HTMLResponse(f'<button class="btn btn-secondary btn-sm" disabled>{label}</button>')

    # Use the job's actual ATS type so auto-submit can pick it up
    job = await container.job_repo.get_by_id(job_id)
    ats_type = job.ats_type if job and job.ats_type != "unknown" else "manual"
    app = await container.application_repo.create(
        user_id, job_id, ats_type=ats_type, status="applying"
    )

    # Fire background tailoring — non-blocking
    asyncio.create_task(container.tailor_and_apply.execute(app.id, user_id, job_id))

    return HTMLResponse(
        f'<button class="btn btn-secondary btn-sm" disabled '
        f'hx-get="/api/jobs/{job_id}/status" hx-trigger="every 4s" hx-swap="outerHTML">'
        f"Applying...</button>"
    )


@router.get("/api/jobs/{job_id}/status", response_model=None)
async def job_apply_status(request: Request, job_id: uuid.UUID) -> HTMLResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return HTMLResponse("")

    container = request.app.state.container
    app = await container.application_repo.get_by_job(user_id, job_id)
    if not app:
        return HTMLResponse(
            '<button class="btn btn-primary btn-sm" '
            f'hx-post="/api/jobs/{job_id}/apply" hx-swap="outerHTML">Apply Me</button>'
        )

    if app.status == "applying":
        return HTMLResponse(
            f'<button class="btn btn-secondary btn-sm" disabled '
            f'hx-get="/api/jobs/{job_id}/status" hx-trigger="every 4s" hx-swap="outerHTML">'
            f"Applying...</button>"
        )

    label = "Auto-submitted" if app.status == "auto_applied" else "Applied"
    return HTMLResponse(f'<button class="btn btn-secondary btn-sm" disabled>{label}</button>')


@router.post("/api/applications/{app_id}/verify", response_model=None)
async def verify_application(request: Request, app_id: uuid.UUID) -> HTMLResponse:
    """Re-open the Greenhouse form, re-fill, submit, enter verification code."""
    user_id = _get_user_id(request)
    if not user_id:
        return HTMLResponse('<span style="color:var(--red);font-size:12px">Login required</span>')

    form = await request.form()
    code = str(form.get(f"code-{app_id}", "")).strip()
    if not code:
        return HTMLResponse('<span style="color:var(--red);font-size:12px">Enter the code</span>')

    container = request.app.state.container
    app = await container.application_repo.get_by_id(app_id)
    if not app or app.user_id != user_id:
        return HTMLResponse('<span style="color:var(--red);font-size:12px">Not found</span>')

    # Run verification inline (takes ~20s but user needs the result)
    from job_agent.composition_root import Container  # noqa: TC001
    from job_agent.infrastructure.persistence.models import ApplicationRow  # noqa: TC001
    from job_agent.infrastructure.submission.browser import complete_verification

    c = container  # type: Container
    a = app  # type: ApplicationRow

    job = await c.job_repo.get_by_id(a.job_id)
    profile = await c.profile_repo.get_by_user(user_id)
    user = await c.user_repo.get_by_id(user_id)

    if not job or not profile:
        return HTMLResponse('<span style="color:var(--red);font-size:12px">Missing data</span>')

    result = await complete_verification(
        url=job.ats_apply_url or job.url,
        ats_type=job.ats_type,
        profile=profile,
        email=str(user.email) if user else "",
        resume_text=(a.form_fields_snapshot or {}).get("tailored_resume", ""),
        verification_code=code,
    )

    if result["success"]:
        await c.application_repo.update_submission(
            app_id=a.id,
            status="auto_applied",
            ats_confirmation_id=f"verified-{a.id.hex[:8]}",
            screenshot_path=str(result.get("screenshot", "")),
            response_text=str(result.get("page_text", ""))[:500],
        )
        return HTMLResponse(
            '<span style="color:var(--green);font-size:12px;font-weight:600">Auto-submitted!</span>'
        )

    error = str(result.get("error", "Verification failed"))
    return HTMLResponse(f'<span style="color:var(--red);font-size:12px">{error[:80]}</span>')
