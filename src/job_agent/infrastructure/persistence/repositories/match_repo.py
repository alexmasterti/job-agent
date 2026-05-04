from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from job_agent.domain.models.match import Match
from job_agent.infrastructure.persistence.models import JobRow, MatchRow

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class MatchRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_scored_job_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        async with self._sf() as s:
            rows = (
                await s.scalars(select(MatchRow.job_id).where(MatchRow.user_id == user_id))
            ).all()
        return set(rows)

    async def save(self, match: Match) -> Match:
        async with self._sf() as s, s.begin():
            row = MatchRow(
                id=match.id,
                user_id=match.user_id,
                job_id=match.job_id,
                embedding_score=match.embedding_score,
                llm_score=match.llm_score,
                hard_requirement_score=match.hard_requirement_score,
                final_score=match.final_score,
                reasoning=match.reasoning,
                flags=match.flags,
                scored_at=match.scored_at,
            )
            s.add(row)
        return match

    async def save_many(self, matches: list[Match]) -> int:
        if not matches:
            return 0
        values = [
            {
                "id": m.id,
                "user_id": m.user_id,
                "job_id": m.job_id,
                "embedding_score": m.embedding_score,
                "llm_score": m.llm_score,
                "hard_requirement_score": m.hard_requirement_score,
                "final_score": m.final_score,
                "reasoning": m.reasoning,
                "flags": m.flags,
                "scored_at": m.scored_at,
            }
            for m in matches
        ]
        stmt = insert(MatchRow).values(values).on_conflict_do_nothing()
        async with self._sf() as s, s.begin():
            result = await s.execute(stmt)
        return result.rowcount  # type: ignore[no-any-return, attr-defined]

    async def list_top(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> list[tuple[Match, str, str, str, str, bool]]:
        """Return top matches joined with job title/company/location/url/remote."""
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(
                        MatchRow,
                        JobRow.title,
                        JobRow.company,
                        JobRow.location,
                        JobRow.url,
                        JobRow.remote,
                    )
                    .join(JobRow, MatchRow.job_id == JobRow.id)
                    .where(MatchRow.user_id == user_id)
                    .order_by(MatchRow.final_score.desc())
                    .limit(limit)
                )
            ).all()

        return [
            (
                _to_domain(r.MatchRow),
                r.title,
                r.company,
                r.location,
                r.url,
                r.remote,
            )
            for r in rows
        ]

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        async with self._sf() as s:
            return (
                await s.scalar(
                    select(func.count()).select_from(MatchRow).where(MatchRow.user_id == user_id)
                )
            ) or 0


def _to_domain(row: MatchRow) -> Match:
    return Match(
        id=row.id,
        user_id=row.user_id,
        job_id=row.job_id,
        embedding_score=row.embedding_score,
        llm_score=row.llm_score,
        hard_requirement_score=row.hard_requirement_score,
        final_score=row.final_score,
        reasoning=row.reasoning,
        flags=list(row.flags) if row.flags else [],
        scored_at=row.scored_at if isinstance(row.scored_at, datetime) else datetime.now(UTC),
    )
