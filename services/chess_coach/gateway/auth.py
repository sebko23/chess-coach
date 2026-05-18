"""Bearer-token authentication.

Protocol §2.1: standard bearer credential. Equality check on the token only;
no coupling to client identity beyond "can read backend.json or got the token
from the operator."

The gateway holds the active token in process memory. Tests can patch the
token via :func:`set_active_token`.
"""
from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header

from chess_coach.errors import UnauthorizedError

_active_token: str | None = None


def set_active_token(token: str | None) -> None:
    """Set the token the gateway will accept. Pass ``None`` to disable auth."""
    global _active_token
    _active_token = token


def get_active_token() -> str | None:
    return _active_token


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


async def require_bearer(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """FastAPI dependency that enforces bearer-token auth.

    Raises :class:`UnauthorizedError` on failure; the central exception handler
    converts that into a protocol-shaped error envelope.
    """
    _check_bearer(authorization)


__all__ = ["get_active_token", "require_bearer", "set_active_token"]


def generate_token_if_needed(static_token: str | None) -> str:
    """Return ``static_token`` if non-empty, else mint a fresh one.

    Protocol §2.1: if a static token is configured the gateway uses it;
    otherwise a fresh urlsafe-base64 token is generated at every restart.
    """
    from .descriptor import generate_token

    if static_token:
        return static_token
    return generate_token()
