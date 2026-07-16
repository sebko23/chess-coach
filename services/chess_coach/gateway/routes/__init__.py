"""Gateway route modules.

Each submodule registers its own FastAPI router; the app includes them
in ``app.py`` via ``app.include_router(router)``.
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

from .pdf_ingest import router as pdf_ingest_router
from .lichess_import import router as lichess_import_router
from .repertoire_recommendations import router as repertoire_recommendations_router
from .profile_analysis import router as profile_analysis_router
from .training_planner import router as training_planner_router
from .kb import kb_router
from .pgn_import import router as pgn_import_router
from .backfill_analyses import router as backfill_analyses_router
from .eval_verifier import router as eval_verifier_router  # BBF-64
# system.py uses a builder pattern (build_system_router); kept as-is.

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
    "eval_verifier_router",
]