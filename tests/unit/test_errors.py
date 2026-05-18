"""Tests for the typed exception hierarchy and code registry."""
from __future__ import annotations

import pytest

from chess_coach.errors import (
    BadRequestError,
    ChessCoachError,
    EngineTimeoutError,
    ErrorCode,
    NotFoundError,
    UnauthorizedError,
)


class TestErrorCode:
    def test_codes_are_strings(self) -> None:
        # StrEnum: each member's value is the dotted string.
        assert str(ErrorCode.BAD_REQUEST) == "client.bad_request"
        assert ErrorCode.ENGINE_TIMEOUT.value == "engine.timeout"

    def test_codes_are_unique(self) -> None:
        values = [c.value for c in ErrorCode]
        assert len(values) == len(set(values)), "duplicate ErrorCode values"


class TestExceptionHierarchy:
    def test_default_code_and_status(self) -> None:
        e = BadRequestError("nope")
        assert e.code is ErrorCode.BAD_REQUEST
        assert e.http_status == 400
        assert str(e) == "nope"
        assert e.message == "nope"

    def test_details_default_empty_dict(self) -> None:
        assert NotFoundError("x").details == {}

    def test_explicit_retriable_overrides_default(self) -> None:
        # NOT_FOUND is not in RETRIABLE
        e1 = NotFoundError("x")
        assert e1.retriable is False
        e2 = NotFoundError("x", retriable=True)
        assert e2.retriable is True

    def test_engine_timeout_is_retriable_by_default(self) -> None:
        # ENGINE_TIMEOUT IS in RETRIABLE
        assert EngineTimeoutError("slow").retriable is True

    def test_subclass_inherits_class_level_code(self) -> None:
        class MyDomain(BadRequestError):
            code = ErrorCode.ANALYSIS_INVALID_POSITION

        e = MyDomain("bad fen")
        assert e.code is ErrorCode.ANALYSIS_INVALID_POSITION
        assert e.http_status == 400  # inherited

    def test_explicit_code_argument_wins(self) -> None:
        e = ChessCoachError("x", code=ErrorCode.RATE_LIMITED)
        assert e.code is ErrorCode.RATE_LIMITED

    def test_unauthorized_status(self) -> None:
        assert UnauthorizedError("missing").http_status == 401

    def test_details_are_isolated_per_instance(self) -> None:
        a = BadRequestError("a", details={"k": 1})
        b = BadRequestError("b")
        a.details["k"] = 99
        assert b.details == {}  # not the same dict

    @pytest.mark.parametrize(
        "exc_type",
        [BadRequestError, NotFoundError, UnauthorizedError, EngineTimeoutError],
    )
    def test_all_inherit_from_base(self, exc_type: type[ChessCoachError]) -> None:
        assert issubclass(exc_type, ChessCoachError)
