from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ApplicationStatus(StrEnum):
    applying = "applying"
    applied_manual = "applied_manual"
    auto_applied = "auto_applied"
    pending_human_review = "pending_human_review"
    queued = "queued"
    submitted = "submitted"
    replied = "replied"
    interview_requested = "interview_requested"
    interview_booked = "interview_booked"
    rejected = "rejected"
    ghosted = "ghosted"
    withdrawn = "withdrawn"


class Application(BaseModel):
    """Tracks a single submission, including the snapshot of what was sent."""

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID

    status: ApplicationStatus = ApplicationStatus.queued
    ats_type: str
    submission_url: str = ""

    resume_hash: str = ""
    cover_letter_hash: str = ""
    form_fields_snapshot: dict[str, str] = {}

    ats_confirmation_id: str | None = None
    screenshot_path: str | None = None
    response_text: str | None = None

    submitted_at: datetime | None = None
    replied_at: datetime | None = None
    created_at: datetime
