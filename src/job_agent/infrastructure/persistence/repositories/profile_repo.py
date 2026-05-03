from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_agent.domain.models.profile import Profile
from job_agent.infrastructure.persistence.models import ProfileRow


class ProfileRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_by_user(self, user_id: uuid.UUID) -> Profile | None:
        async with self._sf() as s:
            row = await s.scalar(select(ProfileRow).where(ProfileRow.user_id == user_id))
        return _to_domain(row) if row else None

    async def save(self, profile: Profile) -> Profile:
        async with self._sf() as s:
            async with s.begin():
                existing = await s.scalar(
                    select(ProfileRow).where(ProfileRow.user_id == profile.user_id)
                )
                if existing:
                    existing.resume_text = profile.resume_text
                    existing.data = _to_data(profile)
                    existing.updated_at = profile.updated_at
                    row = existing
                else:
                    row = ProfileRow(
                        id=profile.id,
                        user_id=profile.user_id,
                        resume_text=profile.resume_text,
                        data=_to_data(profile),
                        created_at=profile.created_at,
                        updated_at=profile.updated_at,
                    )
                    s.add(row)
        return _to_domain(row)


def _to_data(profile: Profile) -> dict:
    return profile.model_dump(
        exclude={"id", "user_id", "resume_text", "created_at", "updated_at"}
    )


def _to_domain(row: ProfileRow) -> Profile:
    return Profile(
        id=row.id,
        user_id=row.user_id,
        resume_text=row.resume_text,
        created_at=row.created_at,
        updated_at=row.updated_at,
        **row.data,
    )
