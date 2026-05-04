from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import uuid


@runtime_checkable
class BillingPort(Protocol):
    """Feature-gate abstraction. Current adapter always returns True (all users are pro).

    A future StripeBillingService adapter swaps in here when monetization lands.
    """

    async def can_use(self, user_id: uuid.UUID, feature: str) -> bool:
        """Return True if *user_id* is allowed to use *feature* under their current tier."""
        ...
