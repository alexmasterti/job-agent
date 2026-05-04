from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from job_agent.infrastructure.persistence.models import ApplicationRow, JobRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class ApplicationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create(
        self,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        ats_type: str = "manual",
        status: str = "applying",
    ) -> ApplicationRow:
        async with self._sf() as s, s.begin():
            row = ApplicationRow(
                id=uuid.uuid4(),
                user_id=user_id,
                job_id=job_id,
                status=status,
                ats_type=ats_type,
                created_at=datetime.now(UTC),
            )
            s.add(row)
        return row

    async def get_by_job(self, user_id: uuid.UUID, job_id: uuid.UUID) -> ApplicationRow | None:
        async with self._sf() as s:
            result = await s.scalar(
                select(ApplicationRow).where(
                    ApplicationRow.user_id == user_id,
                    ApplicationRow.job_id == job_id,
                )
            )
        return result

    async def list_applying(
        self, user_id: uuid.UUID
    ) -> list[tuple[ApplicationRow, str, str, str, str]]:
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(
                        ApplicationRow, JobRow.title, JobRow.company, JobRow.location, JobRow.url
                    )
                    .join(JobRow, ApplicationRow.job_id == JobRow.id)
                    .where(ApplicationRow.user_id == user_id, ApplicationRow.status == "applying")
                    .order_by(ApplicationRow.created_at.desc())
                )
            ).all()
        return [(r.ApplicationRow, r.title, r.company, r.location, r.url) for r in rows]

    async def list_applied(
        self, user_id: uuid.UUID
    ) -> list[tuple[ApplicationRow, str, str, str, str]]:
        applied_statuses = ("applied_manual", "auto_applied")
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(
                        ApplicationRow, JobRow.title, JobRow.company, JobRow.location, JobRow.url
                    )
                    .join(JobRow, ApplicationRow.job_id == JobRow.id)
                    .where(
                        ApplicationRow.user_id == user_id,
                        ApplicationRow.status.in_(applied_statuses),
                    )
                    .order_by(ApplicationRow.created_at.desc())
                )
            ).all()
        return [(r.ApplicationRow, r.title, r.company, r.location, r.url) for r in rows]

    async def update_with_tailoring(
        self, app_id: uuid.UUID, tailored_resume: str, status: str
    ) -> None:
        async with self._sf() as s, s.begin():
            await s.execute(
                update(ApplicationRow)
                .where(ApplicationRow.id == app_id)
                .values(status=status, form_fields_snapshot={"tailored_resume": tailored_resume})
            )

    async def list_queued(
        self, user_id: uuid.UUID
    ) -> list[tuple[ApplicationRow, str, str, str, str]]:
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(
                        ApplicationRow, JobRow.title, JobRow.company, JobRow.location, JobRow.url
                    )
                    .join(JobRow, ApplicationRow.job_id == JobRow.id)
                    .where(ApplicationRow.user_id == user_id, ApplicationRow.status == "queued")
                    .order_by(ApplicationRow.created_at.desc())
                )
            ).all()
        return [(r.ApplicationRow, r.title, r.company, r.location, r.url) for r in rows]

    async def list_submitted(
        self, user_id: uuid.UUID
    ) -> list[tuple[ApplicationRow, str, str, str, str]]:
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(
                        ApplicationRow, JobRow.title, JobRow.company, JobRow.location, JobRow.url
                    )
                    .join(JobRow, ApplicationRow.job_id == JobRow.id)
                    .where(ApplicationRow.user_id == user_id, ApplicationRow.status != "queued")
                    .order_by(ApplicationRow.created_at.desc())
                )
            ).all()
        return [(r.ApplicationRow, r.title, r.company, r.location, r.url) for r in rows]

    async def update_status(self, app_id: uuid.UUID, status: str) -> None:
        async with self._sf() as s, s.begin():
            await s.execute(
                update(ApplicationRow).where(ApplicationRow.id == app_id).values(status=status)
            )

    async def update_submission(
        self,
        app_id: uuid.UUID,
        status: str,
        ats_confirmation_id: str | None = None,
        submitted_at: datetime | None = None,
        response_text: str | None = None,
        screenshot_path: str | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if ats_confirmation_id:
            values["ats_confirmation_id"] = ats_confirmation_id
        if submitted_at:
            values["submitted_at"] = submitted_at
        if response_text:
            values["response_text"] = response_text
        if screenshot_path:
            values["screenshot_path"] = screenshot_path
        async with self._sf() as s, s.begin():
            await s.execute(
                update(ApplicationRow).where(ApplicationRow.id == app_id).values(**values)
            )

    async def counts(self, user_id: uuid.UUID) -> dict[str, int]:
        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(ApplicationRow.status, func.count().label("cnt"))
                    .where(ApplicationRow.user_id == user_id)
                    .group_by(ApplicationRow.status)
                )
            ).all()
        return {r.status: r.cnt for r in rows}

    async def exists(self, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
        async with self._sf() as s:
            result = await s.scalar(
                select(ApplicationRow.id).where(
                    ApplicationRow.user_id == user_id,
                    ApplicationRow.job_id == job_id,
                )
            )
        return result is not None

    async def get_by_id(self, app_id: uuid.UUID) -> ApplicationRow | None:
        async with self._sf() as s:
            result = await s.scalar(select(ApplicationRow).where(ApplicationRow.id == app_id))
        return result
