"""Lever ATS submission adapter.

Lever public postings accept applications via multipart POST:
  POST https://api.lever.co/v0/postings/{company}/{posting_id}?key=...

For public boards without an API key, use the candidate-facing form endpoint:
  POST https://jobs.lever.co/company/posting_id/apply

Required fields: name, email, resume (file).
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

_TIMEOUT = httpx.Timeout(30.0)


def _extract_company_and_posting(url: str) -> tuple[str, str] | None:
    """Extract company slug and posting ID from a Lever URL.

    Handles:
      https://jobs.lever.co/company/uuid
      https://jobs.lever.co/company/uuid/apply
    """
    import re

    match = re.search(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})", url)
    if match:
        return match.group(1), match.group(2)
    return None


class LeverSubmitter:
    """Submits applications to Lever public job boards."""

    ats_type = "lever"

    async def submit(self, application: Application, profile: Profile) -> Application:
        """Submit application via Lever's candidate form endpoint.

        Idempotent: returns unchanged application if already submitted.
        """
        if application.ats_confirmation_id:
            log.info("lever.submit.skip_idempotent", app_id=str(application.id))
            return application

        submit_url = application.submission_url
        # If URL already ends with /apply, use it directly
        if "jobs.lever.co" in submit_url and "/apply" in submit_url:
            url = submit_url
        else:
            parsed = _extract_company_and_posting(submit_url)
            if not parsed:
                log.warning(
                    "lever.submit.bad_url",
                    app_id=str(application.id),
                    url=submit_url,
                )
                return application
            company, posting_id = parsed
            url = f"https://jobs.lever.co/{company}/{posting_id}/apply"

        name = profile.full_name.strip() if profile.full_name else ""
        email = application.form_fields_snapshot.get("email", "")
        if not email:
            email = _extract_email(profile)

        tailored_resume = application.form_fields_snapshot.get("tailored_resume", "")

        form_data = {
            "name": name,
            "email": email,
            "org": "Other",
        }

        files = {}
        if tailored_resume:
            files["resume"] = (
                "resume.txt",
                tailored_resume.encode(),
                "text/plain",
            )

        log.info("lever.submit.start", app_id=str(application.id), url=url)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, data=form_data, files=files)

        if resp.status_code in (200, 201, 303):
            confirmation_id = f"lever-{uuid.uuid4().hex[:12]}"
            log.info(
                "lever.submit.success",
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
            "lever.submit.failed",
            app_id=str(application.id),
            status=resp.status_code,
            body=resp.text[:300],
        )
        return application


def _extract_email(profile: Profile) -> str:
    """Try to find email from profile experience or structured data."""
    for exp in profile.experience:
        if "email" in exp:
            return str(exp["email"])
    return ""
