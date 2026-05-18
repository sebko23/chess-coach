"""FastAPI application factory and lifespan.

The lifespan handler:
  1. Validates the data directory is writable (storage.ensure_writable).
  2. Runs SQLite migrations (storage.migrate).
  3. Resolves the active session token (config.backend_token or fresh).
  4. Starts a single uvicorn server (handled by __main__).
  5. Writes ``backend.json`` AFTER uvicorn has bound a port — so we know the
     real port even if config.port == 0.
  6. On shutdown, removes ``backend.json``.

ADR-0001: one event loop. ADR-0002: typed exceptions only.
"""
from __future__ import annotations

import contextlib
import logging
import platform
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response

from chess_coach.storage import ensure_writable, migrate

from .auth import generate_token_if_needed, set_active_token
from .config import GatewaySettings
from .descriptor import Descriptor, remove_descriptor, write_descriptor
from .routes import engines_router, analysis_router
from chess_coach.engine_orch.pool import EnginePool, EngineSpec
from .exception_handlers import install_exception_handlers
from .routes.system import build_system_router

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

#: Backend semver. Bumped on releases; not the protocol version.
BACKEND_VERSION = "0.1.0"

#: Protocol versions this backend serves.
PROTOCOL_MIN = "1.0.0"
PROTOCOL_MAX = "1.0.0"

#: Capabilities advertised on /v1/system/info; Phase 1 minimum.
CAPABILITIES: list[str] = []  # populated as features land


@dataclass(slots=True)
class GatewayState:
    """Process-wide state held on ``app.state`` for handlers."""

    settings: GatewaySettings
    started_at: float
    descriptor: Descriptor | None = None


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    # Idempotent: replace any existing root handlers.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
    # Quiet uvicorn's noisy access logger by default; users can re-enable.
    logging.getLogger("uvicorn.access").setLevel(max(level, logging.WARNING))


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    state: GatewayState = app.state.gateway  # type: ignore[attr-defined]
    settings = state.settings

    # 1. Filesystem sanity + migrations.
    ensure_writable(settings.sqlite_path)
    applied = migrate(settings.sqlite_path, backups_dir=settings.backups_dir)
    if applied:
        logger.info("gateway.startup: applied %d migration(s)", len(applied))

    # 1b. Engine pool (skip if already injected, e.g. by test fixtures)
    if not hasattr(app.state, 'engine_pool') or getattr(app.state, 'engine_pool', None) is None:
        stockfish_path = '/usr/local/bin/stockfish'
        if not pathlib.Path(stockfish_path).exists():
            stockfish_path = 'stockfish'  # fallback to PATH
        app.state.engine_pool = EnginePool(  # type: ignore[attr-defined]
            [EngineSpec(engine_id="stockfish", path=stockfish_path)],
            max_workers=1,
        )
        # Pre-warm the engine subprocess
        await app.state.engine_pool._acquire(  # type: ignore[attr-defined]
            EngineSpec(engine_id="stockfish", path=stockfish_path), {}
        )
        logger.info("gateway.startup: engine pool ready (stockfish=%s)", stockfish_path)
    else:
        logger.info("gateway.startup: engine pool pre-injected, skipping auto-init")

    # 2. Token.
    token = generate_token_if_needed(settings.backend_token)
    set_active_token(token)

    # 3. Descriptor write happens AFTER uvicorn binds; see __main__.
    # (Lifespan runs inside uvicorn but BEFORE serving traffic; the bound
    # port is already assigned by the time lifespan startup executes, but the
    # gateway itself doesn't know which port without uvicorn's cooperation.
    # __main__ reads the bound socket and stamps state.descriptor before
    # entering the serve loop.)

    logger.info(
        "gateway.startup: backend_version=%s protocol=%s..%s data_dir=%s",
        BACKEND_VERSION, PROTOCOL_MIN, PROTOCOL_MAX, settings.data_dir,
    )

    try:
        yield
    finally:
        if state.descriptor is not None:
            remove_descriptor(settings.descriptor_path)
            logger.info("gateway.shutdown: removed %s", settings.descriptor_path)
        else:
            # Defensive cleanup: descriptor may still exist if lifespan was
            # interrupted mid-startup.
            remove_descriptor(settings.descriptor_path)
        try:
            await app.state.engine_pool.shutdown()  # type: ignore[attr-defined]
            logger.info("gateway.shutdown: engine pool stopped")
        except Exception as exc:
            logger.warning("gateway.shutdown: engine pool error: %s", exc)
        logger.info("gateway.shutdown: complete")


async def _request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = rid
    response = await call_next(request)
    response.headers.setdefault("X-Request-Id", rid)
    return response


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    """Build the FastAPI app.

    Importing this module has no side effects; all wiring happens here.
    """
    settings = settings or GatewaySettings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="CHESS COACH Backend",
        version=BACKEND_VERSION,
        description=(
            "Conforming implementation of the CHESS COACH GUI <-> Backend "
            "protocol; see specs/v1.0/chess-coach-protocol-v1.md."
        ),
        # We define our own envelope shape; suppress FastAPI's default 422 schema.
        responses={},
        lifespan=_lifespan,
    )
    app.state.gateway = GatewayState(  # type: ignore[attr-defined]
        settings=settings,
        started_at=time.monotonic(),
    )

    install_exception_handlers(app)
    app.middleware("http")(_request_id_middleware)

    # Routers
    app.include_router(
        build_system_router(
            backend_version=BACKEND_VERSION,
            protocol_min=PROTOCOL_MIN,
            protocol_max=PROTOCOL_MAX,
            capabilities=CAPABILITIES,
            runtime_info={
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
        ),
        prefix="/v1/system",
        tags=["system"],
    )

    # Engine management + analysis routes
    app.include_router(engines_router)
    app.include_router(analysis_router)

    return app


__all__ = [
    "BACKEND_VERSION",
    "CAPABILITIES",
    "GatewayState",
    "PROTOCOL_MAX",
    "PROTOCOL_MIN",
    "create_app",
]
