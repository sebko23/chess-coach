"""Models for ``/v1/system/*`` endpoints.

Phase-1 minimal subset; sufficient for client discovery and health checks.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .envelopes import _ProtocolModel


class SystemInfo(_ProtocolModel):
    """Returned by ``GET /v1/system/info``.

    Lets a client (typically the GUI) confirm protocol-version compatibility
    and discover what the backend can do without poking at every endpoint.
    """

    backend_version: str = Field(..., description="Backend semver, e.g. '0.1.0'.")
    protocol_min: str = Field(..., description="Lowest supported protocol version.")
    protocol_max: str = Field(..., description="Highest supported protocol version.")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Stable capability flags the client can rely on.",
        examples=[["engine.stockfish", "narration.grounded"]],
    )
    runtime: dict[str, str] = Field(
        default_factory=dict,
        description="Free-form runtime info (python_version, platform, etc.). Advisory only.",
    )


HealthStatus = Literal["ok", "degraded", "unhealthy"]


class HealthCheckComponent(_ProtocolModel):
    """Per-subsystem health entry."""

    name: str = Field(..., description="Subsystem name, e.g. 'storage', 'engine_orch'.")
    status: HealthStatus
    message: str | None = Field(
        default=None,
        description="Optional one-line explanation; absent when status is 'ok'.",
    )


class HealthCheck(_ProtocolModel):
    """Returned by ``GET /v1/system/health``."""

    status: HealthStatus = Field(..., description="Overall rollup of component statuses.")
    components: list[HealthCheckComponent] = Field(
        default_factory=list,
        description="Per-component breakdown.",
    )
    uptime_seconds: float = Field(..., ge=0.0, description="Seconds since gateway start.")


__all__ = ["HealthCheck", "HealthCheckComponent", "HealthStatus", "SystemInfo"]
