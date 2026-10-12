"""Bearer-token authentication.

Protocol §2.1: standard bearer credential. Equality check on the token only;
no coupling to client identity beyond "can read backend.json or got the token
from the operator".

The gateway holds the active token in process memory. Tests can patch the
token via :func:`set_active_token`.

BBF-FU-11a extension: scope-based authorization. The active token is a
string of the form ``"<secret>:<SCOPE>"`` (e.g., ``"devtoken123:BOOKS_WRITE"``).
The ``:SCOPE`` suffix is optional; a token with no suffix grants read-only
access (any caller passing the correct secret is accepted by
:func:`require_bearer`). The new :func:`require_bearer_with_scope` dep
requires both the secret and the named scope.

Design constraints (FU-11 ledger line 813: "α is per-call, stateless,
no side-effects; β is anything that persists, indexes, or remembers"):

  - Existing tokens (no scope suffix) continue to work with both
    :func:`require_bearer` and :func:`require_bearer_with_scope` when
    called with ``required_scope=None`` (read-only-equivalent).
  - Write access is ONLY available via :func:`require_bearer_with_scope`.
    A read-only token cannot satisfy a write-scope dep.
  - Scope matching is exact-match on the suffix. No scope chains, no
    wildcards, no inheritance. This is the smallest design that
    satisfies the FU-11 boundary statement.

Token format:

  - ``"devtoken123"`` → secret=``devtoken123``, scope=None (read-only)
  - ``"devtoken123:BOOKS_WRITE"`` → secret=``devtoken123``, scope=``BOOKS_WRITE``
  - ``"devtoken123:"`` (empty scope) → secret=``devtoken123``, scope=None

The split is on the LAST ``:``. This means a token whose secret happens
to contain ``:`` (unlikely for a base64 secret, but possible) is
split on the rightmost colon; the prefix is the secret, the suffix is
the scope. Real Polyglot tokens are urlsafe-base64 (per
``generate_token()``), which excludes ``:`` from the alphabet. The
last-colon split is safe.
"""
from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Header

from chess_coach.errors import UnauthorizedError

_active_token: str | None = None


def set_active_token(token: str | None) -> None:
    """Set the token the gateway will accept. Pass ``None`` to disable auth.

    The token may be a plain secret (``"devtoken123"``) or a
    scope-suffixed secret (``"devtoken123:BOOKS_WRITE"``). See module
    docstring for the full format spec.
    """
    global _active_token
    _active_token = token


def get_active_token() -> str | None:
    return _active_token


def _parse_token(value: str) -> tuple[str, str | None]:
    """Split a token string into ``(secret, scope_or_None)``.

    Splits on the LAST ``:``. An empty scope suffix (``"foo:"``) is
    treated as no scope. Returns ``("", None)`` for an empty input.
    """
    if not value:
        return ("", None)
    if ":" not in value:
        return (value, None)
    secret, _, scope = value.rpartition(":")
    if not scope:
        # Trailing colon with no scope: treat as no scope.
        return (secret, None)
    return (secret, scope)


def _check_bearer(authorization: str | None) -> None:
    if _active_token is None:
        # Auth disabled (e.g. test fixture). Allow.
        return
    if not authorization:
        raise UnauthorizedError("Missing Authorization header.")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise UnauthorizedError("Authorization scheme must be Bearer.")
    # Constant-time comparison to avoid timing oracles.
    if not hmac.compare_digest(value, _active_token):
        raise UnauthorizedError("Invalid bearer token.")


def _check_bearer_with_scope(
    authorization: str | None, required_scope: str | None
) -> None:
    """Like :func:`_check_bearer` but additionally checks the token's scope.

    If ``required_scope`` is None, this is equivalent to
    :func:`_check_bearer` (any token whose secret matches is accepted,
    regardless of scope). If ``required_scope`` is a non-empty string,
    the active token MUST be of the form ``"secret:<required_scope>"``
    (or the request is rejected with 401).

    The :func:`_check_bearer` check (secret-only) is run first; this
    means a wrong-secret request fails with "Invalid bearer token" even
    when the scope is also wrong. This is intentional — it avoids
    leaking the presence of a scope to a caller who doesn't have the
    secret.
    """
    if _active_token is None:
        return
    if not authorization:
        raise UnauthorizedError("Missing Authorization header.")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise UnauthorizedError("Authorization scheme must be Bearer.")

    # Split the active token first. The active token carries the scope;
    # the request only carries the secret-bearing value. We split the
    # active token, then compare the prefix (the secret) to the request
    # value via constant-time compare.
    active_secret, active_scope = _parse_token(_active_token)
    if not hmac.compare_digest(value, active_secret):
        raise UnauthorizedError("Invalid bearer token.")

    # Secret matches. Now check scope.
    if required_scope is None:
        return  # read-only-equivalent: any scope (or no scope) is OK
    if active_scope != required_scope:
        raise UnauthorizedError(
            f"Token does not have required scope: {required_scope!r}"
        )


async def require_bearer(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """FastAPI dependency that enforces bearer-token auth.

    Raises :class:`UnauthorizedError` on failure; the central exception handler
    converts that into a protocol-shaped error envelope.
    """
    _check_bearer(authorization)


async def require_bearer_with_scope(
    scope: str,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """FastAPI dependency that enforces bearer-token auth AND a named scope.

    Use this dep on routes that mutate persistent state (the β side of
    FU-11: the three book endpoints at
    ``/v1/repertoire/{player}/book``). The ``scope`` argument is a
    class-level constant from the route module; FastAPI's dependency
    injection resolves it at import time, not request time. The
    active token MUST be configured as ``"secret:<scope>"`` for the
    request to be accepted.

    See module docstring for the full token-format spec.
    """
    _check_bearer_with_scope(authorization, scope)


__all__ = [
    "generate_token_if_needed",
    "get_active_token",
    "require_bearer",
    "require_bearer_with_scope",
    "set_active_token",
]


def generate_token_if_needed(static_token: str | None) -> str:
    """Return ``static_token`` if non-empty, else mint a fresh one.

    Protocol §2.1: if a static token is configured the gateway uses it;
    otherwise a fresh urlsafe-base64 token is generated at every restart.

    BBF-FU-11a: the returned token is the literal string the user
    configured (e.g., ``"devtoken123:BOOKS_WRITE"``); the
    :func:`_parse_token` split happens at request time, not at
    generation time. The env var ``CHESS_COACH_BACKEND_TOKEN`` is
    therefore the operator's knob for both the secret and the scope.
    """
    from .descriptor import generate_token

    if static_token:
        return static_token
    return generate_token()
