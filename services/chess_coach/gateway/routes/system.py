"""``/v1/system/*`` endpoints.

- ``GET /v1/system/info``   - protocol/backend version + capabilities (§4)
- ``GET /v1/system/health`` - rolled-up component health (§4)

Both require bearer auth per protocol §2; the gateway holds the active token.
"""
from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from chess_coach.protocol_types import (
    HealthCheck,
    HealthCheckComponent,
    OkResponse,
    SystemInfo,
)

from ..auth import require_bearer


def build_system_router(
    *,
    backend_version: str,
    protocol_min: str,
    protocol_max: str,
    capabilities: list[str],
    runtime_info: Mapping[str, str],
) -> APIRouter:
    """Construct the router. Runtime values are captured at startup time."""
    router = APIRouter()

    @router.get(
        "/info",
        response_model=OkResponse[SystemInfo],
        summary="Backend identity and protocol-version compatibility.",
    )
    async def system_info(
        _: Annotated[None, Depends(require_bearer)],
    ) -> OkResponse[SystemInfo]:
        return OkResponse[SystemInfo](
            data=SystemInfo(
                backend_version=backend_version,
                protocol_min=protocol_min,
                protocol_max=protocol_max,
                capabilities=list(capabilities),
                runtime=dict(runtime_info),
            )
        )

    @router.get(
        "/health",
        response_model=OkResponse[HealthCheck],
        summary="Component health rollup.",
    )
    async def system_health(
        request: Request,
        _: Annotated[None, Depends(require_bearer)],
    ) -> OkResponse[HealthCheck]:
        # Phase-1 placeholder: only the gateway component reports for now.
        # Other components will register their own health probes as they land.
        gateway_state = request.app.state.gateway
        uptime = max(0.0, time.monotonic() - gateway_state.started_at)
        components = [
            HealthCheckComponent(name="gateway", status="ok"),
            HealthCheckComponent(name="storage", status="ok"),
        ]
        # Rollup: worst-of by severity.
        order = {"ok": 0, "degraded": 1, "unhealthy": 2}
        worst = max(order[c.status] for c in components) if components else 0
        rollup = next(s for s, n in order.items() if n == worst)
        return OkResponse[HealthCheck](
            data=HealthCheck(
                status=rollup,  # type: ignore[arg-type]
                components=components,
                uptime_seconds=uptime,
            )
        )

    return router


__all__ = ["build_system_router"]
