from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PreferredLocation(BaseModel):
    """A preferred location with a search radius in miles."""

    name: str
    radius_miles: float = 50.0


class LocationPreference(BaseModel):
    """A location pattern with a score weight (positive = boost, negative = penalty)."""

    pattern: str
    weight: float = 0.0


class ScheduleConstraint(BaseModel):
    """Free-form constraint the LLM judge uses when evaluating a job description."""

    description: str


class StackAlignment(BaseModel):
    strong_match: list[str] = Field(default_factory=list)
    weak_match: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class Compensation(BaseModel):
    min_base_salary_usd: int = 0
    min_total_comp_usd: int = 0
    currency: str = "USD"
    equity_required: bool = False


class WorkAuthorization(BaseModel):
    country: str = "US"
    status: str = "citizen"
    requires_sponsorship: bool = False


class RoleTarget(BaseModel):
    title_pattern: str
    level: str = "senior"
    weight: float = 0.0


class Profile(BaseModel):
    """Master user profile. Every field is generic — no user-specific values hardcoded."""

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # Raw resume text extracted from the PDF/DOCX
    resume_text: str = ""

    # Structured fields populated by the parser and refined by the user
    full_name: str = ""
    headline: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[dict[str, str]] = Field(default_factory=list)

    # Location / remote preferences (user-editable)
    preferred_locations: list[PreferredLocation] = Field(default_factory=list)
    # "remote_only" | "hybrid_ok" | "any"
    remote_preference: str = "any"
    # Minimum match score (0-100) to show in the Matched tab
    min_match_score: int = 0

    @field_validator("preferred_locations", mode="before")
    @classmethod
    def _normalize_locations(cls, v: Any) -> list[dict[str, Any]]:
        """Accept both old list[str] and new list[dict] formats from DB."""
        if not isinstance(v, list):
            return []
        result: list[dict[str, Any]] = []
        for item in v:
            if isinstance(item, str):
                result.append({"name": item, "radius_miles": 50.0})
            elif isinstance(item, dict):
                result.append(item)
            else:
                result.append({"name": str(item), "radius_miles": 50.0})
        return result

    # Matching preferences (advanced)
    location_preferences: list[LocationPreference] = Field(default_factory=list)
    schedule_constraints: list[ScheduleConstraint] = Field(default_factory=list)
    stack_alignment: StackAlignment = Field(default_factory=StackAlignment)
    compensation: Compensation = Field(default_factory=Compensation)
    work_authorization: WorkAuthorization = Field(default_factory=WorkAuthorization)
    role_targets: list[RoleTarget] = Field(default_factory=list)
    industry_preferences: list[dict[str, float]] = Field(default_factory=list)
    hard_filters: list[str] = Field(default_factory=list)

    # Safety / exclusion
    current_employer: str = ""
    competitors_to_exclude: list[str] = Field(default_factory=list)
