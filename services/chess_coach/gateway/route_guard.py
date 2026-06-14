"""Route error guard decorator — ADR-0002 compliant error handling.

Wraps async route handlers to convert:
  - aiosqlite.DatabaseError     -> ChessCoachError(INTERNAL)
  - empty result (returns None) -> NotFoundError
  - unexpected Exception        -> ChessCoachError(INTERNAL)
  - existing ChessCoachError    -> re-raised (already handled by exception_handlers)
  - existing HTTPException      -> re-raised (already handled by exception_handlers)

Usage:
    @router.get("/v1/thing/{id}")
    @route_guard
    async def get_thing(id: str) -> Thing:
        ...
"""
from __future__ import annotations

import functools
import logging
import uuid
from collections.abc import Callable
from typing import Any

import aiosqlite
from starlette.exceptions import HTTPException as StarletteHTTPException

from chess_coach.errors.codes import ErrorCode
from chess_coach.errors.exceptions import ChessCoachError, NotFoundError

logger = logging.getLogger(__name__)


def route_guard(fn: Callable) -> Callable:
    """Decorator that adds ADR-0002 compliant error handling to async route handlers."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request_id = str(uuid.uuid4())[:8]
        try:
            result = await fn(*args, **kwargs)
            if result is None:
                raise NotFoundError(f"Resource not found (request_id={request_id})")
            return result
        except (ChessCoachError, StarletteHTTPException):
            raise
        except aiosqlite.DatabaseError as exc:
            logger.error(
                "route_guard[%s]: database error in %s: %s",
                request_id, fn.__name__, exc,
            )
            raise ChessCoachError(
                message=f"Database error (request_id={request_id})",
                code=ErrorCode.INTERNAL,
            ) from exc
        except Exception as exc:
            logger.error(
                "route_guard[%s]: unhandled error in %s: %s",
                request_id, fn.__name__, exc,
                exc_info=True,
            )
            raise ChessCoachError(
                message=f"Unexpected error (request_id={request_id})",
                code=ErrorCode.INTERNAL,
            ) from exc

    return wrapper
