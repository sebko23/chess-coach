"""OCR backend dispatch and concrete backend implementations.

The backend is selected at call time via the ``CHESS_COACH_OCR_BACKEND``
environment variable. The route layer does not read this directly; it goes
through :func:`predict_fen` so the call signature is stable across backends
and the only thing future BBFs need to do is add a new backend implementation
and register it in :func:`get_backend`.

Why an env-var only (no GatewaySettings field):
    The OpenRouter API key at ``services/chess_coach/llm_router/config.py``
    follows the same pattern: env-only, lazy read at call time. The PDF
    ingestion route is not a hot path (one HTTP per page on user-triggered
    upload), so call-time env reads are cheap and avoid a GatewaySettings
    schema migration until a backend is actually selected.

Backend interface contract:
    A backend exposes an async ``predict(image_png_bytes: bytes) -> OcrResult``.
    ``OcrResult`` is a tuple ``(fen | None, confidence: float, error: str | None)``.
    Backends MUST NOT raise; they MUST return ``error`` instead so the route
    can produce structured ``DiagramResult`` rows.

Network-bound backends (currently just ``chessvision``) are additionally
wrapped by :mod:`chess_coach.pdf_ocr.protection` -- a per-process token
bucket for rate limiting and a 3-state circuit breaker that opens after
N consecutive failures and half-opens after a cooldown. See that module
for env-var configuration. The protections NEVER raise; they produce
structured ``OcrResult`` errors prefixed ``rate_limit:`` or ``circuit_open:``.
"""
from __future__ import annotations

import base64
import logging
import os
from collections.abc import Awaitable, Callable
from typing import NamedTuple

import httpx

from .protection import get_protection_registry

logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "chessvision"
CHESSVISION_URL = "http://app.chessvision.ai/predict"
CHESSVISION_TIMEOUT_SECONDS = 30
CHESSVISION_DEFAULT_CONFIDENCE = 0.9

ENV_OCR_BACKEND = "CHESS_COACH_OCR_BACKEND"

Predicter = Callable[[bytes], Awaitable["OcrResult"]]


class OcrResult(NamedTuple):
    fen: str | None
    confidence: float
    error: str | None


class UnknownOcrBackend(ValueError):
    """Raised when CHESS_COACH_OCR_BACKEND names a backend that is not registered.

    Future BBFs add backends by extending :func:`get_backend`. The route layer
    MUST NOT catch this exception; it propagates to ``/v1/import/pdf`` callers
    as a 500 because it indicates a server-side misconfiguration, not a
    per-page OCR failure.
    """


async def predict_fen(image_png_bytes: bytes) -> OcrResult:
    """Dispatch to the OCR backend selected by env at call time.

    Reads ``CHESS_COACH_OCR_BACKEND`` on every call. Cost is one ``os.getenv``;
    not worth caching. If the env var is unset or empty, falls back to
    :data:`DEFAULT_BACKEND` (``chessvision``).
    """
    backend_name = os.getenv(ENV_OCR_BACKEND) or DEFAULT_BACKEND
    backend = get_backend(backend_name)
    return await backend(image_png_bytes)


def get_backend(name: str) -> Predicter:
    """Resolve a backend name to its async predicter callable.

    Raises :class:`UnknownOcrBackend` for unregistered names. The route
    MUST treat this as a configuration error, not an OCR failure.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        valid = ", ".join(sorted(_REGISTRY))
        raise UnknownOcrBackend(
            f"unknown OCR backend {name!r}; valid values: {valid}"
        ) from exc


# ---------------------------------------------------------------------------
# chessvision.ai backend (current behavior, preserved verbatim from
# services/chess_coach/gateway/routes/pdf_ingest.py:59-80 in BBF-67.2)
# ---------------------------------------------------------------------------


async def _predict_chessvision(image_png_bytes: bytes) -> OcrResult:
    """Submit one PNG to the public chessvision.ai /predict endpoint.

    Mirrors the original ``_predict_fen`` behavior exactly so the existing
    integration test (``tests/integration/test_pdf_import.py``) keeps passing
    when it mocks this path.
    """
    b64 = base64.b64encode(image_png_bytes).decode()
    payload = {
        "board_orientation": "predict",
        "cropped": False,
        "current_player": "white",
        "image": f"data:image/png;base64,{b64}",
        "predict_turn": False,
    }
    try:
        async with httpx.AsyncClient(timeout=CHESSVISION_TIMEOUT_SECONDS) as client:
            resp = await client.post(CHESSVISION_URL, json=payload)
        if resp.status_code != 200:
            return OcrResult(None, 0.0, f"HTTP {resp.status_code}")
        data = resp.json()
        if not data.get("success"):
            return OcrResult(None, 0.0, "chessvision returned success=false")
        fen = data.get("result", "").replace("_", " ").strip()
        return OcrResult(fen or None, CHESSVISION_DEFAULT_CONFIDENCE, None)
    except Exception as exc:  # network, JSON, etc.
        return OcrResult(None, 0.0, str(exc))


async def _predict_chessvision_protected(image_png_bytes: bytes) -> OcrResult:
    """Wrap :func:`_predict_chessvision` with rate limit + circuit breaker.

    Order of checks (rate limit first, breaker second) matches the
    "shed load before testing upstream" pattern: if the bucket is empty,
    there's no point probing the breaker. The protections NEVER raise;
    a denied request becomes an ``OcrResult`` with a structured error
    string that the route surface as ``DiagramResult.issue``.

    Error-string conventions (the route may pattern-match these):
        ``rate_limit:<backend>:bucket_empty``
        ``circuit_open:<backend>:cooldown``
    """
    registry = get_protection_registry()
    if not registry.bucket_try_acquire("chessvision"):
        logger.info("chessvision: rate-limited (bucket empty)")
        return OcrResult(None, 0.0, "rate_limit:chessvision:bucket_empty")
    if not registry.breaker_should_allow("chessvision"):
        logger.info("chessvision: circuit open, short-circuit")
        return OcrResult(None, 0.0, "circuit_open:chessvision:cooldown")
    result = await _predict_chessvision(image_png_bytes)
    if result.error is None:
        registry.breaker_record_success("chessvision")
    else:
        registry.breaker_record_failure("chessvision")
    return result


# ---------------------------------------------------------------------------
# Local OCR backend (BBF-68.1 follow-up; raises a structured 501 today).
#
# The real local backend has to solve three problems chessvision hides:
#   1. board-vs-page segmentation on a chess-book PDF page (1.6 k × 2.3 k)
#   2. 8x8 grid rectification with sub-pixel accuracy
#   3. per-square piece classification into the 12 FEN_CHARS
# Candidate model survey: docs/16_audit/BBF-68.1-candidate-survey-2026-07-17.md
# ---------------------------------------------------------------------------


async def _predict_local(image_png_bytes: bytes) -> OcrResult:
    """Not yet implemented. The follow-up BBF-68.1 will replace this with a
    real local backend once the candidate model is benchmarked on
    ``/a0/usr/projects/trener/pdfs/Capablanca, Jose - Chess Fundamentals.pdf``.
    """
    logger.warning(
        "CHESS_COACH_OCR_BACKEND=local requested; local OCR backend not yet "
        "wired (BBF-68.1 follow-up). Returning structured error."
    )
    return OcrResult(
        None,
        0.0,
        "local OCR backend not yet implemented (BBF-68.1 follow-up; "
        "see docs/16_audit/BBF-68.1-candidate-survey-2026-07-17.md)",
    )


_REGISTRY: dict[str, Predicter] = {
    "chessvision": _predict_chessvision_protected,
    "local": _predict_local,
}
