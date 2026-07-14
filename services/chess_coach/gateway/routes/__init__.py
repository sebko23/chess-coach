"""Gateway route modules.

Each submodule registers its own FastAPI router; the app includes them
in ``app.py`` via ``app.include_router(router)``.

BBF-39: ``pdf_ingest`` is loaded lazily via module-level ``__getattr__``
(PEP 562) because it pulls in ``pdf2image`` (a native dep that
requires ``poppler-utils`` and is not installed in the runtime
Docker image). Eagerly importing the module crashed the gateway on
startup with ``ModuleNotFoundError: No module named 'pdf2image'``,
taking the whole smoke CI red. Now the import happens only when
``pdf_ingest_router`` is first accessed, so a missing optional dep
surfaces as a 5xx on the affected endpoint, not a process exit.
"""
from .analysis import router as analysis_router
from .blunder_routes import router as blunder_router
from .engines import router as engines_router
from .eval_graph import router as eval_graph_router
from .game_routes import router as game_router
from .narration import router as narration_router
from .players import router as players_router
from .profile import router as profile_router
from .repertoire import router as repertoire_router
from .training import router as training_router

# Lazy-loaded below: pdf_ingest_router, lichess_import_router,
# repertoire_recommendations_router, profile_analysis_router,
# training_planner_router, kb_router, pgn_import_router,
# backfill_analyses_router. See __getattr__ at the bottom of this file.

from .lichess_import import router as lichess_import_router
from .repertoire_recommendations import router as repertoire_recommendations_router
from .profile_analysis import router as profile_analysis_router
from .training_planner import router as training_planner_router
from .kb import kb_router
from .pgn_import import router as pgn_import_router
from .backfill_analyses import router as backfill_analyses_router
# system.py uses a builder pattern (build_system_router); kept as-is.

# ---- BBF-39: lazy pdf_ingest (pdf2image dep is not in the runtime image) ----
# Without this, importing routes.pdf_ingest_router at gateway startup
# pulls in pdf2image, which is not installed, and crashes the whole
# process. With this, the import happens only on first attribute access,
# so the gateway can start and serve all other endpoints even when the
# PDF ingest feature is unavailable.

_LAZY_ROUTE_MODULES = {
    "pdf_ingest_router": "pdf_ingest",
}


def __getattr__(name: str):
    """PEP 562 module-level lazy attribute access.

    Only ``pdf_ingest_router`` is lazy today; the rest of the routes
    are eagerly imported above. Add new entries to
    ``_LAZY_ROUTE_MODULES`` here as more optional-dependency routes
    appear.
    """
    module_name = _LAZY_ROUTE_MODULES.get(name)
    if module_name is None:
        raise AttributeError(
            f"module 'chess_coach.gateway.routes' has no attribute {name!r}"
        )
    import importlib
    module = importlib.import_module(f".{module_name}", __name__)
    value = getattr(module, "router")
    # Cache on the module so subsequent accesses are O(1).
    globals()[name] = value
    return value


def __dir__():
    # Help REPL / debugger auto-completion; keeps the public surface
    # honest with __all__.
    return sorted(set(__all__) | set(globals().keys()))


__all__ = [
    "analysis_router",
    "blunder_router",
    "engines_router",
    "eval_graph_router",
    "game_router",
    "narration_router",
    "players_router",
    "profile_router",
    "repertoire_router",
    "training_router",
    "pdf_ingest_router",
    "lichess_import_router",
    "repertoire_recommendations_router",
    "profile_analysis_router",
    "training_planner_router",
    "kb_router",
    "pgn_import_router",
    "backfill_analyses_router",
]
