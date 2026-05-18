"""Central exception handlers — the only place that builds the error envelope.

ADR-0002: backend code raises typed exceptions (:mod:`chess_coach.errors`);
the gateway is the single seam that converts them to the protocol error
envelope. Code outside the gateway must NOT raise FastAPI ``HTTPException``.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from chess_coach.errors import ChessCoachError, ErrorCode
from chess_coach.protocol_types import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _envelope(
    *,
    code: ErrorCode | str,
    message: str,
    details: dict[str, Any] | None,
    retriable: bool,
    request_id: str | None,
    http_status: int,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=str(code),
            message=message,
            details=details or {},
            retriable=retriable,
            request_id=request_id,
        )
    ).model_dump(mode="json")
    return JSONResponse(content=body, status_code=http_status)


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    return rid if isinstance(rid, str) else None


async def _chess_coach_error_handler(request: Request, exc: ChessCoachError) -> JSONResponse:
    rid = _request_id(request)
    # Log at WARNING for client errors, ERROR for server errors. Never log
    # `details` at info+ level (ADR-0002 §5).
    if 400 <= exc.http_status < 500:
        logger.warning(
            "gateway.error code=%s status=%d request_id=%s message=%s",
            exc.code, exc.http_status, rid, exc.message,
        )
    else:
        logger.error(
            "gateway.error code=%s status=%d request_id=%s message=%s",
            exc.code, exc.http_status, rid, exc.message,
        )
    if exc.details:
        logger.debug("gateway.error.details %r", exc.details)
    return _envelope(
        code=exc.code,
        message=exc.message,
        details=exc.details,
        retriable=exc.retriable,
        request_id=rid,
        http_status=exc.http_status,
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    rid = _request_id(request)
    logger.warning(
        "gateway.error code=%s status=422 request_id=%s errors=%d",
        ErrorCode.BAD_REQUEST, rid, len(exc.errors()),
    )
    return _envelope(
        code=ErrorCode.BAD_REQUEST,
        message="Request payload failed validation.",
        details={"errors": exc.errors()},
        retriable=False,
        request_id=rid,
        http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def _starlette_http_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Catch HTTPException raised inside FastAPI itself (e.g. 404 on missing route)."""
    rid = _request_id(request)
    code: ErrorCode
    if exc.status_code == 404:
        code = ErrorCode.NOT_FOUND
    elif exc.status_code == 401:
        code = ErrorCode.UNAUTHORIZED
    elif exc.status_code == 403:
        code = ErrorCode.FORBIDDEN
    elif exc.status_code == 405:
        code = ErrorCode.BAD_REQUEST
    else:
        code = ErrorCode.INTERNAL
    return _envelope(
        code=code,
        message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        details=None,
        retriable=False,
        request_id=rid,
        http_status=exc.status_code,
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id(request)
    logger.exception("gateway.error.unhandled request_id=%s", rid)
    return _envelope(
        code=ErrorCode.INTERNAL,
        message="Internal server error.",
        details=None,
        retriable=False,
        request_id=rid,
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Wire all exception handlers onto ``app``.

    Order matters: more-specific handlers must be registered before the
    catch-all ``Exception`` handler.
    """
    app.add_exception_handler(ChessCoachError, _chess_coach_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _starlette_http_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)


__all__ = ["install_exception_handlers"]
