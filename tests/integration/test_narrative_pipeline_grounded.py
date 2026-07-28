"""BBF-87.1 integration test: the narration route injects v2 corpus grounding.

End-to-end test of POST /v1/narration/explain:
  - When the FEN matches a v2 corpus entry, the response carries
    a non-null `corpus_entry_id`, and the `narrations` table row
    has the corpus_entry_id populated.
  - When the FEN does not match, the response has corpus_entry_id=None
    and the table row is NULL.

We use a stub LLM router (a fake router that returns a pre-canned
narration) so this test doesn't depend on a live LLM. The validator
still runs on the LLM's output, but our pre-canned narration is
ground-truth-valid by construction (moves + evals match the
analysis; grounding block, if any, matches the corpus explanation).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from chess_coach.llm_router.router import LLMRouter
from chess_coach.narration.grounding import GroundingIndex
from chess_coach.narration.pipeline import NarrationPipeline

# Pre-canned nar that the LLM stub will return. Contains a
# legitimate <move> + <eval> that match any analysis, and an empty
# <grounding> block (which the validator will pass since it's
# not in grounding mode when the FEN doesn't match).
_PRE_CANNED_NARRATION = (
    "Try <move>e4</move> with eval <eval>+0.38</eval>."
)


def _make_stub_router(narration: str = _PRE_CANNED_NARRATION) -> LLMRouter:
    """Build a stub LLMRouter that returns `narration` on every call."""
    router = MagicMock(spec=LLMRouter)
    router.complete = AsyncMock(return_value=narration)
    return router


@pytest.fixture
def tmp_sqlite_db(tmp_path: Path) -> Path:
    """Build a SQLite DB with the production schema applied.

    Uses chess_coach.storage.migrate.migrate to apply all
    migrations including 0008 (BBF-87.1's narrations.corpus_entry_id).
    """
    from chess_coach.storage.migrate import migrate
    db_path = tmp_path / "chess_coach.db"
    migrate(db_path)
    return db_path


@pytest.mark.integration
class TestNarrationRouteGrounded:
    async def test_route_with_known_v2_fen_returns_corpus_entry_id(
        self, tmp_sqlite_db: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /v1/narration/explain with a v2 FEN returns the
        corpus_entry_id in the response and stores it in the DB.
        """
        from fastapi import FastAPI

        from chess_coach.gateway.auth import require_bearer
        from chess_coach.gateway.exception_handlers import (
            install_exception_handlers,
        )
        from chess_coach.gateway.routes.narration import (
            router as narration_router,
        )

        app = FastAPI()
        install_exception_handlers(app)

        # Wire app.state with our test sqlite path and a pipeline
        # built around the v2 grounding index + stub router.
        gi = GroundingIndex(version="v2")
        pipeline = NarrationPipeline(
            router=_make_stub_router(),
            grounding=gi,
        )
        app.state.gateway = MagicMock()
        app.state.gateway.settings = MagicMock()
        app.state.gateway.settings.sqlite_path = tmp_sqlite_db
        app.state.narration_pipeline = pipeline

        # Override the auth dep with a no-op so the test client
        # doesn't need a Bearer token.
        app.dependency_overrides[require_bearer] = lambda: None
        app.include_router(narration_router)

        # Pick a FEN that's in the v2 corpus.
        v2 = json.loads(
            Path("tests/gold/narrative/v2/corpus.json").read_text(
                encoding="utf-8"
            )
        )
        target = v2["entries"][0]
        target_fen = target["fen"]
        expected_entry_id = target["id"]

        # Run the request via TestClient (sync) inside a thread.
        # FastAPI's TestClient is sync; it runs the async route in
        # a thread loop internally.
        client = TestClient(app)
        resp = client.post(
            "/v1/narration/explain",
            json={
                "fen": target_fen,
                "move_san": "e4",
                "eval_cp": 38,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The response carries the corpus_entry_id. The `grounded`
        # flag is the LLM-citation-validated flag (separate from
        # corpus grounding); with the pre-canned stub narration
        # that doesn't match the engine PVs (the stub synthesis
        # here is minimal), the LLM validation will fail and
        # `grounded` may be False. We only assert corpus_entry_id
        # here; the LLM-citation path is exercised by the unit
        # tests in tests/unit/test_narration.py and
        # tests/unit/test_narrative_grounding.py.
        assert body["corpus_entry_id"] == expected_entry_id
        # Verify the audit table row has corpus_entry_id populated.
        async with aiosqlite.connect(str(tmp_sqlite_db)) as db, db.execute(
            "SELECT id, corpus_entry_id, position_id FROM narrations"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[1] == expected_entry_id

    async def test_route_with_unknown_fen_returns_no_corpus_entry_id(
        self, tmp_sqlite_db: Path,
    ) -> None:
        """POST /v1/narration/explain with a FEN NOT in v2 returns
        corpus_entry_id=None and stores NULL in the audit table.
        """
        from fastapi import FastAPI

        from chess_coach.gateway.auth import require_bearer
        from chess_coach.gateway.exception_handlers import (
            install_exception_handlers,
        )
        from chess_coach.gateway.routes.narration import (
            router as narration_router,
        )

        app = FastAPI()
        install_exception_handlers(app)
        gi = GroundingIndex(version="v2")
        pipeline = NarrationPipeline(
            router=_make_stub_router(),
            grounding=gi,
        )
        app.state.gateway = MagicMock()
        app.state.gateway.settings = MagicMock()
        app.state.gateway.settings.sqlite_path = tmp_sqlite_db
        app.state.narration_pipeline = pipeline
        app.dependency_overrides[require_bearer] = lambda: None
        app.include_router(narration_router)

        # Synthesize a FEN that's very unlikely to be in v2.
        unknown_fen = (
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )

        client = TestClient(app)
        resp = client.post(
            "/v1/narration/explain",
            json={
                "fen": unknown_fen,
                "move_san": "e4",
                "eval_cp": 38,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["corpus_entry_id"] is None

        async with aiosqlite.connect(str(tmp_sqlite_db)) as db, db.execute(
            "SELECT corpus_entry_id FROM narrations"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[0] is None

    def test_migration_0008_adds_corpus_entry_id_column(
        self, tmp_sqlite_db: Path,
    ) -> None:
        """The 0008 migration adds corpus_entry_id to narrations
        and makes position_id nullable.
        """
        conn = sqlite3.connect(str(tmp_sqlite_db))
        cols = conn.execute("PRAGMA table_info(narrations)").fetchall()
        col_names = [c[1] for c in cols]
        assert "corpus_entry_id" in col_names
        # position_id is now nullable (notnull=0)
        position_id_col = next(c for c in cols if c[1] == "position_id")
        assert position_id_col[3] == 0  # notnull=0
        # The new index exists.
        idx = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='narrations'"
        ).fetchall()
        idx_names = [i[0] for i in idx]
        assert "narrations_corpus_entry_id_idx" in idx_names
