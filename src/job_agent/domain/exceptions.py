from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain exceptions."""


class UserNotAllowedError(DomainError):
    """Email is not in the ALLOWED_GOOGLE_EMAILS list."""


class UserNotFoundError(DomainError):
    """No user row found for the given identifier."""


class ProfileNotFoundError(DomainError):
    """No profile exists for the user."""


class BudgetExceededError(DomainError):
    """Daily LLM spend cap reached for this user."""


class DuplicateJobError(DomainError):
    """Job with this content hash already exists for the user."""


class MatchBelowThresholdError(DomainError):
    """Match score did not meet the minimum threshold."""


class TruthfulnessViolationError(DomainError):
    """Tailored resume introduced claims not present in the source profile."""


class ApplicationExistsError(DomainError):
    """An application to this job already exists for the user."""


class AgentPausedError(DomainError):
    """Worker is paused; no external actions are allowed."""


class DailyCapExceededError(DomainError):
    """Daily application submission cap reached."""


class CompanyExcludedError(DomainError):
    """Company is on the user's exclusion list."""
