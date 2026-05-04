"""TailorAndApplyUseCase — tailors resume to a job, then marks application as applied."""

from __future__ import annotations

import uuid

import structlog

from job_agent.infrastructure.llm.anthropic_client import AnthropicClient
from job_agent.infrastructure.persistence.repositories.application_repo import ApplicationRepository
from job_agent.infrastructure.persistence.repositories.job_repo import JobRepository
from job_agent.infrastructure.persistence.repositories.profile_repo import ProfileRepository
from job_agent.infrastructure.persistence.repositories.resume_repo import UserResumeRepository

log = structlog.get_logger()

_SONNET = "claude-sonnet-4-6"

_TAILOR_SYSTEM = """\
You are an expert resume writer helping a software engineer land interviews.
Your task: rewrite the provided resume to better match the target job posting.

Rules:
- Keep ALL facts 100% accurate — never fabricate experience, skills, or credentials
- Mirror keywords and phrases from the job description naturally (ATS optimization)
- Emphasize the most relevant experience and projects for this specific role
- Tighten bullet points to be more impact-driven (action verb + metric/outcome)
- Keep the same overall structure and sections
- Output only the rewritten resume text, no commentary or markdown fences"""

_TAILOR_PROMPT = """\
## Target Job
Title: {title}
Company: {company}

{description}

## Current Resume
{resume_text}

Rewrite the resume to best fit this role. Keep all facts true."""


class TailorAndApplyUseCase:
    def __init__(
        self,
        profile_repo: ProfileRepository,
        job_repo: JobRepository,
        application_repo: ApplicationRepository,
        llm: AnthropicClient,
        resume_repo: UserResumeRepository | None = None,
    ) -> None:
        self._profile_repo = profile_repo
        self._job_repo = job_repo
        self._application_repo = application_repo
        self._llm = llm
        self._resume_repo = resume_repo

    async def execute(self, app_id: uuid.UUID, user_id: uuid.UUID, job_id: uuid.UUID) -> None:
        log.info("tailor.start", app_id=str(app_id), job_id=str(job_id))
        try:
            profile = await self._profile_repo.get_by_user(user_id)
            job = await self._job_repo.get_by_id(job_id)

            if not profile or not job:
                log.warning("tailor.missing_data", has_profile=bool(profile), has_job=bool(job))
                await self._application_repo.update_status(app_id, "applied_manual")
                return

            # Prefer the user's primary resume over the profile resume_text
            resume_text = ""
            if self._resume_repo:
                primary = await self._resume_repo.get_primary(user_id)
                if primary:
                    resume_text = primary.resume_text
            if not resume_text:
                resume_text = profile.resume_text or _profile_to_text(profile)

            prompt = _TAILOR_PROMPT.format(
                title=job.title,
                company=job.company,
                description=job.description[:3000],
                resume_text=resume_text[:6000],
            )

            tailored = await self._llm.complete(
                user_id=user_id,
                purpose="tailor_resume",
                system=_TAILOR_SYSTEM,
                prompt=prompt,
                model=_SONNET,
                max_tokens=2048,
                temperature=0.2,
            )

            await self._application_repo.update_with_tailoring(app_id, tailored, "applied_manual")
            log.info("tailor.done", app_id=str(app_id), chars=len(tailored))

        except Exception as exc:
            log.error("tailor.failed", app_id=str(app_id), error=str(exc))
            await self._application_repo.update_status(app_id, "applied_manual")


def _profile_to_text(profile) -> str:  # type: ignore[no-untyped-def]
    from job_agent.domain.services.matching import _profile_to_text as _pt
    return _pt(profile)
