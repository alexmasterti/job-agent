"""Greenhouse ATS submission adapter.

Greenhouse public boards accept applications via multipart POST:
  POST https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}

Required fields: first_name, last_name, email. Optional: resume (file), cover_letter.
No API key required for public boards.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from job_agent.domain.models.application import Application
    from job_agent.domain.models.profile import Profile

log = structlog.get_logger()

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
_TIMEOUT = httpx.Timeout(30.0)


def _is_greenhouse_api_url(url: str) -> bool:
    """Check if URL is already a Greenhouse boards-api URL."""
    return "boards-api.greenhouse.io" in url


def _extract_slug_and_job_id(url: str) -> tuple[str, str] | None:
    """Extract company slug and job ID from a Greenhouse URL.

    Handles:
      https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id} (API URL)
      https://boards.greenhouse.io/{slug}/jobs/{id}
      https://job-boards.eu.greenhouse.io/{slug}/jobs/{id}
    """
    import re

    # API URL: boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}
    match = re.search(r"boards-api\.greenhouse\.io/v1/boards/([^/]+)/jobs/(\d+)", url)
    if match:
        return match.group(1), match.group(2)
    # Human URL: *.greenhouse.io/{slug}/jobs/{id}
    match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if match:
        return match.group(1), match.group(2)
    return None


class GreenhouseSubmitter:
    """Submits applications to Greenhouse public job boards."""

    ats_type = "greenhouse"

    async def submit(self, application: Application, profile: Profile) -> Application:
        """Submit application via Greenhouse public API.

        Idempotent: returns unchanged application if already submitted.
        """
        if application.ats_confirmation_id:
            log.info("greenhouse.submit.skip_idempotent", app_id=str(application.id))
            return application

        # Use the submission_url (which should be ats_apply_url from discovery)
        submit_url = application.submission_url
        if _is_greenhouse_api_url(submit_url):
            url = submit_url
        else:
            parsed = _extract_slug_and_job_id(submit_url)
            if not parsed:
                log.warning(
                    "greenhouse.submit.bad_url",
                    app_id=str(application.id),
                    url=submit_url,
                )
                return application
            slug, job_id = parsed
            url = _BASE_URL.format(slug=slug, job_id=job_id)

        # Parse name from profile
        name_parts = profile.full_name.strip().split() if profile.full_name else [""]
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        email = application.form_fields_snapshot.get("email", "")
        if not email:
            email = _extract_email(profile)

        tailored_resume = application.form_fields_snapshot.get("tailored_resume", "")

        form_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
        }

        files = {}
        if tailored_resume:
            files["resume"] = (
                "resume.txt",
                tailored_resume.encode(),
                "text/plain",
            )

        log.info("greenhouse.submit.start", app_id=str(application.id), url=url)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, data=form_data, files=files)

        if resp.status_code in (200, 201):
            confirmation_id = f"gh-{uuid.uuid4().hex[:12]}"
            log.info(
                "greenhouse.submit.success",
                app_id=str(application.id),
                confirmation=confirmation_id,
            )
            return application.model_copy(
                update={
                    "status": "submitted",
                    "ats_confirmation_id": confirmation_id,
                    "submitted_at": datetime.now(UTC),
                    "response_text": resp.text[:500],
                }
            )

        log.warning(
            "greenhouse.submit.failed",
            app_id=str(application.id),
            status=resp.status_code,
            body=resp.text[:300],
        )
        return application


def _extract_email(profile: Profile) -> str:
    """Try to find email from profile experience or structured data."""
    # Check if there's contact info in experience entries
    for exp in profile.experience:
        if "email" in exp:
            return str(exp["email"])
    return ""
