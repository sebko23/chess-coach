"""SQLite storage layer.

The migration runner lives at :mod:`chess_coach.storage.migrate`; ADR-0003.
Storage models (Pydantic) will be added in :mod:`chess_coach.storage.models`
as Phase-1 features land.
"""
from __future__ import annotations

import sys as _sys
if "chess_coach.storage.migrate" not in _sys.modules:
    from .migrate import (
        Migration,
        discover_migrations,
        ensure_writable,
        get_user_version,
        migrate,
        rebuild_clean,
        set_user_version,
    )

__all__ = [
    "Migration",
    "discover_migrations",
    "ensure_writable",
    "get_user_version",
    "migrate",
    "rebuild_clean",
    "set_user_version",
]
