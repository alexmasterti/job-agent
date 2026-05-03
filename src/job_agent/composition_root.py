"""Wire concrete adapters to ports at startup.

All high-level code depends on the domain abstractions; concrete types are
resolved here and nowhere else. Adding a new source means adding one entry
in this file — nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from job_agent.application.use_cases.load_profile import LoadProfileUseCase
from job_agent.config import Settings
from job_agent.infrastructure.auth.google_oauth import GoogleOAuthAdapter
from job_agent.infrastructure.billing.local_billing import LocalBillingService
from job_agent.infrastructure.llm.anthropic_client import AnthropicClient
from job_agent.infrastructure.persistence.database import build_engine
from job_agent.infrastructure.persistence.repositories import (
    LLMCallRepository,
    ProfileRepository,
    UserRepository,
)


@dataclass(frozen=True)
class Container:
    """Fully assembled dependency graph. Passed to entry points (API, CLI, worker)."""

    settings: Settings

    # Infrastructure
    user_repo: UserRepository
    profile_repo: ProfileRepository
    llm_call_repo: LLMCallRepository
    llm: AnthropicClient
    oauth: GoogleOAuthAdapter
    billing: LocalBillingService

    # Use cases
    load_profile: LoadProfileUseCase


def build_container(settings: Settings) -> Container:
    """Instantiate every concrete adapter and wire them together."""
    write_factory, read_factory = build_engine(settings)

    user_repo = UserRepository(write_factory)
    profile_repo = ProfileRepository(write_factory)
    llm_call_repo = LLMCallRepository(write_factory)

    llm = AnthropicClient(settings, llm_call_repo)
    oauth = GoogleOAuthAdapter(settings, user_repo)
    billing = LocalBillingService()

    load_profile = LoadProfileUseCase(user_repo, profile_repo, llm)

    return Container(
        settings=settings,
        user_repo=user_repo,
        profile_repo=profile_repo,
        llm_call_repo=llm_call_repo,
        llm=llm,
        oauth=oauth,
        billing=billing,
        load_profile=load_profile,
    )
