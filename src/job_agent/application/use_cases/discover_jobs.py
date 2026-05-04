"""DiscoverJobsUseCase — orchestrates source adapters → job repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import uuid

    from job_agent.domain.ports.job_source import JobSourcePort
    from job_agent.infrastructure.persistence.repositories.job_repo import JobRepository

log = structlog.get_logger()


@dataclass
class DiscoveryResult:
    source: str
    fetched: int
    new: int
    skipped: int


class DiscoverJobsUseCase:
    def __init__(
        self,
        sources: dict[str, JobSourcePort],
        job_repo: JobRepository,
    ) -> None:
        self._sources = sources
        self._job_repo = job_repo

    async def execute(
        self,
        user_id: uuid.UUID,
        source_name: str,
        query: str,
        remote: bool = False,
    ) -> list[DiscoveryResult]:
        if source_name == "all":
            targets = list(self._sources.values())
        elif source_name in self._sources:
            targets = [self._sources[source_name]]
        else:
            raise ValueError(f"Unknown source '{source_name}'. Available: {list(self._sources)}")

        results: list[DiscoveryResult] = []
        for source in targets:
            log.info("discover.start", source=source.source_name, query=query, remote=remote)
            jobs = await source.discover(user_id, query, remote)
            new, skipped = await self._job_repo.upsert_many(jobs)
            log.info(
                "discover.done",
                source=source.source_name,
                fetched=len(jobs),
                new=new,
                skipped=skipped,
            )
            results.append(
                DiscoveryResult(
                    source=source.source_name,
                    fetched=len(jobs),
                    new=new,
                    skipped=skipped,
                )
            )

        return results
