from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from job_agent.domain.models.application import Application
    from job_agent.domain.models.profile import Profile


@runtime_checkable
class JobSubmitterPort(Protocol):
    """Write port: submits a fully prepared application to an ATS."""

    ats_type: str

    async def submit(self, application: Application, profile: Profile) -> Application:
        """Submit *application* and return an updated copy with ATS confirmation data.

        Implementations must be idempotent — check the ATS for an existing
        submission before sending.
        """
        ...


@runtime_checkable
class EasyApplyDrafterPort(Protocol):
    """Prepare-only port for ATS types where auto-submit is disallowed (e.g. LinkedIn).

    Never calls the final submit action. Returns the application in
    *pending_human_review* status with a screenshot attached.
    """

    ats_type: str

    async def draft(self, application: Application, profile: Profile) -> Application:
        """Fill out the form up to the final submit button, capture a screenshot,
        and return the application in *pending_human_review* state.
        """
        ...
