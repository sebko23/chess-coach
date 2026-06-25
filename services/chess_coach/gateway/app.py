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

from dotenv import load_dotenv
load_dotenv()

import contextlib
import logging
import pathlib
import platform
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware


from chess_coach.storage import ensure_writable, migrate

from .auth import generate_token_if_needed, set_active_token
from .config import GatewaySettings
from .descriptor import Descriptor, remove_descriptor, write_descriptor
from .routes import (
    analysis_router,
    blunder_router,
    engines_router,
    eval_graph_router,
    game_router,
    repertoire_router,
    narration_router,
    profile_router,
    training_router,
    pdf_ingest_router,
    lichess_import_router,
    repertoire_recommendations_router,
    profile_analysis_router,
    training_planner_router,
    players_router,
    kb_router,
)
from chess_coach.engine_orch.pool import EnginePool, EngineSpec
from chess_coach.narration import NarrationPipeline
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
        maia_path = '/a0/usr/projects/chess_coach/data/engines/lc0'
        maia_weights = '/a0/usr/projects/chess_coach/data/engines/maia-1500.pb'
        import pathlib as _pathlib
        maia_available = _pathlib.Path(maia_path).exists() and _pathlib.Path(maia_weights).exists()

        specs = [EngineSpec(engine_id="stockfish", path=stockfish_path)]
        if maia_available:
            specs.append(EngineSpec(
                engine_id="maia",
                path=maia_path,
                extra_args=[
                    "classic",
                    f"--weights={maia_weights}",
                    "--backend=blas",
                ],
                skip_options={"Hash", "Threads"},
            ))

        engine_pool = EnginePool(specs, max_workers=1)
        app.state.engine_pool = engine_pool  # type: ignore[attr-defined]
        await engine_pool._acquire(  # type: ignore[attr-defined]
            EngineSpec(engine_id="stockfish", path=stockfish_path), {}
        )
        logger.info(
            "gateway.startup: engine pool ready (stockfish=%s, maia=%s)",
            stockfish_path,
            "yes" if maia_available else "no",
        )
    else:
        engine_pool = app.state.engine_pool  # type: ignore[attr-defined]
        logger.info("gateway.startup: engine pool pre-injected, skipping auto-init")

    # 1c. Narration pipeline (stored on app.state for FastAPI Depends)
    app.state.narration_pipeline = NarrationPipeline()  # type: ignore[attr-defined]
    # 1d. Memory KB store — eager init, index positions from SQLite
    _kb_t0 = time.time()
    _db_path = str(state.settings.sqlite_path)
    _qdrant_url = state.settings.qdrant_url
    _qdrant_key = state.settings.qdrant_api_key
    logger.info("kb: using Qdrant at %s", _qdrant_url)
    if _qdrant_url == ":memory:":
        logger.info("kb: skipping eager index in :memory: mode")
    else:
        try:
            _kb_count = index_positions(
                _db_path,
                limit=5000,
                qdrant_url=_qdrant_url,
                qdrant_api_key=_qdrant_key,
            )
            logger.info(
                "kb: indexed %d positions in %.2fs",
                _kb_count,
                time.time() - _kb_t0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kb: index_positions failed (%s) — KB will return empty results",
                exc,
            )
    app.state.kb_ready = True  # type: ignore[attr-defined]
    logger.info("gateway.startup: narration pipeline ready")

    # 2. Token.
    token = generate_token_if_needed(settings.backend_token)
    set_active_token(token)

    logger.info(
        "gateway.startup: backend_version=%s protocol=%s..%s data_dir=%s",
        BACKEND_VERSION, PROTOCOL_MIN, PROTOCOL_MAX, settings.data_dir,
    )

    try:
        yield
    finally:
        if state.descriptor is not None:
            remove_descriptor(settings.descriptor_path)
        else:
            remove_descriptor(settings.descriptor_path)
        try:
            await engine_pool.shutdown()  # type: ignore[attr-defined]
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
    settings = settings or GatewaySettings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="CHESS COACH Backend",
        version=BACKEND_VERSION,
        description=(
            "Conforming implementation of the CHESS COACH GUI <-> Backend "
            "protocol; see specs/v1.0/chess-coach-protocol-v1.md."
        ),
        responses={},
        lifespan=_lifespan,
    )
    app.state.gateway = GatewayState(  # type: ignore[attr-defined]
        settings=settings,
        started_at=time.monotonic(),
    )

    install_exception_handlers(app)
    app.middleware("http")(_request_id_middleware)

    # CORS: required for Tauri dev mode (Vite dev server at localhost:1420)
    # Also allows production Tauri webview (tauri://localhost)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "tauri://localhost"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

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

    app.include_router(engines_router)
    app.include_router(analysis_router)
    app.include_router(narration_router)

    app.include_router(training_router)
    app.include_router(eval_graph_router)
    app.include_router(blunder_router)
    app.include_router(game_router)
    app.include_router(repertoire_router)
    app.include_router(pdf_ingest_router)
    app.include_router(lichess_import_router)
    app.include_router(repertoire_recommendations_router)
    app.include_router(profile_router)
    app.include_router(profile_analysis_router)
    app.include_router(training_planner_router)
    app.include_router(players_router)
    app.include_router(kb_router)

    return app


__all__ = [
    "BACKEND_VERSION",
    "CAPABILITIES",
    "GatewayState",
    "PROTOCOL_MAX",
    "PROTOCOL_MIN",
    "create_app",
]
