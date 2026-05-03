"""Anthropic SDK adapter. Wraps every call with cost tracking and budget enforcement."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

import anthropic
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from job_agent.config import Settings
from job_agent.domain.exceptions import BudgetExceeded
from job_agent.infrastructure.persistence.repositories.llm_call_repo import LLMCallRepository

log = structlog.get_logger()

# Cost per 1M tokens (USD) — update when Anthropic changes pricing
_COST_TABLE: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}

_DEFAULT_HAIKU = "claude-haiku-4-5-20251001"
_DEFAULT_SONNET = "claude-sonnet-4-6"


class AnthropicClient:
    """Thin adapter over the Anthropic SDK implementing LLMPort."""

    def __init__(self, settings: Settings, llm_call_repo: LLMCallRepository) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._daily_budget = settings.llm_daily_budget_usd
        self._repo = llm_call_repo

    @retry(
        retry=retry_if_exception_type(anthropic.RateLimitError),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5),
    )
    async def complete(
        self,
        *,
        user_id: uuid.UUID,
        purpose: str,
        system: str,
        prompt: str,
        model: str = _DEFAULT_SONNET,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        """Call the model and return the completion text.

        Checks per-user budget before every call. Logs the call regardless of outcome.
        """
        await self._assert_budget(user_id)

        request_hash = _hash(system + prompt + model)
        t0 = time.monotonic()

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        elapsed = time.monotonic() - t0
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        cost = _compute_cost(model, in_tok, out_tok)
        text = response.content[0].text  # type: ignore[union-attr]

        await self._repo.log_call(
            user_id=user_id,
            model=model,
            purpose=purpose,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            request_hash=request_hash,
        )

        log.info(
            "llm.complete",
            model=model,
            purpose=purpose,
            user_id=str(user_id),
            in_tokens=in_tok,
            out_tokens=out_tok,
            cost_usd=round(cost, 5),
            elapsed_s=round(elapsed, 2),
        )

        return text

    async def embed(self, text: str) -> list[float]:
        """Embedding is handled by the local sentence-transformers model, not Anthropic.

        This method exists so the adapter satisfies LLMPort; the real embedding logic
        lives in infrastructure/embeddings/.
        """
        raise NotImplementedError("Use EmbeddingAdapter for embeddings — no API cost.")

    async def smoke_test(self) -> dict[str, Any]:
        """Quick connectivity check using Haiku (cheapest model)."""
        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=_DEFAULT_HAIKU,
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
        elapsed = time.monotonic() - t0
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        return {
            "model": _DEFAULT_HAIKU,
            "latency_s": round(elapsed, 3),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": _compute_cost(_DEFAULT_HAIKU, in_tok, out_tok),
            "response": response.content[0].text,  # type: ignore[union-attr]
        }

    async def _assert_budget(self, user_id: uuid.UUID) -> None:
        spent = await self._repo.today_spend(user_id)
        if spent >= self._daily_budget:
            raise BudgetExceeded(
                f"Daily LLM budget ${self._daily_budget:.2f} reached "
                f"(spent ${spent:.2f}) for user {user_id}"
            )


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _COST_TABLE.get(model, (3.00, 15.00))
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
