"""LoadProfileUseCase — ingests a resume file and persists the parsed profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from job_agent.domain.exceptions import UserNotFoundError
from job_agent.infrastructure.profile.parser import parse_resume

if TYPE_CHECKING:
    import uuid
    from pathlib import Path

    from job_agent.domain.models.profile import Profile
    from job_agent.infrastructure.llm.anthropic_client import AnthropicClient
    from job_agent.infrastructure.persistence.repositories.profile_repo import ProfileRepository
    from job_agent.infrastructure.persistence.repositories.user_repo import UserRepository

log = structlog.get_logger()


class LoadProfileUseCase:
    """Parse a resume file and save the structured profile for the given user.

    Designed to be called from both the CLI and the dashboard onboarding flow.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        profile_repo: ProfileRepository,
        llm: AnthropicClient,
    ) -> None:
        self._user_repo = user_repo
        self._profile_repo = profile_repo
        self._llm = llm

    async def execute(self, user_id: uuid.UUID, resume_path: Path) -> Profile:
        """Parse *resume_path* and persist the result for *user_id*.

        Raises UserNotFoundError if the user row doesn't exist.
        """
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(f"No user found for id={user_id}")

        log.info("load_profile.start", user_id=str(user_id), path=str(resume_path))
        profile = await parse_resume(resume_path, user_id, self._llm)
        saved = await self._profile_repo.save(profile)
        log.info("load_profile.done", user_id=str(user_id), profile_id=str(saved.id))
        return saved
