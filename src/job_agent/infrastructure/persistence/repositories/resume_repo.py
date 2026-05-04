from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from job_agent.infrastructure.persistence.models import UserResumeRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class UserResumeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_for_user(self, user_id: uuid.UUID) -> list[UserResumeRow]:
        async with self._sf() as s:
            rows = (
                await s.scalars(
                    select(UserResumeRow)
                    .where(UserResumeRow.user_id == user_id)
                    .order_by(UserResumeRow.is_primary.desc(), UserResumeRow.created_at.desc())
                )
            ).all()
        return list(rows)

    async def get_primary(self, user_id: uuid.UUID) -> UserResumeRow | None:
        async with self._sf() as s:
            row = await s.scalar(
                select(UserResumeRow).where(
                    UserResumeRow.user_id == user_id, UserResumeRow.is_primary.is_(True)
                )
            )
        return row

    async def get_by_id(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> UserResumeRow | None:
        async with self._sf() as s:
            return await s.scalar(
                select(UserResumeRow).where(
                    UserResumeRow.id == resume_id,
                    UserResumeRow.user_id == user_id,
                )
            )

    async def create(
        self,
        user_id: uuid.UUID,
        name: str,
        file_ext: str,
        file_data: bytes,
        resume_text: str,
        set_primary: bool = False,
    ) -> UserResumeRow:
        async with self._sf() as s, s.begin():
            if set_primary:
                await s.execute(
                    update(UserResumeRow)
                    .where(UserResumeRow.user_id == user_id)
                    .values(is_primary=False)
                )
            row = UserResumeRow(
                id=uuid.uuid4(),
                user_id=user_id,
                name=name,
                file_ext=file_ext,
                file_data=file_data,
                resume_text=resume_text,
                is_primary=set_primary,
                created_at=datetime.now(UTC),
            )
            s.add(row)
        return row

    async def set_primary(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> None:
        async with self._sf() as s, s.begin():
            await s.execute(
                update(UserResumeRow)
                .where(UserResumeRow.user_id == user_id)
                .values(is_primary=False)
            )
            await s.execute(
                update(UserResumeRow)
                .where(UserResumeRow.id == resume_id, UserResumeRow.user_id == user_id)
                .values(is_primary=True)
            )

    async def delete(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> None:
        async with self._sf() as s, s.begin():
            row = await s.scalar(
                select(UserResumeRow).where(
                    UserResumeRow.id == resume_id,
                    UserResumeRow.user_id == user_id,
                )
            )
            if row:
                await s.delete(row)
