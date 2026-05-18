"""Generic envelope models.

Mirror of protocol §3 (envelope conventions) and §10 (error envelope).
The Pydantic models here are the **single source of truth** that generates
``specs/v1.0/schemas/*.schema.json`` (Phase 1 onward; generator authored
later this commit batch's planning step).
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class _ProtocolModel(BaseModel):
    """Common config: forbid extra fields so contract drift is loud."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


T = TypeVar("T", bound=BaseModel)


class ErrorDetail(_ProtocolModel):
    """The error payload returned in non-2xx HTTP responses.

    Shape mirrors protocol §10. Field names match the spec exactly.
    """

    code: str = Field(
        ...,
        description="Stable, dotted error code from the registry (`spec §10`).",
        examples=["client.bad_request", "engine.timeout"],
    )
    message: str = Field(
        ...,
        description="Human-readable, single-line, never contains unsanitized user input.",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured, JSON-safe extras. May be empty.",
    )
    retriable: bool = Field(
        ...,
        description="Whether the client SHOULD retry after backoff.",
    )
    request_id: str | None = Field(
        default=None,
        description="Correlation id assigned by the gateway; echoes the X-Request-Id header.",
    )


class ErrorResponse(_ProtocolModel):
    """Outer envelope for error responses."""

    error: ErrorDetail


class OkResponse(_ProtocolModel, Generic[T]):
    """Outer envelope for successful responses.

    Per protocol §3, success bodies are ``{\"data\": <payload>}``.
    """

    data: T


__all__ = ["ErrorDetail", "ErrorResponse", "OkResponse"]
