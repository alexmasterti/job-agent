from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import uuid

    from job_agent.domain.models.job import Job


@runtime_checkable
class JobSourcePort(Protocol):
    """Read-only port: discovers job postings from a given source."""

    source_name: str

    async def discover(self, user_id: uuid.UUID, query: str, remote: bool = False) -> list[Job]:
        """Return a list of jobs matching *query* for *user_id*.

        Implementations must not submit, mutate state, or perform side effects
        beyond network I/O.
        """
        ...
