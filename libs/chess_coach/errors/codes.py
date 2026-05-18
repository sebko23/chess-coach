"""Error-code registry.

Mirror of protocol §10 (specs/v1.0/chess-coach-protocol-v1.md). The protocol
document is the authoritative source of which codes exist; this module is the
Python-side enumeration used by the typed exception hierarchy in
``chess_coach.errors.exceptions``.

ADR-0002 governs how new codes are added: namespaced ``<category>.<sub>.<detail>``;
adding a code is a minor protocol bump, removing/renaming is a major bump.

Note: this module is intentionally dependency-free so it can be imported by
anything (including the gateway's earliest startup hooks).
"""
from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable, registered error codes returned to clients in the error envelope."""

    # ----- generic -----
    INTERNAL = "internal.unexpected"
    NOT_IMPLEMENTED = "internal.not_implemented"
    BAD_REQUEST = "client.bad_request"
    NOT_FOUND = "client.not_found"
    UNAUTHORIZED = "client.unauthorized"
    FORBIDDEN = "client.forbidden"
    CONFLICT = "client.conflict"
    RATE_LIMITED = "client.rate_limited"
    PAYLOAD_TOO_LARGE = "client.payload_too_large"
    UNSUPPORTED_VERSION = "client.unsupported_version"

    # ----- server state -----
    SERVER_UNAVAILABLE = "server.unavailable"
    VALIDATION_ERROR = "client.validation_error"

    # ----- engine domain -----
    ENGINE_NOT_FOUND = "engine.not_found"
    ENGINE_FAILED_TO_START = "engine.failed_to_start"
    ENGINE_TIMEOUT = "engine.timeout"
    ENGINE_CRASHED = "engine.crashed"
    ENGINE_BAD_OUTPUT = "engine.bad_output"

    # ----- analysis domain -----
    ANALYSIS_INVALID_POSITION = "analysis.invalid_position"
    ANALYSIS_NO_LEGAL_MOVES = "analysis.no_legal_moves"

    # ----- storage / cache -----
    STORAGE_LOCKED = "storage.locked"
    STORAGE_MIGRATION_FAILED = "storage.migration_failed"
    STORAGE_CORRUPTION = "storage.corruption"
    CACHE_MISS_TRANSIENT = "cache.miss.transient"

    # ----- llm router / narration -----
    LLM_PROVIDER_ERROR = "llm.provider_error"
    LLM_BUDGET_EXCEEDED = "llm.budget_exceeded"
    LLM_TIMEOUT = "llm.timeout"
    NARRATION_GROUNDING_FAILED = "narration.grounding_failed"
    NARRATION_VALIDATION_FAILED = "narration.validation_failed"

    # ----- jobs / async -----
    JOB_NOT_FOUND = "job.not_found"
    JOB_CANCELLED = "job.cancelled"
    JOB_FAILED = "job.failed"


#: Codes that are normally retriable by clients (transient conditions).
RETRIABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.RATE_LIMITED,
        ErrorCode.STORAGE_LOCKED,
        ErrorCode.CACHE_MISS_TRANSIENT,
        ErrorCode.LLM_TIMEOUT,
        ErrorCode.LLM_PROVIDER_ERROR,
        ErrorCode.ENGINE_TIMEOUT,
    }
)
