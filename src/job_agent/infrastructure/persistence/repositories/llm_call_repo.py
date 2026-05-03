from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from job_agent.infrastructure.persistence.models import LLMCallRow


class LLMCallRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def log_call(
        self,
        *,
        user_id: uuid.UUID,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        request_hash: str,
    ) -> None:
        async with self._sf() as s:
            async with s.begin():
                s.add(
                    LLMCallRow(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        model=model,
                        purpose=purpose,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_usd,
                        request_hash=request_hash,
                    )
                )

    async def today_spend(self, user_id: uuid.UUID) -> float:
        today = datetime.now(timezone.utc).date()
        async with self._sf() as s:
            result = await s.scalar(
                select(func.coalesce(func.sum(LLMCallRow.cost_usd), 0.0)).where(
                    LLMCallRow.user_id == user_id,
                    func.date(LLMCallRow.created_at) == today,
                )
            )
        return float(result or 0.0)
