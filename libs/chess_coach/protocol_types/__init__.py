"""Pydantic models that mirror ``specs/v1.0/``.

Single source of truth for JSON Schemas published at
``specs/v1.0/schemas/`` (generator to be authored at
``tools/gen/regen_schemas.py``).

ADR-0003 §4: storage models and protocol models are deliberately separate;
these are the **protocol** models.
"""
from __future__ import annotations

from .envelopes import ErrorDetail, ErrorResponse, OkResponse
from .system import HealthCheck, HealthCheckComponent, HealthStatus, SystemInfo

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "HealthCheck",
    "HealthCheckComponent",
    "HealthStatus",
    "OkResponse",
    "SystemInfo",
]
