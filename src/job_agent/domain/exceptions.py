from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain exceptions."""


class UserNotAllowed(DomainError):
    """Email is not in the ALLOWED_GOOGLE_EMAILS list."""


class UserNotFound(DomainError):
    """No user row found for the given identifier."""


class ProfileNotFound(DomainError):
    """No profile exists for the user."""


class BudgetExceeded(DomainError):
    """Daily LLM spend cap reached for this user."""


class DuplicateJob(DomainError):
    """Job with this content hash already exists for the user."""


class MatchBelowThreshold(DomainError):
    """Match score did not meet the minimum threshold."""


class TruthfulnessViolation(DomainError):
    """Tailored resume introduced claims not present in the source profile."""


class ApplicationExists(DomainError):
    """An application to this job already exists for the user."""


class AgentPaused(DomainError):
    """Worker is paused; no external actions are allowed."""


class DailyCapExceeded(DomainError):
    """Daily application submission cap reached."""


class CompanyExcluded(DomainError):
    """Company is on the user's exclusion list."""
