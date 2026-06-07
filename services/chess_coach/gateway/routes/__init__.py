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
from .profile import router as profile_router
from .repertoire import router as repertoire_router
from .training import router as training_router

from .pdf_ingest import router as pdf_ingest_router
from .lichess_import import router as lichess_import_router
from .repertoire_recommendations import router as repertoire_recommendations_router
# system.py uses a builder pattern (build_system_router); kept as-is.

__all__ = [
    "analysis_router",
    "blunder_router",
    "engines_router",
    "eval_graph_router",
    "game_router",
    "narration_router",
    "profile_router",
    "repertoire_router",
    "training_router",
    "pdf_ingest_router",
    "lichess_import_router",
    "repertoire_recommendations_router",
]
