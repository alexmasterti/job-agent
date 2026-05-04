"""Matching pipeline: hard filters → embedding similarity → LLM judge → final score.

Each stage is deliberately cheap-to-expensive so most jobs never reach the LLM.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from job_agent.domain.models.match import Match

if TYPE_CHECKING:
    from job_agent.domain.models.job import Job
    from job_agent.domain.models.profile import Profile

log = structlog.get_logger()

_EMBEDDING_THRESHOLD = 0.25  # cosine similarity below this → skip LLM entirely
_HAIKU = "claude-haiku-4-5-20251001"

_JUDGE_SYSTEM = """\
You are a technical recruiter evaluating candidate fit. Be direct and calibrated.
Respond ONLY with valid JSON — no markdown, no explanation outside the JSON object."""

_JUDGE_PROMPT = """\
Evaluate this candidate's fit for the job posting.

## Candidate Profile
{profile_text}

## Job Posting
Title: {title}
Company: {company}
Location: {location}

{description}

## Task
Return a JSON object with exactly these keys:
- "fit_score": integer 0-100 (overall fit based on skills, experience level, and role alignment)
- "hard_score": float 0.0-1.0 (fraction of job's must-have requirements the candidate clearly meets)
- "reasoning": string of 2-3 sentences explaining the score, noting key matches and gaps

Example: {{"fit_score": 72, "hard_score": 0.8, "reasoning": "Strong .NET background aligns well..."}}"""


class MatchingService:
    """Scores a (profile, job) pair and returns a Match or None if filtered/below threshold."""

    def __init__(self, encoder: object, llm: object) -> None:
        self._encoder = encoder  # type: ignore[assignment]
        self._llm = llm  # type: ignore[assignment]

    def passes_hard_filters(self, profile: Profile, job: Job) -> tuple[bool, list[str]]:
        """Check exclusion rules. Returns (passes, list_of_triggered_flags)."""
        flags: list[str] = []
        combined = f"{job.title} {job.company} {job.description}".lower()

        if profile.current_employer and profile.current_employer.lower() in job.company.lower():
            flags.append(f"current_employer:{profile.current_employer}")

        for excl in profile.competitors_to_exclude:
            if excl.lower() in job.company.lower():
                flags.append(f"competitor:{excl}")

        for pattern in profile.hard_filters:
            if re.search(pattern, combined, re.IGNORECASE):
                flags.append(f"hard_filter:{pattern}")

        return len(flags) == 0, flags

    async def score(
        self,
        user_id: uuid.UUID,
        profile: Profile,
        job: Job,
        job_embedding: list[float],
        profile_embedding: list[float],
    ) -> Match | None:
        passes, flags = self.passes_hard_filters(profile, job)
        if not passes:
            log.debug("match.filtered", job_id=str(job.id), flags=flags)
            return None

        embedding_score = self._encoder.cosine(profile_embedding, job_embedding)  # type: ignore[attr-defined]
        if embedding_score < _EMBEDDING_THRESHOLD:
            return None

        llm_score, hard_score, reasoning = await self._llm_judge(user_id, profile, job)

        final_score = 0.4 * embedding_score * 100 + 0.4 * llm_score + 0.2 * hard_score * 100

        return Match(
            id=uuid.uuid4(),
            user_id=user_id,
            job_id=job.id,
            embedding_score=embedding_score,
            llm_score=llm_score,
            hard_requirement_score=hard_score,
            final_score=round(final_score, 2),
            reasoning=reasoning,
            flags=flags,
            scored_at=datetime.now(UTC),
        )

    async def _llm_judge(
        self,
        user_id: uuid.UUID,
        profile: Profile,
        job: Job,
    ) -> tuple[float, float, str]:
        profile_text = _profile_to_text(profile)
        prompt = _JUDGE_PROMPT.format(
            profile_text=profile_text,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description[:1500],
        )
        try:
            raw = await self._llm.complete(  # type: ignore[attr-defined]
                user_id=user_id,
                purpose="match_judge",
                system=_JUDGE_SYSTEM,
                prompt=prompt,
                model=_HAIKU,
                max_tokens=256,
                temperature=0.1,
            )
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(cleaned)
            fit = float(data.get("fit_score", 50))
            hard = float(data.get("hard_score", 0.5))
            reasoning = str(data.get("reasoning", ""))
            return fit, hard, reasoning
        except Exception as exc:
            log.warning("match.llm_judge_failed", job_id=str(job.id), error=str(exc))
            return 50.0, 0.5, "LLM judge unavailable."


def _profile_to_text(profile: Profile) -> str:
    parts: list[str] = []
    if profile.full_name:
        parts.append(f"Name: {profile.full_name}")
    if profile.headline:
        parts.append(f"Headline: {profile.headline}")
    if profile.summary:
        parts.append(f"Summary: {profile.summary[:500]}")
    if profile.skills:
        parts.append(f"Skills: {', '.join(profile.skills[:40])}")
    if profile.stack_alignment.strong_match:
        parts.append(f"Strong stack: {', '.join(profile.stack_alignment.strong_match)}")
    if profile.stack_alignment.avoid:
        parts.append(f"Avoid: {', '.join(profile.stack_alignment.avoid)}")
    for exp in profile.experience[:3]:
        title = exp.get("title", "")
        company = exp.get("company", "")
        desc = str(exp.get("description", ""))[:200]
        if title:
            parts.append(f"Role: {title} at {company} — {desc}")
    if not parts and profile.resume_text:
        parts.append(profile.resume_text[:1000])
    return "\n".join(parts)
