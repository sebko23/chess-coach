"""Tests for bearer-token authentication."""
from __future__ import annotations

import pytest

from chess_coach.errors import UnauthorizedError
from chess_coach.gateway.auth import (
    _check_bearer,
    generate_token_if_needed,
    set_active_token,
)


class TestCheckBearer:
    def setup_method(self) -> None:
        set_active_token("good-token")

    def teardown_method(self) -> None:
        set_active_token(None)

    def test_valid_token_passes(self) -> None:
        _check_bearer("Bearer good-token")

    def test_case_insensitive_scheme(self) -> None:
        _check_bearer("bearer good-token")
        _check_bearer("BEARER good-token")

    def test_missing_header(self) -> None:
        with pytest.raises(UnauthorizedError):
            _check_bearer(None)

    def test_wrong_scheme(self) -> None:
        with pytest.raises(UnauthorizedError):
            _check_bearer("Basic dXNlcjpwYXNz")

    def test_wrong_token(self) -> None:
        with pytest.raises(UnauthorizedError):
            _check_bearer("Bearer wrong-token")

    def test_empty_token_value(self) -> None:
        with pytest.raises(UnauthorizedError):
            _check_bearer("Bearer ")


class TestAuthDisabled:
    def test_no_active_token_means_open(self) -> None:
        set_active_token(None)
        # Should not raise even with no Authorization header.
        _check_bearer(None)
        _check_bearer("anything")


class TestGenerateTokenIfNeeded:
    def test_static_token_returned_verbatim(self) -> None:
        assert generate_token_if_needed("my-static") == "my-static"

    def test_none_or_empty_mints_fresh(self) -> None:
        a = generate_token_if_needed(None)
        b = generate_token_if_needed("")
        assert a
        assert b
        assert a != b  # vanishingly unlikely to collide
