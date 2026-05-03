"""Async SQLAlchemy engine + session factory with read/write session distinction."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from job_agent.config import Settings


def build_engine(settings: Settings) -> tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]]:
    """Return (write_factory, read_factory). Both point to the same DB for now.

    When a read replica is provisioned, swap read_factory's URL without touching call sites.
    """
    engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=5,
        echo=settings.app_env == "development",
    )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    return factory, factory


@asynccontextmanager
async def unit_of_work(session_factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    """Context manager that owns a single transaction.

    Services call this instead of managing commits/rollbacks themselves.
    On exception, rolls back; on clean exit, commits.
    """
    async with session_factory() as session:
        async with session.begin():
            yield session
