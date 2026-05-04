from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import uuid

    from job_agent.domain.models.application import Application, ApplicationStatus
    from job_agent.domain.models.job import Job
    from job_agent.domain.models.match import Match
    from job_agent.domain.models.profile import Profile
    from job_agent.domain.models.user import User


@runtime_checkable
class UserRepositoryPort(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_google_sub(self, google_sub: str) -> User | None: ...
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...
    async def upsert(self, user: User) -> User: ...


@runtime_checkable
class ProfileRepositoryPort(Protocol):
    async def get_by_user(self, user_id: uuid.UUID) -> Profile | None: ...
    async def save(self, profile: Profile) -> Profile: ...


@runtime_checkable
class JobRepositoryPort(Protocol):
    async def get_by_hash(self, user_id: uuid.UUID, content_hash: str) -> Job | None: ...
    async def save(self, job: Job) -> Job: ...
    async def list_unmatched(self, user_id: uuid.UUID, limit: int = 500) -> list[Job]: ...


@runtime_checkable
class ApplicationRepositoryPort(Protocol):
    async def get_by_job(self, user_id: uuid.UUID, job_id: uuid.UUID) -> Application | None: ...
    async def save(self, application: Application) -> Application: ...
    async def count_today(self, user_id: uuid.UUID) -> int: ...
    async def list_by_status(
        self, user_id: uuid.UUID, status: ApplicationStatus
    ) -> list[Application]: ...


@runtime_checkable
class LLMCallRepositoryPort(Protocol):
    async def log_call(
        self,
        *,
        user_id: uuid.UUID,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        request_hash: str,
    ) -> None: ...

    async def today_spend(self, user_id: uuid.UUID) -> float: ...


@runtime_checkable
class MatchRepositoryPort(Protocol):
    async def save(self, match: Match) -> Match: ...
    async def list_top(self, user_id: uuid.UUID, limit: int = 50) -> list[Match]: ...
