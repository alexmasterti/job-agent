from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

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
