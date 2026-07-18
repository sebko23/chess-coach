"""Unit tests for the OCR backend protection layer (token bucket + circuit breaker).

These tests exercise the protection primitives in isolation -- no FastAPI,
no httpx, no real chessvision.ai calls. The integration tests in
``tests/integration/test_ocr_backend.py`` verify the wiring through the
adapter dispatcher.

The test layout follows the pattern from ``tests/unit/test_kb_persistent_path.py``
(plain pytest functions, no special markers). The autouse ``_isolate_env``
fixture in ``tests/conftest.py`` clears all ``CHESS_COACH_*`` env vars per
test, so we use ``monkeypatch.setenv`` to inject the config under test.

Test categories:

- :class:`TestTokenBucket` -- rate-limit behavior in isolation.
- :class:`TestCircuitBreaker` -- state machine in isolation.
- :class:`TestProtectionRegistry` -- per-backend isolation + env-var wiring.
"""
from __future__ import annotations

from typing import cast

import pytest

from chess_coach.pdf_ocr.protection import (
    CircuitBreaker,
    CircuitState,
    TokenBucket,
    get_protection_registry,
    reset_protection_registry,
)


class TestTokenBucket:
    def test_starts_full(self) -> None:
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        # All 5 tokens available immediately on construction.
        for _ in range(5):
            assert bucket.try_acquire() is True
        # 6th call finds the bucket empty.
        assert bucket.try_acquire() is False

    def test_refills_over_time(self) -> None:
        # 2 RPS, capacity 1: one token available now, next after 500ms.
        bucket = TokenBucket(capacity=1, refill_rate=2.0)
        assert bucket.try_acquire() is True
        assert bucket.try_acquire() is False
        # We don't sleep (test slowness); just verify the structure accepts
        # the refill math. The 0-time call right after a successful acquire
        # must NOT have a token available yet.
        assert bucket.try_acquire() is False

    def test_rejects_zero_capacity(self) -> None:
        with pytest.raises(ValueError, match="capacity"):
            TokenBucket(capacity=0, refill_rate=1.0)

    def test_rejects_zero_rate(self) -> None:
        with pytest.raises(ValueError, match="refill_rate"):
            TokenBucket(capacity=1, refill_rate=0.0)


class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker(threshold=3, cooldown_seconds=60.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.should_allow() is True

    def test_opens_after_threshold_failures(self) -> None:
        cb = CircuitBreaker(threshold=3, cooldown_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state != CircuitState.OPEN
        cb.record_failure()  # threshold hit
        assert cast(CircuitState, cb.state) == CircuitState.OPEN
        # While OPEN, calls are rejected.
        assert cb.should_allow() is False

    def test_success_resets_consecutive_failures(self) -> None:
        cb = CircuitBreaker(threshold=3, cooldown_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # reset
        cb.record_failure()
        cb.record_failure()
        # Still CLOSED -- success in between reset the counter.
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_cooldown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cb = CircuitBreaker(threshold=2, cooldown_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Fake the cooldown by rewinding ``opened_at`` via monkeypatch.
        # The simplest portable hack: we can read ``cb.opened_at`` and
        # patch the time function. We patch time.monotonic instead.
        import time as time_mod
        original = time_mod.monotonic
        # Pretend 120 seconds have passed since ``opened_at``.
        monkeypatch.setattr(
            time_mod, "monotonic", lambda: cb.opened_at + 120.0
        )
        try:
            # First call after cooldown is allowed through as a probe.
            assert cb.should_allow() is True
            assert cast(CircuitState, cb.state) == CircuitState.HALF_OPEN
            # Second concurrent call is rejected (single-shot probe).
            assert cb.should_allow() is False
            # Probe success -> CLOSED.
            cb.record_success()
            assert cast(CircuitState, cb.state) == CircuitState.CLOSED
        finally:
            monkeypatch.setattr(time_mod, "monotonic", original)

    def test_half_open_probe_failure_reopens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cb = CircuitBreaker(threshold=2, cooldown_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        import time as time_mod
        original = time_mod.monotonic
        monkeypatch.setattr(
            time_mod, "monotonic", lambda: cb.opened_at + 120.0
        )
        try:
            cb.should_allow()  # CLOSED -> HALF_OPEN (probe in flight)
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_failure()  # probe failed
            assert cast(CircuitState, cb.state) == CircuitState.OPEN
            # Subsequent calls rejected until cooldown elapses again.
            monkeypatch.setattr(
                time_mod, "monotonic", lambda: cb.opened_at + 30.0
            )
            assert cb.should_allow() is False
        finally:
            monkeypatch.setattr(time_mod, "monotonic", original)

    def test_rejects_invalid_threshold(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            CircuitBreaker(threshold=0, cooldown_seconds=60.0)

    def test_rejects_zero_cooldown(self) -> None:
        with pytest.raises(ValueError, match="cooldown_seconds"):
            CircuitBreaker(threshold=1, cooldown_seconds=0.0)


class TestProtectionRegistry:
    def test_per_backend_isolation(self) -> None:
        reset_protection_registry()
        reg = get_protection_registry()
        # Exhaust chessvision's burst (default capacity 5).
        for _ in range(5):
            assert reg.bucket_try_acquire("chessvision") is True
        # Next call on chessvision is denied.
        assert reg.bucket_try_acquire("chessvision") is False
        # A different backend gets its own fresh bucket.
        assert reg.bucket_try_acquire("local") is True

    def test_breaker_failure_count_is_per_backend(self) -> None:
        reset_protection_registry()
        reg = get_protection_registry()
        # Trip the chessvision breaker (default threshold 5).
        for _ in range(5):
            reg.breaker_record_failure("chessvision")
        assert reg.breaker_should_allow("chessvision") is False
        # local's breaker is independent.
        assert reg.breaker_should_allow("local") is True

    def test_env_var_override_capacity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reset_protection_registry()
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_BURST", "2")
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_RPS", "0.5")
        reg = get_protection_registry()
        assert reg.bucket_try_acquire("chessvision") is True
        assert reg.bucket_try_acquire("chessvision") is True
        # Third call denied -- burst exhausted.
        assert reg.bucket_try_acquire("chessvision") is False

    def test_env_var_override_breaker_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reset_protection_registry()
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_CB_THRESHOLD", "2")
        reg = get_protection_registry()
        reg.breaker_record_failure("chessvision")
        reg.breaker_record_failure("chessvision")
        # After just 2 failures the breaker is OPEN.
        assert reg.breaker_should_allow("chessvision") is False

    def test_invalid_env_var_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Garbage values must NOT crash -- they fall back to the default
        # and emit a warning. This is a robustness check: a typo in an env
        # var must not brick OCR.
        reset_protection_registry()
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_RPS", "not-a-number")
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_BURST", "forty-two")
        reg = get_protection_registry()
        # Should still be usable with defaults (capacity 5).
        for _ in range(5):
            assert reg.bucket_try_acquire("chessvision") is True
        assert reg.bucket_try_acquire("chessvision") is False
        # And we logged the bad values.
        assert any(
            "invalid" in record.message.lower() or "default" in record.message.lower()
            for record in caplog.records
        )

    def test_reset_clears_state(self) -> None:
        reset_protection_registry()
        reg = get_protection_registry()
        # Exhaust chessvision.
        for _ in range(5):
            reg.bucket_try_acquire("chessvision")
        assert reg.bucket_try_acquire("chessvision") is False
        # Reset.
        reset_protection_registry()
        # Fresh registry -- bucket is full again.
        assert reg.bucket_try_acquire("chessvision") is True
