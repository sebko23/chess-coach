"""Rate limiting and circuit breaker for OCR backends.

This module provides two protection primitives, both keyed per backend name:

- :class:`TokenBucket` -- per-process rate limit. Backends are throttled to
  ``refill_rate`` requests per second sustained, with ``capacity`` requests
  of burst. When the bucket is empty, requests are short-circuited with a
  structured error (``rate_limit:<backend>:bucket_empty``).

- :class:`CircuitBreaker` -- classic 3-state breaker (CLOSED, OPEN, HALF_OPEN).
  After ``threshold`` consecutive failures, the breaker trips OPEN for
  ``cooldown_seconds``. The first call after cooldown is a HALF_OPEN probe;
  success closes the circuit, failure re-opens it for another cooldown.

The two are composed by :class:`ProtectionRegistry`, which holds one
(bucket, breaker) pair per backend. There is one module-level registry;
state is in-process and resets on container restart. This is deliberate:
the public chessvision.ai endpoint has no SLA, so cross-instance state
(e.g. Redis) would add operational complexity for no real benefit at
the volumes this endpoint sees.

Why env-only (no GatewaySettings field):
    The OpenRouter API key (services/chess_coach/llm_router/config.py) and
    the OCR backend (this package's adapter.py) follow the same pattern:
    env-only, lazy read at call time. PDF ingestion is not a hot path
    (one HTTP per page on user-triggered upload), so call-time env reads
    are cheap and avoid a GatewaySettings schema migration.

Env vars (all optional, all `CHESS_COACH_OCR_<BACKEND>_*`):

    CHESS_COACH_OCR_CHESSVISION_RPS          default 1.0
    CHESS_COACH_OCR_CHESSVISION_BURST        default 5
    CHESS_COACH_OCR_CHESSVISION_CB_THRESHOLD default 5
    CHESS_COACH_OCR_CHESSVISION_CB_COOLDOWN  default 120.0
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


# Defaults; per-backend env vars override.
DEFAULT_RPS = 1.0
DEFAULT_BURST = 5
DEFAULT_CB_THRESHOLD = 5
DEFAULT_CB_COOLDOWN_SECONDS = 120.0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("invalid float for %s=%r; using default %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid int for %s=%r; using default %s", name, raw, default)
        return default


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class TokenBucket:
    """Classic token-bucket rate limiter.

    Tokens are added continuously at ``refill_rate`` per second, up to
    ``capacity``. ``try_acquire`` is non-blocking: returns True if a
    token was available, False otherwise. The caller MUST treat False
    as "drop this request and produce a 429-style error", never as
    "wait until a token is available" -- waiting would couple
    request-handling latency to the bucket's drain rate.
    """

    capacity: int
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError(f"capacity must be > 0; got {self.capacity}")
        if self.refill_rate <= 0:
            raise ValueError(f"refill_rate must be > 0; got {self.refill_rate}")
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

    def try_acquire(self) -> bool:
        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


@dataclass
class CircuitBreaker:
    """3-state circuit breaker (CLOSED, OPEN, HALF_OPEN).

    State transitions:

    - CLOSED: every call passes through. Consecutive failures are counted.
      When ``failures >= threshold``, transition to OPEN and stamp
      ``opened_at``.
    - OPEN: every call is short-circuited. After ``cooldown_seconds``
      elapses, transition to HALF_OPEN.
    - HALF_OPEN: the NEXT single call is allowed through as a probe.
      Success → CLOSED, ``failures`` reset to 0. Failure → OPEN with a
      fresh ``opened_at``.

    Half-open probes are deliberately single-shot: a thundering herd of
    probes after cooldown would just re-trip the breaker on the same
    upstream failure.
    """

    threshold: int
    cooldown_seconds: float
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failures: int = field(default=0, init=False)
    opened_at: float = field(default=0.0, init=False)
    half_open_in_flight: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.threshold < 1:
            raise ValueError(f"threshold must be >= 1; got {self.threshold}")
        if self.cooldown_seconds <= 0:
            raise ValueError(f"cooldown_seconds must be > 0; got {self.cooldown_seconds}")

    def should_allow(self) -> bool:
        if self.state is CircuitState.CLOSED:
            return True
        if self.state is CircuitState.OPEN:
            if time.monotonic() - self.opened_at >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_in_flight = False
                logger.info("circuit breaker entering HALF_OPEN")
                # fall through to HALF_OPEN handling below
            else:
                return False
        # HALF_OPEN
        if self.half_open_in_flight:
            return False
        self.half_open_in_flight = True
        return True

    def record_success(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.half_open_in_flight = False
            logger.info("circuit breaker probe succeeded; CLOSED")
        else:
            # CLOSED: reset consecutive failure counter on any success.
            self.failures = 0

    def record_failure(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            self.half_open_in_flight = False
            logger.warning("circuit breaker probe failed; re-OPEN for %ss", self.cooldown_seconds)
            return
        self.failures += 1
        if self.failures >= self.threshold and self.state is CircuitState.CLOSED:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            logger.warning(
                "circuit breaker OPEN after %d consecutive failures; cooldown %ss",
                self.failures, self.cooldown_seconds,
            )


@dataclass
class _BackendProtection:
    bucket: TokenBucket
    breaker: CircuitBreaker


class ProtectionRegistry:
    """Per-backend (bucket, breaker) pairs, lazily created."""

    def __init__(self) -> None:
        self._by_backend: dict[str, _BackendProtection] = {}

    @staticmethod
    def _config_for(backend: str) -> tuple[int, float, int, float]:
        # Env-var layout: CHESS_COACH_OCR_<BACKEND>_<KEY>; backend name is
        # upper-cased to form the prefix (e.g. CHESSVISION -> CHESSVISION).
        prefix = f"CHESS_COACH_OCR_{backend.upper()}"
        burst = _env_int(f"{prefix}_BURST", DEFAULT_BURST)
        rps = _env_float(f"{prefix}_RPS", DEFAULT_RPS)
        cb_threshold = _env_int(f"{prefix}_CB_THRESHOLD", DEFAULT_CB_THRESHOLD)
        cb_cooldown = _env_float(f"{prefix}_CB_COOLDOWN", DEFAULT_CB_COOLDOWN_SECONDS)
        return burst, rps, cb_threshold, cb_cooldown

    def _get(self, backend: str) -> _BackendProtection:
        if backend not in self._by_backend:
            burst, rps, cb_threshold, cb_cooldown = self._config_for(backend)
            self._by_backend[backend] = _BackendProtection(
                bucket=TokenBucket(capacity=burst, refill_rate=rps),
                breaker=CircuitBreaker(threshold=cb_threshold, cooldown_seconds=cb_cooldown),
            )
        return self._by_backend[backend]

    def bucket_try_acquire(self, backend: str) -> bool:
        return self._get(backend).bucket.try_acquire()

    def breaker_should_allow(self, backend: str) -> bool:
        return self._get(backend).breaker.should_allow()

    def breaker_record_success(self, backend: str) -> None:
        self._get(backend).breaker.record_success()

    def breaker_record_failure(self, backend: str) -> None:
        self._get(backend).breaker.record_failure()

    def reset(self) -> None:
        """Test hook: clear all per-backend state. NOT used in production."""
        self._by_backend.clear()


_REGISTRY = ProtectionRegistry()


def get_protection_registry() -> ProtectionRegistry:
    """Return the module-level :class:`ProtectionRegistry` singleton."""
    return _REGISTRY


def reset_protection_registry() -> None:
    """Test hook. Clears the module-level registry between tests."""
    _REGISTRY.reset()
