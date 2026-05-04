"""Wire concrete adapters to ports at startup.

All high-level code depends on the domain abstractions; concrete types are
resolved here and nowhere else. Adding a new source means adding one entry
in this file — nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from job_agent.application.use_cases.discover_jobs import DiscoverJobsUseCase
from job_agent.application.use_cases.load_profile import LoadProfileUseCase
from job_agent.application.use_cases.match_jobs import MatchJobsUseCase
from job_agent.application.use_cases.tailor_and_apply import TailorAndApplyUseCase
from job_agent.domain.services.matching import MatchingService
from job_agent.infrastructure.auth.google_oauth import GoogleOAuthAdapter
from job_agent.infrastructure.billing.local_billing import LocalBillingService
from job_agent.infrastructure.embeddings.encoder import EmbeddingEncoder
from job_agent.infrastructure.llm.anthropic_client import AnthropicClient
from job_agent.infrastructure.persistence.database import build_engine
from job_agent.infrastructure.persistence.repositories import (
    ApplicationRepository,
    JobRepository,
    LLMCallRepository,
    MatchRepository,
    ProfileRepository,
    UserRepository,
    UserResumeRepository,
)
from job_agent.infrastructure.sources.greenhouse import GreenhouseSource
from job_agent.infrastructure.sources.lever import LeverSource

if TYPE_CHECKING:
    from job_agent.config import Settings
    from job_agent.domain.ports.job_source import JobSourcePort


@dataclass(frozen=True)
class Container:
    """Fully assembled dependency graph. Passed to entry points (API, CLI, worker)."""

    settings: Settings

    # Infrastructure
    user_repo: UserRepository
    profile_repo: ProfileRepository
    llm_call_repo: LLMCallRepository
    job_repo: JobRepository
    match_repo: MatchRepository
    application_repo: ApplicationRepository
    resume_repo: UserResumeRepository
    llm: AnthropicClient
    oauth: GoogleOAuthAdapter
    billing: LocalBillingService
    encoder: EmbeddingEncoder

    # Use cases
    load_profile: LoadProfileUseCase
    discover_jobs: DiscoverJobsUseCase
    match_jobs: MatchJobsUseCase
    tailor_and_apply: TailorAndApplyUseCase


def build_container(settings: Settings) -> Container:
    """Instantiate every concrete adapter and wire them together."""
    write_factory, read_factory = build_engine(settings)

    user_repo = UserRepository(write_factory)
    profile_repo = ProfileRepository(write_factory)
    llm_call_repo = LLMCallRepository(write_factory)
    job_repo = JobRepository(write_factory)
    match_repo = MatchRepository(write_factory)
    application_repo = ApplicationRepository(write_factory)
    resume_repo = UserResumeRepository(write_factory)

    llm = AnthropicClient(settings, llm_call_repo)
    oauth = GoogleOAuthAdapter(settings, user_repo)
    billing = LocalBillingService()
    encoder = EmbeddingEncoder()

    sources: dict[str, JobSourcePort] = {
        "greenhouse": GreenhouseSource(),
        "lever": LeverSource(),
    }

    matching_service = MatchingService(encoder=encoder, llm=llm)

    load_profile = LoadProfileUseCase(user_repo, profile_repo, llm)
    discover_jobs = DiscoverJobsUseCase(sources, job_repo)
    tailor_and_apply = TailorAndApplyUseCase(
        profile_repo=profile_repo,
        job_repo=job_repo,
        application_repo=application_repo,
        llm=llm,
        resume_repo=resume_repo,
    )
    match_jobs = MatchJobsUseCase(
        profile_repo=profile_repo,
        job_repo=job_repo,
        match_repo=match_repo,
        encoder=encoder,
        matching_service=matching_service,
    )

    return Container(
        settings=settings,
        user_repo=user_repo,
        profile_repo=profile_repo,
        llm_call_repo=llm_call_repo,
        job_repo=job_repo,
        match_repo=match_repo,
        application_repo=application_repo,
        resume_repo=resume_repo,
        llm=llm,
        oauth=oauth,
        billing=billing,
        encoder=encoder,
        load_profile=load_profile,
        discover_jobs=discover_jobs,
        match_jobs=match_jobs,
        tailor_and_apply=tailor_and_apply,
    )
