"""Tests for BBF-FU-11a scope-based auth (services/chess_coach/gateway/auth.py).

The scope extension adds ``require_bearer_with_scope(scope: str)`` and
``_check_bearer_with_scope(...)`` to the existing auth surface. The
tests in this file cover:

  1. The ``_parse_token`` helper — the (secret, scope) split on LAST ``:``.
  2. ``_check_bearer_with_scope`` — the three branches:
     a. secret mismatch (401 with "Invalid bearer token")
     b. secret match, scope mismatch (401 with "Token does not have required scope")
     c. secret match, scope match (200-equivalent: no raise)
  3. ``require_bearer_with_scope`` is just a thin FastAPI wrapper around
     ``_check_bearer_with_scope`` — verified by the same test cases
     running through the async dep.
  4. Backward compat: a token without a scope suffix (``"devtoken123"``)
     continues to work with both ``require_bearer`` AND
     ``require_bearer_with_scope(scope="BOOKS_WRITE")`` rejected (the
     read-only token does NOT have BOOKS_WRITE).
  5. The exact-match discipline: scope chains, wildcards, and
     inheritance are NOT supported.
  6. Auth-disabled (active token None): both deps allow all requests.
"""
from __future__ import annotations

import pytest

from chess_coach.errors import UnauthorizedError
from chess_coach.gateway.auth import (
    _check_bearer_with_scope,
    _parse_token,
    require_bearer_with_scope,
    set_active_token,
)

# -----------------------------------------------------------------------
# _parse_token
# -----------------------------------------------------------------------


class TestParseToken:
    def test_no_colon_returns_secret_no_scope(self) -> None:
        assert _parse_token("devtoken123") == ("devtoken123", None)

    def test_colon_with_scope(self) -> None:
        assert _parse_token("devtoken123:BOOKS_WRITE") == (
            "devtoken123",
            "BOOKS_WRITE",
        )

    def test_empty_scope_treated_as_no_scope(self) -> None:
        # Trailing colon with empty suffix → no scope. This is a
        # defensive choice: a user who types "secret:" by accident
        # gets a read-only token, not a malformed scope.
        assert _parse_token("devtoken123:") == ("devtoken123", None)

    def test_splits_on_LAST_colon(self) -> None:
        # Real Polyglot tokens are urlsafe-base64 which excludes ":",
        # so the rightmost-colon split is safe. If a secret ever does
        # contain ":", the split still works correctly: the rightmost
        # ":" is the scope separator.
        assert _parse_token("a:b:c:SCOPE") == ("a:b:c", "SCOPE")

    def test_empty_string_returns_empty_secret(self) -> None:
        assert _parse_token("") == ("", None)

    def test_just_colon(self) -> None:
        # Edge case: a single ":". Split: prefix="", suffix="". Empty
        # scope → no scope. Secret is empty. This is a malformed token
        # (empty secret) but the parser doesn't reject; the auth check
        # rejects it via the constant-time compare.
        assert _parse_token(":") == ("", None)

    def test_scope_with_multiple_words_underscore(self) -> None:
        # Standard SCREAMING_SNAKE_CASE scope name. Splits on the LAST
        # colon, so a multi-colon scope collapses to a single scope
        # value (the suffix after the last colon). The prefix carries
        # any prior colons intact.
        assert _parse_token("secret:BOOKS_WRITE:EXTENDED") == (
            "secret:BOOKS_WRITE",
            "EXTENDED",
        )


# -----------------------------------------------------------------------
# _check_bearer_with_scope
# -----------------------------------------------------------------------


