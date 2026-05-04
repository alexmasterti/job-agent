from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from job_agent.config import Settings
from job_agent.infrastructure.profile.parser import extract_text_from_docx, extract_text_from_pdf
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


def _extract_text(file_bytes: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)
    try:
        if suffix == ".pdf":
            return extract_text_from_pdf(tmp_path)
        return extract_text_from_docx(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/profile", response_model=None)
async def profile_page(request: Request) -> HTMLResponse | RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login")

    container = request.app.state.container
    user = await container.user_repo.get_by_id(user_id)
    if not user:
        return RedirectResponse("/auth/login")

    profile = await container.profile_repo.get_by_user(user_id)
    resumes = await container.resume_repo.list_for_user(user_id)

    preferred_locations = (profile.preferred_locations if profile else [])
    remote_preference = (profile.remote_preference if profile else "any")

    return _templates(request).TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "profile": profile,
            "resumes": resumes,
            "preferred_locations": preferred_locations,
            "remote_preference": remote_preference,
        },
    )


@router.post("/profile/preferences", response_model=None)
async def save_preferences(request: Request) -> RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login", status_code=303)

    form = await request.form()
    raw_locs = str(form.get("preferred_locations", ""))
    remote_pref = str(form.get("remote_preference", "any"))

    locations = [ln.strip() for ln in raw_locs.replace(",", "\n").splitlines() if ln.strip()]

    container = request.app.state.container
    await container.profile_repo.save_preferences(user_id, locations, remote_pref)

    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/resumes/upload", response_model=None)
async def upload_resume(request: Request, file: UploadFile) -> RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login", status_code=303)

    form = await request.form()
    name = str(form.get("name", "")).strip() or Path(file.filename or "resume").stem
    set_primary = form.get("set_primary") == "on"

    suffix = Path(file.filename or "resume.pdf").suffix.lower() or ".pdf"
    content = await file.read()
    resume_text = _extract_text(content, suffix)

    container = request.app.state.container
    existing = await container.resume_repo.list_for_user(user_id)
    # First upload is always primary
    if not existing:
        set_primary = True

    await container.resume_repo.create(
        user_id=user_id,
        name=name,
        file_ext=suffix,
        file_data=content,
        resume_text=resume_text,
        set_primary=set_primary,
    )

    # Re-parse profile from the primary resume text
    if set_primary:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            await container.load_profile.execute(user_id, resume_path=tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/resumes/{resume_id}/set-primary", response_model=None)
async def set_primary_resume(request: Request, resume_id: uuid.UUID) -> RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login", status_code=303)

    container = request.app.state.container
    row = await container.resume_repo.get_by_id(resume_id, user_id)
    if row:
        await container.resume_repo.set_primary(resume_id, user_id)
        # Re-parse profile from newly promoted primary resume
        suffix = row.file_ext
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(row.file_data)
            tmp_path = Path(tmp.name)
        try:
            await container.load_profile.execute(user_id, resume_path=tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/resumes/{resume_id}/delete", response_model=None)
async def delete_resume(request: Request, resume_id: uuid.UUID) -> RedirectResponse:
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/auth/login", status_code=303)

    container = request.app.state.container
    await container.resume_repo.delete(resume_id, user_id)
    return RedirectResponse("/profile", status_code=303)


@router.get("/profile/resumes/{resume_id}/download", response_model=None)
async def download_resume(request: Request, resume_id: uuid.UUID) -> Response:
    user_id = _get_user_id(request)
    if not user_id:
        return Response("Unauthorized", status_code=401)

    container = request.app.state.container
    row = await container.resume_repo.get_by_id(resume_id, user_id)
    if not row:
        return Response("Not found", status_code=404)

    media = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if row.file_ext == ".docx"
        else "application/pdf"
    )
    safe_name = row.name.replace(" ", "-").lower()
    return Response(
        content=row.file_data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}{row.file_ext}"'},
    )


# Keep old upload route for backward compat (redirects to new)
@router.post("/profile/upload", response_model=None)
async def upload_resume_legacy(request: Request, file: UploadFile) -> RedirectResponse:
    return await upload_resume(request, file)
