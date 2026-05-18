"""Minimal async OpenRouter client."""
from __future__ import annotations
import asyncio
import logging
from openai import AsyncOpenAI
from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    PRIMARY_TIMEOUT,
    FALLBACK_TIMEOUT,
)

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """Raised when no model is reachable (after all retries)."""


class LLMRouter:
    """Completions router with primary/fallback model.

    Simple instead of complex — no streaming, no function calling,
    no per-request model override.  Designed for controlled grounding
    where we pass a full prompt and expect tagged structured text.
    """

    def __init__(self) -> None:
        if not OPENROUTER_API_KEY:
            logger.warning(
                "OPENROUTER_API_KEY not set; router will fail at call time."
            )
        self._client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            timeout=PRIMARY_TIMEOUT,
        )

    async def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.3,
    ) -> str:
        """Return the completed text, trying primary then fallback."""
        for model, timeout in (
            (PRIMARY_MODEL, PRIMARY_TIMEOUT),
            (FALLBACK_MODEL, FALLBACK_TIMEOUT),
        ):
            try:
                self._client.timeout = timeout
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:
                logger.warning("Model %s failed: %s", model, exc)
        raise LLMUnavailableError("All models unavailable")
