"""Gateway route modules.

Each submodule registers its own FastAPI router; the app includes them
in ``app.py`` via ``app.include_router(router)``.
"""
from .analysis import router as analysis_router
from .engines import router as engines_router
from .narration import router as narration_router

# system.py uses a builder pattern (build_system_router); kept as-is.

__all__ = ["analysis_router", "engines_router", "narration_router"]
