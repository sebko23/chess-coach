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

# BBF-86.1a: the imports below MUST come after `load_dotenv()` so
# `chess_coach.config` (and the rest of the modules that read
# os.environ at import time) sees the .env values before they're
# first read. The existing precedent (set by BBF-87.1) covers
# `GroundingIndex`; this commit extends the same rationale to the
# rest of the contiguous import cluster.
import asyncio  # noqa: E402
import contextlib  # noqa: E402
import logging  # noqa: E402
import pathlib  # noqa: E402
import platform  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from typing import TYPE_CHECKING  # noqa: E402

from fastapi import FastAPI, Request, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from chess_coach.engine_orch.pool import EnginePool, EngineSpec  # noqa: E402
from chess_coach.kb.pipeline import index_positions  # noqa: E402
from chess_coach.narration import NarrationPipeline  # noqa: E402
from chess_coach.narration.grounding import (  # noqa: E402
    GroundingIndex,  # noqa: E402  (BBF-87.1; follows existing app.py E402 pattern)
)
from chess_coach.storage import ensure_writable, migrate  # noqa: E402

from .auth import generate_token_if_needed, set_active_token  # noqa: E402
from .config import GatewaySettings  # noqa: E402
from .descriptor import Descriptor, remove_descriptor  # noqa: E402
from .exception_handlers import install_exception_handlers  # noqa: E402
from .routes import (  # noqa: E402
    analysis_router,
    backfill_analyses_router,
    blunder_router,
    engines_router,
    eval_graph_router,
    eval_verifier_router,
    game_router,
    kb_router,
    lichess_import_router,
    narration_router,
    pdf_ingest_router,
    pgn_import_router,
    players_router,
    profile_analysis_router,
    profile_router,
    repertoire_recommendations_router,
    repertoire_router,
    training_planner_router,
    training_router,
)
from .routes.system import build_system_router  # noqa: E402

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
        if not await asyncio.to_thread(pathlib.Path(stockfish_path).exists):
            stockfish_path = 'stockfish'  # fallback to PATH
        maia_path = '/a0/usr/projects/chess_coach/data/engines/lc0'
        maia_weights = '/a0/usr/projects/chess_coach/data/engines/maia-1500.pb'
        maia_path_exists, maia_weights_exist = await asyncio.gather(
            asyncio.to_thread(pathlib.Path(maia_path).exists),
            asyncio.to_thread(pathlib.Path(maia_weights).exists),
        )
        maia_available = maia_path_exists and maia_weights_exist

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

        import os
        # (env_workers / max_workers handling moved into the engine_pool block below; BBF-19)
        # Single Stockfish is single-coroutine, but with N slots we can
        # run N analyses truly in parallel — each slot owns its own
        # subprocess and per-slot lock. BBF-19.
        env_workers = int(os.environ.get("CHESS_COACH_MAX_WORKERS", "0"))
        max_workers = env_workers if env_workers > 0 else 1
        engine_pool = EnginePool(specs, max_workers=max_workers)
        app.state.engine_pool = engine_pool  # type: ignore[attr-defined]
        # Warmup: start all N stockfish subprocesses eagerly so the
        # first PGN import doesn't pay Nx cold-start cost.
        await engine_pool.warmup()
        logger.info(
            "gateway.startup: engine pool max_workers=%d (CHESS_COACH_MAX_WORKERS env)",
            max_workers,
        )
        logger.info(
            "gateway.startup: engine pool ready (stockfish=%s, maia=%s, workers=%d)",
            stockfish_path,
            "yes" if maia_available else "no",
            max_workers,
        )
    else:
        engine_pool = app.state.engine_pool  # type: ignore[attr-defined]
        logger.info("gateway.startup: engine pool pre-injected, skipping auto-init")

    # 1c. Narration pipeline (stored on app.state for FastAPI Depends).
    # BBF-87.1: load the v2 narrative corpus as a GroundingIndex and
    # pass it to the pipeline. The pipeline looks up FENs against
    # this index per request; missing FENs are no-ops (the pipeline
    # behaves exactly as before for ungrounded calls).
    _grounding_index = GroundingIndex(version="v2")
    if _grounding_index.size > 0:
        logger.info(
            "narration: loaded v2 corpus with %d entries for FEN grounding",
            _grounding_index.size,
        )
    else:
        # BBF-86.6: emit a WARNING at the gateway logger (not just
        # the GroundingIndex constructor) so the degraded mode is
        # visible in the gateway's startup log. Production deploys
        # ship the corpus via Dockerfile COPY (BBF-87.1 + 87.1.y
        # follow-up), so this WARNING only fires for dev/test
        # environments or mis-configured production.
        logger.warning(
            "narration: v2 grounding corpus loaded with 0 entries; "
            "narration will run without FEN-based grounding. This is "
            "the pre-BBF-87.1 behavior for FENs that don't match the "
            "v1 corpus. Status 'degraded' will be reported by "
            "GET /v1/system/health."
        )
    app.state.narration_pipeline = NarrationPipeline(  # type: ignore[attr-defined]
        grounding=_grounding_index,
    )
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

    # BBF-86.6: the health endpoint surfaces a `narration_grounding`
    # component whose status reflects the in-process GroundingIndex
    # size. The closure reads `app.state.narration_pipeline._grounding.size`
    # at request time (not at router build time) so the status is
    # always live. Returns None when the pipeline / grounding index
    # is not yet wired (e.g. tests that bypass lifespan), which the
    # router treats as `ok` for backwards compatibility.
    def _grounding_size() -> int | None:
        pipeline = getattr(app.state, "narration_pipeline", None)
        if pipeline is None:
            return None
        gi = getattr(pipeline, "_grounding", None)
        if gi is None:
            return None
        return gi.size

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
            grounding_size_fn=_grounding_size,
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
    app.include_router(pgn_import_router)
    app.include_router(backfill_analyses_router)
    app.include_router(eval_verifier_router)

    return app


__all__ = [
    "BACKEND_VERSION",
    "CAPABILITIES",
    "GatewayState",
    "PROTOCOL_MAX",
    "PROTOCOL_MIN",
    "create_app",
]
