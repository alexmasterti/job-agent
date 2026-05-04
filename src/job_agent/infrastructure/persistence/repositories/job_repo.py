from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from job_agent.domain.models.job import Job
from job_agent.infrastructure.persistence.models import JobRow

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class JobRepository:
    """SQLAlchemy implementation of JobRepositoryPort."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_by_hash(self, user_id: uuid.UUID, content_hash: str) -> Job | None:
        async with self._sf() as s:
            row = await s.scalar(
                select(JobRow).where(
                    JobRow.user_id == user_id,
                    JobRow.content_hash == content_hash,
                )
            )
        return _to_domain(row) if row else None

    async def save(self, job: Job) -> Job:
        async with self._sf() as s, s.begin():
            row = JobRow(
                id=job.id,
                user_id=job.user_id,
                source=job.source,
                external_id=job.external_id,
                content_hash=job.content_hash,
                title=job.title,
                company=job.company,
                location=job.location,
                remote=job.remote,
                url=job.url,
                description=job.description,
                ats_type=job.ats_type,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                discovered_at=job.discovered_at,
            )
            s.add(row)
        return job

    async def upsert_many(self, jobs: list[Job]) -> tuple[int, int]:
        """Bulk-insert jobs, skipping duplicates by (user_id, content_hash).

        Returns (new_count, skipped_count).
        """
        if not jobs:
            return 0, 0

        values = [
            {
                "id": job.id,
                "user_id": job.user_id,
                "source": job.source,
                "external_id": job.external_id,
                "content_hash": job.content_hash,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "remote": job.remote,
                "url": job.url,
                "description": job.description,
                "ats_type": job.ats_type,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "discovered_at": job.discovered_at,
            }
            for job in jobs
        ]

        stmt = insert(JobRow).values(values).on_conflict_do_nothing(constraint="uq_job_user_hash")
        async with self._sf() as s, s.begin():
            result = await s.execute(stmt)

        new_count: int = result.rowcount  # type: ignore[attr-defined]
        return new_count, len(jobs) - new_count

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        async with self._sf() as s:
            row = await s.scalar(select(JobRow).where(JobRow.id == job_id))
        return _to_domain(row) if row else None

    async def list_unmatched(self, user_id: uuid.UUID, limit: int = 500) -> list[Job]:
        async with self._sf() as s:
            rows = (
                await s.scalars(
                    select(JobRow)
                    .where(JobRow.user_id == user_id)
                    .order_by(JobRow.discovered_at.desc())
                    .limit(limit)
                )
            ).all()
        return [_to_domain(r) for r in rows]

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        async with self._sf() as s:
            return (
                await s.scalar(
                    select(func.count()).select_from(JobRow).where(JobRow.user_id == user_id)
                )
            ) or 0


def _to_domain(row: JobRow) -> Job:
    return Job(
        id=row.id,
        user_id=row.user_id,
        source=row.source,
        external_id=row.external_id,
        content_hash=row.content_hash,
        title=row.title,
        company=row.company,
        location=row.location,
        remote=row.remote,
        url=row.url,
        description=row.description,
        ats_type=row.ats_type,
        salary_min=row.salary_min,
        salary_max=row.salary_max,
        discovered_at=row.discovered_at,
    )
