"""SubmitApplicationUseCase — auto-submits a tailored application to the ATS."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import uuid

    from job_agent.domain.ports.job_submitter import JobSubmitterPort
    from job_agent.infrastructure.persistence.repositories.application_repo import (
        ApplicationRepository,
    )
    from job_agent.infrastructure.persistence.repositories.job_repo import JobRepository
    from job_agent.infrastructure.persistence.repositories.profile_repo import ProfileRepository
    from job_agent.infrastructure.persistence.repositories.user_repo import UserRepository

log = structlog.get_logger()

# ATS types that must NEVER be auto-submitted (ToS restrictions)
_ASSIST_ONLY_ATS = frozenset({"linkedin", "indeed"})


class SubmitApplicationUseCase:
    """Picks the right submitter by ATS type and auto-submits."""

    def __init__(
        self,
        submitters: dict[str, JobSubmitterPort],
        application_repo: ApplicationRepository,
        job_repo: JobRepository,
        profile_repo: ProfileRepository,
        user_repo: UserRepository,
    ) -> None:
        self._submitters = submitters
        self._application_repo = application_repo
        self._job_repo = job_repo
        self._profile_repo = profile_repo
        self._user_repo = user_repo

    async def execute(self, app_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Submit the application. Returns True if auto-submitted, False otherwise."""
        app_row = await self._application_repo.get_by_id(app_id)
        if not app_row:
            log.warning("submit.app_not_found", app_id=str(app_id))
            return False

        # Idempotency: already submitted
        if app_row.ats_confirmation_id:
            log.info("submit.already_done", app_id=str(app_id))
            return True

        # Check ATS type — refuse ToS-restricted platforms
        ats_type = app_row.ats_type
        if ats_type in _ASSIST_ONLY_ATS:
            log.info("submit.assist_only", app_id=str(app_id), ats_type=ats_type)
            return False

        # Need a submitter for this ATS type
        submitter = self._submitters.get(ats_type)
        if not submitter:
            log.info("submit.no_submitter", app_id=str(app_id), ats_type=ats_type)
            return False

        # Load profile and job to build the Application domain model
        profile = await self._profile_repo.get_by_user(user_id)
        job = await self._job_repo.get_by_id(app_row.job_id)
        if not profile or not job:
            log.warning("submit.missing_data", app_id=str(app_id))
            return False

        # Get user email for submission forms
        user = await self._user_repo.get_by_id(user_id)
        user_email = user.email if user else ""

        # Build the domain Application from the ORM row
        from job_agent.domain.models.application import Application, ApplicationStatus

        # Inject email into form_fields for submitters
        form_fields = dict(app_row.form_fields_snapshot or {})
        if user_email and "email" not in form_fields:
            form_fields["email"] = user_email

        application = Application(
            id=app_row.id,
            user_id=app_row.user_id,
            job_id=app_row.job_id,
            status=ApplicationStatus(app_row.status),
            ats_type=app_row.ats_type,
            submission_url=app_row.submission_url or job.ats_apply_url or job.url,
            resume_hash=app_row.resume_hash,
            cover_letter_hash=app_row.cover_letter_hash,
            form_fields_snapshot=form_fields,
            ats_confirmation_id=app_row.ats_confirmation_id,
            submitted_at=app_row.submitted_at,
            created_at=app_row.created_at,
        )

        # Ensure submission_url is set
        if not application.submission_url:
            application = application.model_copy(
                update={"submission_url": job.ats_apply_url or job.url}
            )

        result = await submitter.submit(application, profile)

        # Persist the result
        if result.ats_confirmation_id:
            await self._application_repo.update_submission(
                app_id=app_id,
                status="auto_applied",
                ats_confirmation_id=result.ats_confirmation_id,
                submitted_at=result.submitted_at,
                response_text=result.response_text,
                screenshot_path=result.screenshot_path,
            )
            log.info(
                "submit.done",
                app_id=str(app_id),
                confirmation=result.ats_confirmation_id,
            )
            return True

        # Save screenshot even on failure (for debugging in UI)
        if result.screenshot_path or result.response_text:
            await self._application_repo.update_submission(
                app_id=app_id,
                status="applied_manual",
                response_text=result.response_text,
                screenshot_path=result.screenshot_path,
            )
        log.warning("submit.failed_no_confirmation", app_id=str(app_id))
        return False
