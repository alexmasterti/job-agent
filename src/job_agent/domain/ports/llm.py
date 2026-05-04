from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import uuid


@runtime_checkable
class LLMPort(Protocol):
    """Abstraction over any LLM provider. Domain code never imports anthropic directly."""

    async def complete(
        self,
        *,
        user_id: uuid.UUID,
        purpose: str,
        system: str,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        """Send a prompt and return the text completion.

        Implementations must:
        - Log every call to the llm_calls table.
        - Enforce the per-user daily budget before sending.
        - Raise BudgetExceededError if the cap would be breached.
        """
        ...

    async def embed(self, text: str) -> list[float]:
        """Return a dense embedding vector for *text*.

        Used for semantic similarity scoring. May delegate to a local model
        to avoid per-token cost.
        """
        ...

    async def smoke_test(self) -> dict[str, Any]:
        """Call the cheapest model with a trivial prompt. Returns latency + token counts."""
        ...
