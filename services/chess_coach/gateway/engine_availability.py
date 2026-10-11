"""Gateway-side engine availability check helper.

This module exists because ADR-0002 (see
libs/chess_coach/errors/exceptions.py docstring) forbids code outside
the gateway from raising FastAPI ``HTTPException``. The engine pool's
``is_available()`` method lives in ``engine_orch/pool.py`` (a
non-gateway module) — that's correct, because the method only checks
state, it doesn't raise HTTP-flavoured exceptions. But the *route-level
check* (raise 503 if the engine was never acquired) does raise an
HTTPException, so it must live on the gateway side.

Plain helper (not a FastAPI ``Depends``) so each route can call it
inline after resolving ``engine_id`` from its own parameter source
(path, query, POST body, or hardcoded). All engine-consuming routes
use this single helper so the 503 error envelope lives in exactly
one place.

Matches the existing 503 body shape used by ``routes/engines.py``'s
``_pool`` dependency for "pool not initialized" — same code/message
dict, same ``ErrorCode.SERVER_UNAVAILABLE`` — so both error
conditions surface identically to callers.
"""
from __future__ import annotations

from fastapi import HTTPException

from chess_coach.engine_orch.pool import EnginePool
from chess_coach.errors.codes import ErrorCode


def require_engine_available(pool: EnginePool, engine_id: str) -> None:
    """Phase 8 BBF-2 Fix 3 Part B: raise 503 if engine_id has no live slots.

    Plain helper (not a FastAPI Depends) so each route can call it
    inline after resolving engine_id from its own parameter source
    (path, query, POST body, or hardcoded). All engine-consuming
    routes use this single helper so the 503 error envelope lives in
    exactly one place.

    Matches the existing 503 body shape (code/message dict,
    ErrorCode.SERVER_UNAVAILABLE) for consistency across route-level
    "pool not initialized" and "engine not acquired" errors.
    """
    if not pool.is_available(engine_id):
        raise HTTPException(
            status_code=503,
            detail={
                "code": ErrorCode.SERVER_UNAVAILABLE.value,
                "message": f"engine {engine_id} not available",
            },
        )
