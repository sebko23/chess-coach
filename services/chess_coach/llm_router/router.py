"""Minimal async OpenRouter client."""
from __future__ import annotations
import logging
from openai import AsyncOpenAI
from .config import (
    OPENROUTER_BASE_URL,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    PRIMARY_TIMEOUT,
    FALLBACK_TIMEOUT,
    get_api_key,
)

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """Raised when no model is reachable (after all retries)."""


class LLMRouter:
    """Completions router with primary/fallback model.

    Accepts a full ``messages`` list (OpenAI chat format) so callers
    can express multi-turn conversations, not just single system+user pairs.

    The underlying ``AsyncOpenAI`` client is created lazily on the first
    ``complete()`` call so the gateway can boot and serve engine analysis
    even when ``OPENROUTER_API_KEY`` is not set.
    """

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    async def _get_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client
        if not get_api_key():
            raise LLMUnavailableError(
                "OPENROUTER_API_KEY is not set. Set the environment variable "
                "or add it to .env at the project root."
            )
        self._client = AsyncOpenAI(
            api_key=get_api_key(),
            base_url=OPENROUTER_BASE_URL,
            timeout=PRIMARY_TIMEOUT,
        )
        return self._client

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 800,
        temperature: float = 0.3,
    ) -> str:
        """Return the completed text, trying primary then fallback."""
        client = await self._get_client()
        for model, timeout in (
            (PRIMARY_MODEL, PRIMARY_TIMEOUT),
            (FALLBACK_MODEL, FALLBACK_TIMEOUT),
        ):
            try:
                client.timeout = timeout
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:
                logger.warning("Model %s failed: %s", model, exc)
        raise LLMUnavailableError("All models unavailable")
