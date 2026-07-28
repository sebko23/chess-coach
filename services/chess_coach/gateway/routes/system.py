"""``/v1/system/*`` endpoints.

- ``GET /v1/system/info``   - protocol/backend version + capabilities (§4)
- ``GET /v1/system/health`` - rolled-up component health (§4)

Both require bearer auth per protocol §2; the gateway holds the active token.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from chess_coach.protocol_types import (
    HealthCheck,
    HealthCheckComponent,
    OkResponse,
    SystemInfo,
)

from ..auth import require_bearer

#: Signature of the callback that reports the in-process GroundingIndex
#: entry count. Returns ``None`` when the pipeline has not been
#: initialised yet (e.g. very early health probes). BBF-86.6.
GroundingSizeFn = Callable[[], int | None]


def build_system_router(
    *,
    backend_version: str,
    protocol_min: str,
    protocol_max: str,
    capabilities: list[str],
    runtime_info: Mapping[str, str],
    grounding_size_fn: GroundingSizeFn | None = None,
) -> APIRouter:
    """Construct the router. Runtime values are captured at startup time.

    `grounding_size_fn` is the BBF-86.6 hook that lets the health
    endpoint surface a `narration_grounding` component whose status
    reflects whether the GroundingIndex has any entries. Production
    passes a closure that reads `app.state.narration_pipeline._grounding.size`;
    tests pass deterministic values or ``None`` to disable the
    component. When ``None``, the component is omitted (backwards
    compatible with the pre-BBF-86.6 surface).
    """
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
        # BBF-86.6: surface a `narration_grounding` component whose
        # status reflects the in-process GroundingIndex entry count.
        # Empty index (corpus missing or empty) yields `degraded` so
        # the silent-failure mode from BBF-86 F2 becomes visible
        # to operators without taking the gateway out of rotation.
        # Load balancers should treat `degraded` as informational.
        if grounding_size_fn is not None:
            grounding_size = grounding_size_fn()
            if grounding_size is None:
                grounding_status: str = "ok"
                grounding_message = None
            elif grounding_size > 0:
                grounding_status = "ok"
                grounding_message = None
            else:
                grounding_status = "degraded"
                grounding_message = (
                    "narrative grounding corpus is empty (0 entries); "
                    "narration will run without FEN-based grounding. "
                    "Check that the corpus directory is shipped via "
                    "Dockerfile COPY and contains valid entries."
                )
            components.append(
                HealthCheckComponent(
                    name="narration_grounding",
                    status=grounding_status,  # type: ignore[arg-type]
                    message=grounding_message,
                )
            )
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