class TestCheckBearerWithScope:
    def setup_method(self) -> None:
        # Default active token: read-only (no scope). Tests that need
        # a write-scope token set it explicitly in the test body.
        set_active_token("devtoken123")

    def teardown_method(self) -> None:
        set_active_token(None)

    # --- 1. secret mismatch -----------------------------------------

    def test_wrong_secret_raises(self) -> None:
        with pytest.raises(UnauthorizedError, match="Invalid bearer token"):
            _check_bearer_with_scope("Bearer wrong-token", "BOOKS_WRITE")

    def test_missing_header_raises(self) -> None:
        with pytest.raises(UnauthorizedError, match="Missing"):
            _check_bearer_with_scope(None, "BOOKS_WRITE")

    def test_wrong_scheme_raises(self) -> None:
        with pytest.raises(UnauthorizedError, match="scheme"):
            _check_bearer_with_scope("Basic dXNlcjpwYXNz", "BOOKS_WRITE")

    # --- 2. secret match, scope check --------------------------------

    def test_readonly_token_rejected_for_write_scope(self) -> None:
        # Active token is "devtoken123" (no scope). A request with the
        # correct secret but the wrong scope (no scope) is rejected
        # for the BOOKS_WRITE dep.
        with pytest.raises(UnauthorizedError, match="BOOKS_WRITE"):
            _check_bearer_with_scope("Bearer devtoken123", "BOOKS_WRITE")

    def test_readonly_token_rejected_for_any_write_scope(self) -> None:
        # Different scope name; still rejected because the active
        # token has no scope at all.
        with pytest.raises(UnauthorizedError, match="PROFILE_WRITE"):
            _check_bearer_with_scope("Bearer devtoken123", "PROFILE_WRITE")

    def test_wrong_scope_rejected(self) -> None:
        # Active token has BOOKS_WRITE; request asks for PROFILE_WRITE.
        set_active_token("devtoken123:BOOKS_WRITE")
        with pytest.raises(UnauthorizedError, match="PROFILE_WRITE"):
            _check_bearer_with_scope("Bearer devtoken123", "PROFILE_WRITE")

    # --- 3. secret match, scope match --------------------------------

    def test_scope_match_passes(self) -> None:
        set_active_token("devtoken123:BOOKS_WRITE")
        # No raise.
        _check_bearer_with_scope("Bearer devtoken123", "BOOKS_WRITE")

    # --- 4. required_scope=None (read-only-equivalent) ---------------

    def test_readonly_token_passes_when_no_scope_required(self) -> None:
        # The most common case: a dep that just wants to know "is this
        # caller authed" without caring about write permissions. A
        # read-only token satisfies it.
        _check_bearer_with_scope("Bearer devtoken123", None)

    def test_write_scope_token_also_passes_when_no_scope_required(self) -> None:
        # A write-scope token ALSO satisfies a no-scope-required dep
        # (the scope is just not checked).
        set_active_token("devtoken123:BOOKS_WRITE")
        _check_bearer_with_scope("Bearer devtoken123", None)

    # --- 5. case-insensitive scheme (mirrors _check_bearer) ----------

    def test_case_insensitive_scheme_passes(self) -> None:
        set_active_token("devtoken123:BOOKS_WRITE")
        _check_bearer_with_scope("bearer devtoken123", "BOOKS_WRITE")
        _check_bearer_with_scope("BEARER devtoken123", "BOOKS_WRITE")

    # --- 6. auth disabled -------------------------------------------

    def test_auth_disabled_passes(self) -> None:
        set_active_token(None)
        # Even with a wrong secret, no raise.
        _check_bearer_with_scope("Bearer anything", "BOOKS_WRITE")
        _check_bearer_with_scope(None, "BOOKS_WRITE")

    # --- 7. exact-match discipline ----------------------------------

    def test_scope_chain_not_supported(self) -> None:
        # The active token has only BOOKS_WRITE. A request asking for
        # BOOKS_WRITE:EXTENDED is rejected; the scope must match
        # exactly.
        set_active_token("devtoken123:BOOKS_WRITE")
        with pytest.raises(UnauthorizedError, match="BOOKS_WRITE:EXTENDED"):
            _check_bearer_with_scope("Bearer devtoken123", "BOOKS_WRITE:EXTENDED")

    def test_scope_wildcard_not_supported(self) -> None:
        # "*" is not a wildcard; it's just a literal scope name.
        set_active_token("devtoken123:BOOKS_WRITE")
        with pytest.raises(UnauthorizedError, match=r"\*"):
            _check_bearer_with_scope("Bearer devtoken123", "*")

    def test_scope_inheritance_not_supported(self) -> None:
        # A BOOKS_WRITE token does NOT also satisfy PROFILE_WRITE.
        # No inheritance between scopes.
        set_active_token("devtoken123:BOOKS_WRITE")
        with pytest.raises(UnauthorizedError, match="PROFILE_WRITE"):
            _check_bearer_with_scope("Bearer devtoken123", "PROFILE_WRITE")


# -----------------------------------------------------------------------
# require_bearer_with_scope (async FastAPI dep)
# -----------------------------------------------------------------------


