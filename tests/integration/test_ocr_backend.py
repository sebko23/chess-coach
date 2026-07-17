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
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from chess_coach.pdf_ocr import (
    DEFAULT_BACKEND,
    UnknownOcrBackend,
    get_backend,
    predict_fen,
)


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
        result = await predict_fen(b"\x89PNG\r\n\x1a\n")  # valid PNG signature
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
            result = await predict_fen(b"\x89PNG\r\n\x1a\n")
        assert result.error is None
        assert result.fen == "8/8/8/8/8/8/8/8 w - - 0 1"
        assert result.confidence == pytest.approx(0.9)
