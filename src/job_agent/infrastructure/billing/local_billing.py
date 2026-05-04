from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


class LocalBillingService:
    """No-op billing adapter — every user is allowed everything (all are pro tier).

    Swap in StripeBillingService when monetization is needed.
    """

    async def can_use(self, user_id: uuid.UUID, feature: str) -> bool:
        return True
