from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class Job(BaseModel):
    """A discovered job posting. Stable hash ensures idempotent discovery."""

    id: uuid.UUID
    user_id: uuid.UUID
    source: str
    external_id: str
    content_hash: str

    title: str
    company: str
    location: str
    remote: bool = False
    url: str
    description: str
    ats_type: str = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None

    discovered_at: datetime
