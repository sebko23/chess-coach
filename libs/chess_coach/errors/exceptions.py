"""Typed exception hierarchy.

ADR-0002: backend code raises typed exceptions; the FastAPI exception handler
in ``chess_coach.gateway`` is the single point that converts these to the
protocol error envelope. Code outside the gateway must NOT raise FastAPI
``HTTPException``.

Exceptions carry:
    code     - a stable ErrorCode (mirrors protocol §10)
    message  - human-readable, MUST NOT contain unsanitized user-supplied content
    details  - structured, JSON-serializable extra data; MAY be omitted from
               response payload at the gateway's discretion (e.g. for security)
    retriable - explicit override; defaults to whether the code is in RETRIABLE
"""
from __future__ import annotations

from typing import Any

from .codes import RETRIABLE, ErrorCode


class ChessCoachError(Exception):
    """Base class for all backend-raised typed exceptions."""

    code: ErrorCode = ErrorCode.INTERNAL
    """Default code; subclasses override with a class-level assignment."""

    http_status: int = 500
    """Default HTTP status; subclasses override."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        retriable: bool | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details) if details else {}
        self._retriable_override = retriable

    @property
    def retriable(self) -> bool:
        if self._retriable_override is not None:
            return self._retriable_override
        return self.code in RETRIABLE

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ---------- 4xx client errors ----------


class BadRequestError(ChessCoachError):
    code = ErrorCode.BAD_REQUEST
    http_status = 400


class UnauthorizedError(ChessCoachError):
    code = ErrorCode.UNAUTHORIZED
    http_status = 401


class ForbiddenError(ChessCoachError):
    code = ErrorCode.FORBIDDEN
    http_status = 403


class NotFoundError(ChessCoachError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class ConflictError(ChessCoachError):
    code = ErrorCode.CONFLICT
    http_status = 409


class PayloadTooLargeError(ChessCoachError):
    code = ErrorCode.PAYLOAD_TOO_LARGE
    http_status = 413


class RateLimitedError(ChessCoachError):
    code = ErrorCode.RATE_LIMITED
    http_status = 429


class UnsupportedProtocolVersionError(BadRequestError):
    code = ErrorCode.UNSUPPORTED_VERSION


# ---------- 5xx server errors ----------


class NotImplementedYetError(ChessCoachError):
    """Raised for endpoints/features that are intentionally Phase>1."""

    code = ErrorCode.NOT_IMPLEMENTED
    http_status = 501


# ---------- engine domain ----------


class EngineError(ChessCoachError):
    code = ErrorCode.ENGINE_CRASHED
    http_status = 500


class EngineNotFoundError(EngineError):
    code = ErrorCode.ENGINE_NOT_FOUND
    http_status = 404


class EngineStartError(EngineError):
    code = ErrorCode.ENGINE_FAILED_TO_START
    http_status = 503


class EngineTimeoutError(EngineError):
    code = ErrorCode.ENGINE_TIMEOUT
    http_status = 504


class EngineBadOutputError(EngineError):
    code = ErrorCode.ENGINE_BAD_OUTPUT


# ---------- analysis domain ----------


class InvalidPositionError(BadRequestError):
    code = ErrorCode.ANALYSIS_INVALID_POSITION


class NoLegalMovesError(BadRequestError):
    code = ErrorCode.ANALYSIS_NO_LEGAL_MOVES


# ---------- storage ----------


class StorageError(ChessCoachError):
    http_status = 500


class StorageLockedError(StorageError):
    code = ErrorCode.STORAGE_LOCKED
    http_status = 503


class MigrationFailedError(StorageError):
    code = ErrorCode.STORAGE_MIGRATION_FAILED


class StorageCorruptionError(StorageError):
    code = ErrorCode.STORAGE_CORRUPTION


# ---------- llm / narration ----------


class LLMProviderError(ChessCoachError):
    code = ErrorCode.LLM_PROVIDER_ERROR
    http_status = 502


class LLMTimeoutError(LLMProviderError):
    code = ErrorCode.LLM_TIMEOUT
    http_status = 504


class LLMBudgetExceededError(ChessCoachError):
    code = ErrorCode.LLM_BUDGET_EXCEEDED
    http_status = 503


class NarrationGroundingFailedError(ChessCoachError):
    code = ErrorCode.NARRATION_GROUNDING_FAILED
    http_status = 500


class NarrationValidationFailedError(ChessCoachError):
    code = ErrorCode.NARRATION_VALIDATION_FAILED
    http_status = 500


# ---------- jobs ----------


class JobNotFoundError(NotFoundError):
    code = ErrorCode.JOB_NOT_FOUND


class JobCancelledError(ConflictError):
    code = ErrorCode.JOB_CANCELLED


class JobFailedError(ChessCoachError):
    code = ErrorCode.JOB_FAILED
    http_status = 500
