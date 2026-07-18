"""Integration tests for the OCR backend dispatcher.

These tests prove that:

- The default backend (chessvision) is what existing route integration tests
  rely on, and stays wired unchanged. The existing test_pdf_import.py
  continues to mock ``_predict_fen`` on the route, so we don't need to redo
  that here.

- Setting ``CHESS_COACH_OCR_BACKEND=local`` makes ``predict_fen`` return a
  structured error message that points at the BBF-68.1 follow-up instead of
  silently falling back to chessvision (silent fallback was a real risk
  before this dispatcher was added).

- An unknown backend name raises :class:`UnknownOcrBackend` immediately,
  which the route MUST surface as a 500 (server-side misconfiguration).

- BBF-68.2: the chessvision backend is wrapped by a token bucket (rate
  limit) and a 3-state circuit breaker. Rate-limit denials and breaker
  short-circuits produce structured ``OcrResult`` errors WITHOUT invoking
  the network. The breaker recovers on a successful HALF_OPEN probe after
  the configured cooldown.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest

from chess_coach.pdf_ocr import (
    DEFAULT_BACKEND,
    UnknownOcrBackend,
    get_backend,
    predict_fen,
)
from chess_coach.pdf_ocr.protection import reset_protection_registry

# PNG file signature, used everywhere as a minimal valid "image" input.
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class TestOcrDispatcher:
    async def test_default_backend_is_chessvision(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With CHESS_COACH_OCR_BACKEND unset, the dispatched backend is chessvision."""
        monkeypatch.delenv("CHESS_COACH_OCR_BACKEND", raising=False)
        backend = get_backend(DEFAULT_BACKEND)
        assert backend is get_backend("chessvision")

    async def test_local_backend_returns_structured_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHESS_COACH_OCR_BACKEND", "local")
        result = await predict_fen(_PNG_SIG)  # valid PNG signature
        assert result.fen is None
        assert result.confidence == 0.0
        assert result.error is not None
        # Must point future maintainers at the follow-up BBF.
        assert "BBF-68.1" in result.error
        expected_locator = "chess_coach.pdf_ocr"
        alt_locator = "candidate-survey"
        assert expected_locator in result.error or alt_locator in result.error

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(UnknownOcrBackend) as excinfo:
            get_backend("nonexistent")
        msg = str(excinfo.value)
        assert "nonexistent" in msg
        # Error must enumerate the valid options so a misconfiguration is
        # diagnosable from the 500 response body.
        assert "chessvision" in msg
        assert "local" in msg

    async def test_chessvision_backend_invokes_network_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The chessvision backend still goes through httpx (smoke net behavior)."""
        monkeypatch.setenv("CHESS_COACH_OCR_BACKEND", "chessvision")

        async def fake_post(
            self: Any,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: Any,
        ) -> Any:  # noqa: ARG001
            class _FakeResp:
                status_code: int = 200
                def json(self: Any) -> dict[str, object]:
                    return {"success": True, "result": "8/8/8/8/8/8/8/8_w_-_-_0_1"}
            return _FakeResp()

        with patch("httpx.AsyncClient.post", new=fake_post):
            result = await predict_fen(_PNG_SIG)
        assert result.error is None
        assert result.fen == "8/8/8/8/8/8/8/8 w - - 0 1"
        assert result.confidence == pytest.approx(0.9)


class TestOcrProtection:
    """Verify rate-limit + circuit-breaker wiring through the dispatcher.

    The ``_isolate_env`` autouse fixture clears ``CHESS_COACH_*`` per test,
    so each test re-sets the protection env vars it needs. The
    ``reset_protection_registry`` calls ensure a fresh registry per test;
    without them, env var changes would not take effect for backends whose
    state was already materialized in a previous test.
    """

    async def test_rate_limit_returns_structured_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the chessvision bucket is empty, predict_fen returns a structured
        error WITHOUT calling the network. This is the load-shedding case."""
        monkeypatch.setenv("CHESS_COACH_OCR_BACKEND", "chessvision")
        # Tiny burst so we can exhaust it fast.
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_BURST", "2")
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_RPS", "0.001")
        reset_protection_registry()

        network_call_count = 0

        async def fake_post(
            self: Any,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: Any,
        ) -> Any:
            nonlocal network_call_count
            network_call_count += 1

            class _FakeResp:
                status_code: int = 200
                def json(self: Any) -> dict[str, object]:
                    return {"success": True, "result": "8/8/8/8/8/8/8/8_w_-_-_0_1"}
            return _FakeResp()

        with patch("httpx.AsyncClient.post", new=fake_post):
            # First two calls succeed (consume the burst).
            r1 = await predict_fen(_PNG_SIG)
            r2 = await predict_fen(_PNG_SIG)
            assert r1.error is None
            assert r2.error is None
            assert network_call_count == 2

            # Third call is denied by the rate limiter -- no network call.
            r3 = await predict_fen(_PNG_SIG)
            assert r3.fen is None
            assert r3.confidence == 0.0
            assert r3.error is not None
            assert r3.error.startswith("rate_limit:")
            assert "chessvision" in r3.error
            # Network call count is unchanged -- the rate-limited call did
            # NOT invoke the network.
            assert network_call_count == 2

        reset_protection_registry()

    async def test_circuit_breaker_opens_after_consecutive_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """N consecutive errors trip the breaker; subsequent calls are short-circuited."""
        monkeypatch.setenv("CHESS_COACH_OCR_BACKEND", "chessvision")
        # 2 failures trips the breaker (lower threshold for a fast test).
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_CB_THRESHOLD", "2")
        # Disable rate limiting so the breaker is the only thing gating calls.
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_BURST", "1000")
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_RPS", "1000")
        reset_protection_registry()

        network_call_count = 0

        async def fake_failing_post(
            self: Any,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: Any,
        ) -> Any:
            nonlocal network_call_count
            network_call_count += 1

            class _FakeResp:
                status_code: int = 503
                def json(self: Any) -> dict[str, object]:
                    return {"error": "upstream down"}
            return _FakeResp()

        with patch("httpx.AsyncClient.post", new=fake_failing_post):
            r1 = await predict_fen(_PNG_SIG)
            r2 = await predict_fen(_PNG_SIG)
            # Both calls reached the network and got the failure response.
            assert r1.error is not None
            assert r2.error is not None
            assert network_call_count == 2

            # Third call is short-circuited by the breaker -- no network call.
            r3 = await predict_fen(_PNG_SIG)
            assert r3.error is not None
            assert r3.error.startswith("circuit_open:")
            assert "chessvision" in r3.error
            assert network_call_count == 2  # unchanged

        reset_protection_registry()

    async def test_circuit_breaker_recovers_on_probe_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After cooldown, a HALF_OPEN probe that succeeds closes the breaker.

        The recovery scenario: upstream was failing, then comes back. We
        verify the breaker notices and lets traffic through. We use a real
        ``time.sleep`` rather than mocking ``time.monotonic`` because the
        breaker reads ``time.monotonic`` directly; patching it would also
        patch the test framework's own timing. A 0.6s sleep is well under
        the test budget.
        """
        monkeypatch.setenv("CHESS_COACH_OCR_BACKEND", "chessvision")
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_CB_THRESHOLD", "2")
        # 0.5s cooldown; we sleep 0.6s to let it elapse.
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_CB_COOLDOWN", "0.5")
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_BURST", "1000")
        monkeypatch.setenv("CHESS_COACH_OCR_CHESSVISION_RPS", "1000")
        reset_protection_registry()

        # Phase 1: upstream fails; trip the breaker.
        async def fake_failing_post(
            self: Any,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: Any,
        ) -> Any:
            class _FakeResp:
                status_code: int = 503
                def json(self: Any) -> dict[str, object]:
                    return {"error": "down"}
            return _FakeResp()

        with patch("httpx.AsyncClient.post", new=fake_failing_post):
            await predict_fen(_PNG_SIG)
            await predict_fen(_PNG_SIG)
            r3 = await predict_fen(_PNG_SIG)
            assert r3.error is not None
            assert r3.error.startswith("circuit_open:")

        # Wait out the cooldown.
        time.sleep(0.6)

        # Phase 2: upstream is back; the next call is a HALF_OPEN probe.
        async def fake_ok_post(
            self: Any,
            url: str,
            json: dict[str, object] | None = None,
            **kwargs: Any,
        ) -> Any:
            class _FakeResp:
                status_code: int = 200
                def json(self: Any) -> dict[str, object]:
                    return {"success": True, "result": "8/8/8/8/8/8/8/8_w_-_-_0_1"}
            return _FakeResp()

        with patch("httpx.AsyncClient.post", new=fake_ok_post):
            # Probe: succeeds and closes the breaker.
            r_probe = await predict_fen(_PNG_SIG)
            assert r_probe.error is None
            assert r_probe.fen == "8/8/8/8/8/8/8/8 w - - 0 1"

            # Subsequent call also succeeds -- breaker is CLOSED again.
            r_after = await predict_fen(_PNG_SIG)
            assert r_after.error is None

        reset_protection_registry()
