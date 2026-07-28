"""BBF-87.1.y integration test: narrations.position_id is a real FK.

End-to-end test of POST /v1/narration/explain:
  - First call with a FEN creates a freeform positions row
    (game_id=NULL) and stores its id in narrations.position_id.
  - Second call with the same FEN reuses the same positions row
    (idempotent dedup); narrations has TWO rows, both with the
    SAME position_id, and positions has only ONE row.
  - Third call with a different FEN creates a NEW positions row;
    narrations has 3 rows, positions has 2 rows.
  - The migration 0009 makes positions.game_id nullable and
    adds a positions_fen_idx for the lookup.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chess_coach.narration.grounding import GroundingIndex
from chess_coach.narration.pipeline import NarrationPipeline

_PRE_CANNED_NARRATION = (
    "Try <move>e4</move> with eval <eval>+0.38</eval>."
)


def _make_stub_router() -> MagicMock:
    router = MagicMock()
    router.complete = AsyncMock(return_value=_PRE_CANNED_NARRATION)
    return router


@pytest.fixture
def fresh_db(tmp_path: Path) -> Path:
    """Build a SQLite DB with the production schema applied, including
    migration 0009.
    """
    from chess_coach.storage.migrate import migrate
    db_path = tmp_path / "chess_coach.db"
    migrate(db_path)
    return db_path


@pytest.mark.integration
class TestNarrationPositionFK:
    async def test_first_narration_creates_freeform_position(
        self, fresh_db: Path,
    ) -> None:
        """POST /v1/narration/explain with a fresh FEN creates a
        positions row with game_id=NULL and stores its id in
        narrations.position_id.
        """
        from chess_coach.gateway.auth import require_bearer
        from chess_coach.gateway.exception_handlers import (
            install_exception_handlers,
        )
        from chess_coach.gateway.routes.narration import (
            router as narration_router,
        )

        app = FastAPI()
        install_exception_handlers(app)
        pipeline = NarrationPipeline(
            router=_make_stub_router(),
            grounding=GroundingIndex(version="v2"),
        )
        app.state.gateway = MagicMock()
        app.state.gateway.settings = MagicMock()
        app.state.gateway.settings.sqlite_path = fresh_db
        app.state.narration_pipeline = pipeline
        app.dependency_overrides[require_bearer] = lambda: None
        app.include_router(narration_router)

        test_fen = (
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )
        client = TestClient(app)
        resp = client.post(
            "/v1/narration/explain",
            json={"fen": test_fen, "move_san": "e4", "eval_cp": 38},
        )
        assert resp.status_code == 200, resp.text

        # Verify positions row: 1 row, game_id=NULL, fen=test_fen.
        conn = sqlite3.connect(str(fresh_db))
        positions = conn.execute(
            "SELECT id, game_id, fen FROM positions"
        ).fetchall()
        conn.close()
        assert len(positions) == 1
        pos_id, game_id, fen = positions[0]
        assert game_id is None
        assert fen == test_fen

        # Verify narrations row: position_id is a real FK to positions.id.
        async with aiosqlite.connect(str(fresh_db)) as db, db.execute(
            "SELECT position_id FROM narrations"
        ) as cur:
            row = await cur.fetchone()
        assert row[0] == pos_id

    async def test_repeat_narration_reuses_same_position(
        self, fresh_db: Path,
    ) -> None:
        """Two narrations of the same FEN share the same positions.id
        (idempotent dedup).
        """
        from chess_coach.gateway.auth import require_bearer
        from chess_coach.gateway.exception_handlers import (
            install_exception_handlers,
        )
        from chess_coach.gateway.routes.narration import (
            router as narration_router,
        )

        app = FastAPI()
        install_exception_handlers(app)
        pipeline = NarrationPipeline(
            router=_make_stub_router(),
            grounding=GroundingIndex(version="v2"),
        )
        app.state.gateway = MagicMock()
        app.state.gateway.settings = MagicMock()
        app.state.gateway.settings.sqlite_path = fresh_db
        app.state.narration_pipeline = pipeline
        app.dependency_overrides[require_bearer] = lambda: None
        app.include_router(narration_router)

        test_fen = (
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )
        client = TestClient(app)
        for _ in range(2):
            resp = client.post(
                "/v1/narration/explain",
                json={"fen": test_fen, "eval_cp": 38},
            )
            assert resp.status_code == 200, resp.text

        # positions has 1 row; narrations has 2 rows; both narrations
        # share the same position_id.
        conn = sqlite3.connect(str(fresh_db))
        positions = conn.execute("SELECT id FROM positions").fetchall()
        narrations = conn.execute(
            "SELECT position_id FROM narrations ORDER BY created_at"
        ).fetchall()
        conn.close()
        assert len(positions) == 1
        assert len(narrations) == 2
        assert narrations[0][0] == narrations[1][0]
        assert narrations[0][0] == positions[0][0]

    async def test_different_fens_create_different_positions(
        self, fresh_db: Path,
    ) -> None:
        """Narrations of different FENs create different positions
        rows; the FK preserves referential integrity.
        """
        from chess_coach.gateway.auth import require_bearer
        from chess_coach.gateway.exception_handlers import (
            install_exception_handlers,
        )
        from chess_coach.gateway.routes.narration import (
            router as narration_router,
        )

        app = FastAPI()
        install_exception_handlers(app)
        pipeline = NarrationPipeline(
            router=_make_stub_router(),
            grounding=GroundingIndex(version="v2"),
        )
        app.state.gateway = MagicMock()
        app.state.gateway.settings = MagicMock()
        app.state.gateway.settings.sqlite_path = fresh_db
        app.state.narration_pipeline = pipeline
        app.dependency_overrides[require_bearer] = lambda: None
        app.include_router(narration_router)

        fen_a = (
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )
        fen_b = (
            "rnbqkbnr/pp1ppppp/8/2b5/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1"
        )
        client = TestClient(app)
        for fen in (fen_a, fen_b):
            resp = client.post(
                "/v1/narration/explain",
                json={"fen": fen, "eval_cp": 38},
            )
            assert resp.status_code == 200, resp.text

        conn = sqlite3.connect(str(fresh_db))
        positions = conn.execute("SELECT fen FROM positions").fetchall()
        narrations = conn.execute(
            "SELECT position_id, fen FROM narrations "
            "JOIN positions ON narrations.position_id = positions.id"
        ).fetchall()
        conn.close()
        assert len(positions) == 2
        position_fens = {p[0] for p in positions}
        assert position_fens == {fen_a, fen_b}
        assert len(narrations) == 2
        # Each narration's position_id is its respective FEN's row.
        assert all(fen in (fen_a, fen_b) for (_, fen) in narrations)
        # position_id values are distinct (different FENs -> different rows).
        pos_ids = {row[0] for row in narrations}
        assert len(pos_ids) == 2

    def test_migration_0009_makes_game_id_nullable(
        self, fresh_db: Path,
    ) -> None:
        """Migration 0009 makes positions.game_id nullable and
        adds a fen index.
        """
        conn = sqlite3.connect(str(fresh_db))
        cols = conn.execute("PRAGMA table_info(positions)").fetchall()
        game_id_col = next(c for c in cols if c[1] == "game_id")
        assert game_id_col[3] == 0  # notnull=0 means nullable
        idx = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='positions'"
        ).fetchall()
        idx_names = [i[0] for i in idx]
        assert "positions_fen_idx" in idx_names
        # And the legacy positions__0009_old table is gone.
        leftover = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'positions%'"
        ).fetchall()
        leftover_names = [t[0] for t in leftover]
        assert "positions" in leftover_names
        assert "positions__0009_old" not in leftover_names
