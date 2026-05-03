from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_agent.domain.models.user import User, UserTier
from job_agent.infrastructure.persistence.models import UserRow


class UserRepository:
    """Concrete SQLAlchemy implementation of UserRepositoryPort."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_by_email(self, email: str) -> User | None:
        async with self._sf() as s:
            row = await s.scalar(select(UserRow).where(UserRow.email == email))
        return _to_domain(row) if row else None

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        async with self._sf() as s:
            row = await s.scalar(select(UserRow).where(UserRow.google_sub == google_sub))
        return _to_domain(row) if row else None

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        async with self._sf() as s:
            row = await s.get(UserRow, user_id)
        return _to_domain(row) if row else None

    async def upsert(self, user: User) -> User:
        async with self._sf() as s:
            async with s.begin():
                existing = await s.scalar(
                    select(UserRow).where(UserRow.google_sub == user.google_sub)
                )
                if existing:
                    existing.email = user.email
                    existing.tier = user.tier.value
                    existing.is_active = user.is_active
                    row = existing
                else:
                    row = UserRow(
                        id=user.id,
                        email=user.email,
                        google_sub=user.google_sub,
                        tier=user.tier.value,
                        is_active=user.is_active,
                        created_at=user.created_at,
                    )
                    s.add(row)
        return _to_domain(row)


def _to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        google_sub=row.google_sub,
        tier=UserTier(row.tier),
        is_active=row.is_active,
        created_at=row.created_at,
    )