class TestRequireBearerWithScopeDep:
    def setup_method(self) -> None:
        set_active_token("devtoken123")

    def teardown_method(self) -> None:
        set_active_token(None)

    @pytest.mark.asyncio
    async def test_dep_passes_with_correct_scope(self) -> None:
        set_active_token("devtoken123:BOOKS_WRITE")
        # No raise.
        await require_bearer_with_scope(
            "BOOKS_WRITE", authorization="Bearer devtoken123"
        )

    @pytest.mark.asyncio
    async def test_dep_rejects_wrong_scope(self) -> None:
        set_active_token("devtoken123:BOOKS_WRITE")
        with pytest.raises(UnauthorizedError, match="PROFILE_WRITE"):
            await require_bearer_with_scope(
                "PROFILE_WRITE", authorization="Bearer devtoken123"
            )

    @pytest.mark.asyncio
    async def test_dep_rejects_readonly_token_for_write_scope(self) -> None:
        # Active token is "devtoken123" (no scope). The dep rejects it
        # for any write-scope request.
        with pytest.raises(UnauthorizedError, match="BOOKS_WRITE"):
            await require_bearer_with_scope(
                "BOOKS_WRITE", authorization="Bearer devtoken123"
            )

    @pytest.mark.asyncio
    async def test_dep_passes_for_readonly_token_when_no_scope_required(self) -> None:
        # The dep is also useful for "any authed caller" semantics:
        # pass scope=None to require bearer auth without scope check.
        await require_bearer_with_scope(
            None, authorization="Bearer devtoken123"
        )

    @pytest.mark.asyncio
    async def test_dep_rejects_missing_header(self) -> None:
        with pytest.raises(UnauthorizedError, match="Missing"):
            await require_bearer_with_scope("BOOKS_WRITE", authorization=None)

    @pytest.mark.asyncio
    async def test_dep_rejects_wrong_secret(self) -> None:
        set_active_token("devtoken123:BOOKS_WRITE")
        with pytest.raises(UnauthorizedError, match="Invalid bearer token"):
            await require_bearer_with_scope(
                "BOOKS_WRITE", authorization="Bearer wrong"
            )

    @pytest.mark.asyncio
    async def test_dep_allows_when_auth_disabled(self) -> None:
        set_active_token(None)
        # Even with a write-scope request, no raise when auth is off.
        await require_bearer_with_scope("BOOKS_WRITE", authorization=None)
        await require_bearer_with_scope(
            "BOOKS_WRITE", authorization="Bearer anything"
        )


# -----------------------------------------------------------------------
# Backward compat: require_bearer (the existing dep) still works
# -----------------------------------------------------------------------


class TestBackwardCompat:
    """Verify the existing ``require_bearer`` dep is UNCHANGED by BBF-FU-11a.

    The scope extension is purely additive. A token without a scope
    suffix continues to work with ``require_bearer`` (which never
    checks scopes). A token WITH a scope suffix also works with
    ``require_bearer`` (because the full string is still the secret-
    bearing value, and ``require_bearer`` does an equality check on
    the full string).

    Wait — that's a real behavior question. If the active token is
    "devtoken123:BOOKS_WRITE" and the caller sends "Bearer devtok...ITE",
    the equality check on the FULL string fails (the caller sent the
    secret part, not the secret-plus-scope). The caller would have
    to send "Bearer devtok...ITE" which is the full string including
    the scope suffix.

    This is the intended behavior: a caller who wants write access
    sends the full scope-suffixed token in the Authorization header.
    The new :func:`require_bearer_with_scope` dep handles the
    split-on-LAST-colon internally; :func:`require_bearer` does NOT
    do that split (it just compares the full string).
    """

    def setup_method(self) -> None:
        set_active_token("devtoken123")

    def teardown_method(self) -> None:
        set_active_token(None)

    @pytest.mark.asyncio
    async def test_existing_dep_works_with_plain_token(self) -> None:
        # The most common case: a plain token (no scope), the
        # existing dep, request passes.
        from chess_coach.gateway.auth import require_bearer

        await require_bearer(authorization="Bearer devtoken123")
        # No raise.

    @pytest.mark.asyncio
    async def test_existing_dep_accepts_scope_suffixed_token(self) -> None:
        # Per the BBF-FU-11a design (and the BBF-FU-11b bug-fix in
        # 2026-10-12): ``require_bearer`` accepts a token that has
        # the same secret as the active token, even if the request
        # token includes a ``:SCOPE`` suffix. The dep splits the
        # request on the LAST colon and compares the prefix to
        # the active token's prefix; the suffix is ignored. This
        # is what makes the books-write flow work: the caller
        # sends the full token (with scope) and the dep accepts it
        # regardless of which dep is doing the check.
        from chess_coach.gateway.auth import require_bearer

        set_active_token("devtoken123:BOOKS_WRITE")
        # No raise: the request value is "devtoken123:BOOKS_WRITE",
        # the active token is "devtoken123:BOOKS_WRITE", both
        # split to prefix "devtoken123" which matches.
        await require_bearer(authorization="Bearer devtoken123:BOOKS_WRITE")

        set_active_token("devtoken123")
        # No raise: the request value is "devtoken123:BOOKS_WRITE"
        # but the active token is "devtoken123" (no scope). The
        # prefix of the request ("devtoken123") matches the active
        # token ("devtoken123"). The request's scope suffix is
        # ignored because require_bearer is no-scope-required.
        await require_bearer(authorization="Bearer devtoken123:BOOKS_WRITE")

        # Negative: wrong secret still fails.
        with pytest.raises(UnauthorizedError, match="Invalid bearer token"):
            await require_bearer(authorization="Bearer wrong-token")
