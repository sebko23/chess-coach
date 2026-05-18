"""chess_coach.engine_orch — Engine Pool orchestrator.

Manages a bounded FIFO pool of UCI engine workers.
"""
from .pool import EnginePool, EngineSpec

__all__ = ["EnginePool", "EngineSpec"]
