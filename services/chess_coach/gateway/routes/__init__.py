"""Route-builders for the gateway.

Each feature area exposes a ``build_<area>_router`` factory; ``app.create_app``
includes them under stable URL prefixes.
"""
from __future__ import annotations

from .system import build_system_router

__all__ = ["build_system_router"]
