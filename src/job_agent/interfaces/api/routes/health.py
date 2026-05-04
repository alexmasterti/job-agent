from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter()


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(request: Request) -> dict[str, str]:
    """Readiness probe — returns 200 only if DB is reachable.

    Railway health checks point at this endpoint.
    """
    session_factory = request.app.state.container.user_repo._sf
    async with session_factory() as s:
        await s.execute(text("SELECT 1"))
    return {"status": "ready"}
