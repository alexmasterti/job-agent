from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Match(BaseModel):
    """Result of running the scoring pipeline for one (user, job) pair."""

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID

    embedding_score: float = Field(ge=0.0, le=1.0)
    llm_score: float = Field(ge=0.0, le=100.0)
    hard_requirement_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=100.0)

    reasoning: str
    flags: list[str] = Field(default_factory=list)

    scored_at: datetime
