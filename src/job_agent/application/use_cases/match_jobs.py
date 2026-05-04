"""MatchJobsUseCase — runs the full scoring pipeline for all unmatched jobs."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import structlog

from job_agent.domain.models.job import Job
from job_agent.domain.models.match import Match
from job_agent.domain.models.profile import Profile
from job_agent.domain.services.matching import MatchingService
from job_agent.infrastructure.embeddings.encoder import EmbeddingEncoder
from job_agent.infrastructure.persistence.repositories.job_repo import JobRepository
from job_agent.infrastructure.persistence.repositories.match_repo import MatchRepository
from job_agent.infrastructure.persistence.repositories.profile_repo import ProfileRepository

log = structlog.get_logger()

_LLM_CONCURRENCY = 5  # max simultaneous Haiku calls


@dataclass
class MatchResult:
    scored: int
    saved: int
    filtered: int
    skipped_low_embedding: int


class MatchJobsUseCase:
    def __init__(
        self,
        profile_repo: ProfileRepository,
        job_repo: JobRepository,
        match_repo: MatchRepository,
        encoder: EmbeddingEncoder,
        matching_service: MatchingService,
    ) -> None:
        self._profile_repo = profile_repo
        self._job_repo = job_repo
        self._match_repo = match_repo
        self._encoder = encoder
        self._matching = matching_service

    async def execute(
        self,
        user_id: uuid.UUID,
        limit: int = 500,
        min_score: float = 0.0,
    ) -> MatchResult:
        profile = await self._profile_repo.get_by_user(user_id)
        if not profile:
            raise ValueError("No profile found. Run: job-agent profile load")

        all_jobs = await self._job_repo.list_unmatched(user_id, limit=limit)
        already_scored = await self._match_repo.get_scored_job_ids(user_id)
        jobs = [j for j in all_jobs if j.id not in already_scored]

        if not jobs:
            log.info("match.no_new_jobs")
            return MatchResult(scored=0, saved=0, filtered=0, skipped_low_embedding=0)

        log.info("match.start", total_jobs=len(jobs))

        profile_text = _profile_to_text(profile)
        profile_emb = self._encoder.encode(profile_text)

        job_texts = [f"{j.title} {j.description[:2000]}" for j in jobs]
        log.info("match.encoding_jobs", count=len(job_texts))
        job_embs = self._encoder.encode_batch(job_texts)

        sem = asyncio.Semaphore(_LLM_CONCURRENCY)
        matches, filtered, skipped = await self._score_all(
            user_id, profile, jobs, profile_emb, job_embs, sem
        )

        saved = await self._match_repo.save_many(matches)
        log.info("match.done", scored=len(matches), saved=saved, filtered=filtered, skipped=skipped)
        return MatchResult(scored=len(matches), saved=saved, filtered=filtered, skipped_low_embedding=skipped)

    async def _score_all(
        self,
        user_id: uuid.UUID,
        profile: Profile,
        jobs: list[Job],
        profile_emb: list[float],
        job_embs: list[list[float]],
        sem: asyncio.Semaphore,
    ) -> tuple[list[Match], int, int]:
        async def _score_one(job: Job, job_emb: list[float]) -> Match | None:
            async with sem:
                return await self._matching.score(user_id, profile, job, job_emb, profile_emb)

        tasks = [_score_one(job, emb) for job, emb in zip(jobs, job_embs)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        matches: list[Match] = []
        filtered = 0
        skipped = 0

        for job, result in zip(jobs, results):
            if isinstance(result, Exception):
                log.warning("match.score_error", job_id=str(job.id), error=str(result))
            elif result is None:
                passes, _ = self._matching.passes_hard_filters(profile, job)
                if not passes:
                    filtered += 1
                else:
                    skipped += 1
            else:
                matches.append(result)

        return matches, filtered, skipped


def _profile_to_text(profile: Profile) -> str:
    from job_agent.domain.services.matching import _profile_to_text as _pt
    return _pt(profile)
