"""Integration tests for BBF-FU-11c — α route opt-in to stored per-player book.

Routes under test:
  - POST /v1/repertoire/{player}/recommendations  (the α route)

Per BBF-FU-11c's behavior matrix:

  ┌──────────────────────────────────┬─────────────────────────────────────┬─────────────────────────────────────┐
  │ caller supplies polyglot_book_path? │ stored book exists for player?    │ route uses                          │
  ├──────────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────┤
  │ Yes                              │ (doesn't matter)                      │ caller's path (FU-7 behavior)       │
  │ No                               │ Yes                                  │ stored book's path                  │
  │ No                               │ No                                   │ engine-only (BBF-87.2 path)         │
  └──────────────────────────────────┴─────────────────────────────────────┴─────────────────────────────────────┘

Coverage:

  1. test_alpha_uses_stored_book_when_caller_omits_path
     — Write a book for player "ebassti" via the PUT route, call the α
     route without ``polyglot_book_path``, assert the response includes
     book-augmented items (source="book" or source="both").

  2. test_alpha_falls_back_to_engine_only_when_no_stored_book
     — Call the α route without ``polyglot_book_path`` for a player
     with no stored book, assert response is engine-only.

  3. test_alpha_caller_supplied_path_overrides_stored_book
     — Write a stored book for player "ebas_stored", call the α route
     with ``polyglot_book_path`` pointing at a *different* ``.bin`` in
     tmp_path, assert the response matches the different file
     (caller's path wins — back-compat regression test).

  4. test_alpha_default_player_resolves_to_ebassti_for_stored_book
     — Write a book at <data_dir>/books/ebassti.bin, call the α route
     with ``player="default"`` and no ``polyglot_book_path``, assert
     the stored book is used. Verifies the DEFAULT_PLAYER resolution
     at the α route.

  5. test_alpha_stored_book_absent_is_silent_no_warning_logged
     — Assert no WARNING-level log line is emitted when no book is
     stored (the §3.4 path emits DEBUG only).

The helper pattern follows ``test_repertoire_recommendations_polyglot.py``:
``_make_app_with_engine`` for the FastAPI app + mocked engine pool,
``_make_aiosqlite_patch`` for the fake gap rows, ``_active_token_lifecycle``
for the autouse auth fixture.
"""
from __future__ import annotations

# ruff: noqa: E501  -- the ASCII behavior-matrix table at the top of the module docstring is intentionally wider than the 100-char limit; it documents the FU-11c behavior matrix verbatim from the brief's §2. The E501 violations inside the table are deliberate, not drift.
import logging
from typing import Any
from unittest.mock import MagicMock

import chess
import pytest

AUTH = {"Authorization": "Bearer devtoken123"}
AUTH_WRITE = {"Authorization": "Bearer devtoken123:BOOKS_WRITE"}
STARTING_FEN = chess.STARTING_FEN
E2E4 = "e2e4"
D2E4 = "d2d4"


# The "_make_app_with_engine" + "_make_aiosqlite_patch" helpers from the
# α integration test are reused via fixture composition. Re-importing them
# here is cleaner than re-implementing, but to avoid coupling between two
# integration test files we duplicate the minimal slice needed.
#
# Both helpers construct a FastAPI app with ``app.state.gateway.settings``
# pointing at an isolated temp data_dir. The book's PUT route
# (``repertoire_book.py``) writes to <data_dir>/books/<player>.bin via
# ``_book_path``; the α route reads from the same location via ``_books_dir_path``.


def _make_polyglot_bin(path: str, entries: list[tuple[str, str, int, int]]) -> None:
    """Hand-roll a minimal valid Polyglot .bin file (per the FU-7 test pattern)."""
    import struct

    import chess.polyglot as pg

    def _key_for(fen: str) -> int:
        return pg.zobrist_hash(chess.Board(fen))

    sorted_entries = sorted(entries, key=lambda e: _key_for(e[0]))
    with open(path, "wb") as f:
        for fen, uci, weight, learn in sorted_entries:
            key = _key_for(fen)
            move = chess.Move.from_uci(uci)
            raw = (move.from_square << 6) | move.to_square
            if move.promotion:
                raw |= (move.promotion << 14)
            f.write(struct.pack(">QHHI", key, raw, weight, learn))


def _mock_engine_pool_with_pv(top_uci: str = E2E4, top_score_cp: int = 50) -> MagicMock:
    """A MagicMock engine_pool whose analyze() returns a deterministic PV.

    Mirrors ``test_repertoire_recommendations_polyglot.py:_mock_engine_pool_with_pv``.
    The default top-1 is E2E4; the book fixtures use D2E4 (disjoint from the engine)
    so the union produces 1 "engine" item + 1 "book" item with no overlap.
    """
    from unittest.mock import AsyncMock, MagicMock

    pv = MagicMock()
    pv.moves = [top_uci]
    pv.score = MagicMock()
    pv.score.kind = "cp"
    pv.score.value = top_score_cp
    pv.depth = 10

    result = MagicMock()
    result.pvs = [pv]

    pool = MagicMock()
    pool.analyze = AsyncMock(return_value=result)
    return pool


def _make_app_with_engine(engine_top: str = E2E4, engine_score_cp: int = 50):
    """Construct a FastAPI() with the α route mounted and a mocked engine pool.

    Returns (app, engine_pool, db_path, tmp_data_dir). ``db_path`` resolves
    via ``settings.sqlite_path`` from the isolated temp data_dir. ``tmp_data_dir``
    is returned for the test to clean up explicitly via teardown.
    """
    import tempfile as _tf

    from fastapi import FastAPI

    from chess_coach.gateway.config import GatewaySettings
    from chess_coach.gateway.exception_handlers import install_exception_handlers
    from chess_coach.gateway.routes.repertoire_book import router as book_router
    from chess_coach.gateway.routes.repertoire_recommendations import router

    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(router)
    app.include_router(book_router)
    tmp_data_dir = _tf.mkdtemp(prefix="chess_coach_fu11c_test_")
    settings = GatewaySettings(data_dir=tmp_data_dir)
    db_path = str(settings.sqlite_path)
    app.state.gateway = MagicMock()
    app.state.gateway.settings = settings
    engine_pool = _mock_engine_pool_with_pv(engine_top, engine_score_cp)
    app.state.engine_pool = engine_pool
    return app, engine_pool, db_path, tmp_data_dir


def _make_aiosqlite_patch(monkeypatch, fake_rows: list[dict[str, Any]]):
    """Patch aiosqlite.connect so the route sees our fake gap rows.

    Mirrors the FU-7 test's pattern exactly (the helper that ships with
    ``test_repertoire_recommendations_polyglot.py``). The route uses
    ``async with aiosqlite.connect(db_path) as db:`` and then
    ``db.execute_fetchall(...)``. We patch ``aiosqlite.connect`` to
    return our ``_FakeDb`` whose ``execute_fetchall`` returns the
    caller-supplied fake_rows as ``_FakeRow`` wrappers (so ``row["colname"]``
    indexing works).
    """

    class _FakeRow:
        def __init__(self, d):
            self._d = d

        def __getitem__(self, k):
            return self._d[k]

    async def _fake_execute_fetchall(sql, params=None):
        return [_FakeRow(r) for r in fake_rows]

    class _FakeDb:
        def __init__(self, *a, **kw):
            self.row_factory = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def execute_fetchall(self, sql, params=None):
            return _fake_execute_fetchall(sql, params)

    def _connect(*a, **kw):
        return _FakeDb()

    import aiosqlite

    monkeypatch.setattr(aiosqlite, "connect", _connect)


def _issue(app, method: str, path: str, **kw) -> Any:
    """Issue a request through an ASGI transport; return the response.

    If ``headers`` is not explicitly passed, an empty dict is used and
    the request will fail auth (return 401). Tests that need auth must
    pass ``headers=...`` explicitly (typically ``AUTH_WRITE`` or
    ``AUTH_READONLY`` from ``test_repertoire_book.py``'s pattern).
    """
    from starlette.testclient import TestClient

    if "headers" not in kw:
        kw["headers"] = {}
    return TestClient(app).request(method, path, **kw)


@pytest.fixture(autouse=True)
def _active_token_lifecycle():
    from chess_coach.gateway.auth import set_active_token

    set_active_token("devtoken123")
    yield
    set_active_token(None)


# -----------------------------------------------------------------------
# 1. α uses stored book when caller omits path
# -----------------------------------------------------------------------


def test_alpha_uses_stored_book_when_caller_omits_path(tmp_path, monkeypatch) -> None:
    """Write a book for "ebassti", call α without polyglot_book_path,
    assert the response includes book-augmented items."""
    import shutil

    app, _, _, tmp_path = _make_app_with_engine()
    _make_aiosqlite_patch(
        monkeypatch,
        [{"fen": STARTING_FEN, "ply": 0, "cnt": 1}],
    )

    # Write a stored book for player "ebassti" via the PUT route.
    # The PUT route uses BOOKS_WRITE scope (require_bearer_with_scope).
    # Per the BBF-FU-11b auth hotfix: the ACTIVE token must have the
    # BOOKS_WRITE scope; the request header must also carry the
    # write-scope token (the hotfix parses the LAST colon in both).
    from chess_coach.gateway.auth import set_active_token

    set_active_token("devtoken123:BOOKS_WRITE")
    put_resp = _issue(
        app,
        "PUT",
        "/v1/repertoire/ebassti/book",
        json=[{"fen": STARTING_FEN, "uci_move": D2E4, "weight": 5, "learn": 0}],
        headers=AUTH_WRITE,
    )
    assert put_resp.status_code == 200, put_resp.text
    set_active_token("devtoken123")

    # Call the α route without polyglot_book_path. AUTH is read-only
    # bearer (any scope or no scope works for the α route's
    # require_bearer dep). POST is the documented verb for the α route.
    alpha_resp = _issue(
        app,
        "POST",
        "/v1/repertoire/ebassti/recommendations?color=white&limit=5",
        headers=AUTH,
    )
    assert alpha_resp.status_code == 200, alpha_resp.text
    items = alpha_resp.json()["recommendations"]
    sources = {it["source"] for it in items}
    # The stored book has d2d4 on startpos, engine mock returns e2e4.
    # The route should surface both via the stored-book path.
    assert "book" in sources or "both" in sources, f"expected book/both in {sources}"
    # At least one item is source="book" (d2d4 entry, disjoint from engine).
    book_items = [it for it in items if it["source"] == "book"]
    assert book_items, f"expected at least one source=book item, got {items}"

    shutil.rmtree(tmp_path, ignore_errors=True)


# -----------------------------------------------------------------------
# 2. α falls back to engine-only when no stored book
# -----------------------------------------------------------------------


def test_alpha_falls_back_to_engine_only_when_no_stored_book(tmp_path, monkeypatch) -> None:
    """Call α without polyglot_book_path for a player with no stored book,
    assert the response is engine-only (no book items)."""
    import shutil

    app, _, _, tmp_path = _make_app_with_engine()
    _make_aiosqlite_patch(
        monkeypatch,
        [{"fen": STARTING_FEN, "ply": 0, "cnt": 1}],
    )

    # No book stored for player "no_book_player" (the default engine
    # mock returns e2e4 as top-1, but no book is read).
    alpha_resp = _issue(
        app,
        "POST",
        "/v1/repertoire/no_book_player/recommendations?color=white&limit=5",
        headers=AUTH,
    )
    assert alpha_resp.status_code == 200, alpha_resp.text
    items = alpha_resp.json()["recommendations"]
    # Engine-only: every item has source="engine", book_weight=None.
    for it in items:
        assert it["source"] == "engine", f"expected engine-only, got {it}"
        assert it["book_weight"] is None

    shutil.rmtree(tmp_path, ignore_errors=True)


# -----------------------------------------------------------------------
# 3. Caller-supplied path overrides stored book (back-compat regression)
# -----------------------------------------------------------------------


def test_alpha_caller_supplied_path_overrides_stored_book(tmp_path, monkeypatch) -> None:
    """Write a stored book, then call α with a different polyglot_book_path
    in tmp_path; assert the response matches the caller's path, not the
    stored one."""
    import shutil

    app, _, _, tmp_data_dir = _make_app_with_engine()
    _make_aiosqlite_patch(
        monkeypatch,
        [{"fen": STARTING_FEN, "ply": 0, "cnt": 1}],
    )

    # Write a stored book for player "ebas_stored" containing d2d4.
    from chess_coach.gateway.auth import set_active_token

    set_active_token("devtoken123:BOOKS_WRITE")
    put_resp = _issue(
        app,
        "PUT",
        "/v1/repertoire/ebas_stored/book",
        json=[{"fen": STARTING_FEN, "uci_move": D2E4, "weight": 5, "learn": 0}],
        headers=AUTH_WRITE,
    )
    assert put_resp.status_code == 200, put_resp.text
    set_active_token("devtoken123")

    # Write a *different* book at <tmp_path>/caller_book.bin containing
    # only d2d4 with a different score (5 → 99). The α route should use
    # THIS file because the caller supplied it.
    caller_book = tmp_path / "caller_book.bin"
    _make_polyglot_bin(str(caller_book), [(STARTING_FEN, D2E4, 99, 0)])

    alpha_resp = _issue(
        app,
        "POST",
        f"/v1/repertoire/ebas_stored/recommendations?color=white&limit=5&polyglot_book_path={caller_book}",
        headers=AUTH,
    )
    assert alpha_resp.status_code == 200, alpha_resp.text
    items = alpha_resp.json()["recommendations"]
    # The caller's path wins — the stored book at <data_dir>/books/ebas_stored.bin
    # is NOT used. The book entry from the caller's path (d2d4, w=99) should
    # appear as source="book" (engine top-1 is e2e4, disjoint).
    book_items = [it for it in items if it["source"] == "book"]
    assert book_items, f"expected at least one source=book item, got {items}"
    # The book_weight should be 99 (from the caller's path), not 5
    # (from the stored book). This proves the caller's path won.
    assert any(it["book_weight"] == 99 for it in book_items), (
        f"expected book_weight=99 from caller's path, got {[it['book_weight'] for it in book_items]}"
    )

    shutil.rmtree(tmp_data_dir, ignore_errors=True)
    shutil.rmtree(tmp_path, ignore_errors=True)


# -----------------------------------------------------------------------
# 4. default player resolves to "ebassti" for stored book lookup
# -----------------------------------------------------------------------


def test_alpha_default_player_resolves_to_ebassti_for_stored_book(tmp_path, monkeypatch) -> None:
    """Write a book at <data_dir>/books/ebassti.bin, call α with player="default",
    assert the stored book is used (DEFAULT_PLAYER resolution)."""
    import shutil

    app, _, _, tmp_data_dir = _make_app_with_engine()
    _make_aiosqlite_patch(
        monkeypatch,
        [{"fen": STARTING_FEN, "ply": 0, "cnt": 1}],
    )

    from chess_coach.gateway.auth import set_active_token

    set_active_token("devtoken123:BOOKS_WRITE")
    put_resp = _issue(
        app,
        "PUT",
        "/v1/repertoire/ebassti/book",
        json=[{"fen": STARTING_FEN, "uci_move": D2E4, "weight": 5, "learn": 0}],
        headers=AUTH_WRITE,
    )
    assert put_resp.status_code == 200, put_resp.text
    set_active_token("devtoken123")

    # Call α with player="default" and no polyglot_book_path.
    # The DEFAULT_PLAYER resolution at repertoire_recommendations.py:251
    # should map "default" -> "ebassti", and the stored book should be used.
    alpha_resp = _issue(
        app,
        "POST",
        "/v1/repertoire/default/recommendations?color=white&limit=5",
        headers=AUTH,
    )
    assert alpha_resp.status_code == 200, alpha_resp.text
    items = alpha_resp.json()["recommendations"]
    book_items = [it for it in items if it["source"] == "book"]
    assert book_items, f"expected at least one source=book item from stored book at default, got {items}"

    shutil.rmtree(tmp_data_dir, ignore_errors=True)


# -----------------------------------------------------------------------
# 5. No WARNING log when no book is stored (silent DEBUG)
# -----------------------------------------------------------------------


def test_alpha_stored_book_absent_is_silent_no_warning_logged(tmp_path, monkeypatch, caplog) -> None:
    """Call α without polyglot_book_path for a player with no stored book,
    assert no WARNING-level log line is emitted (the §3.4 path emits DEBUG only)."""
    import shutil

    app, _, _, tmp_data_dir = _make_app_with_engine()
    _make_aiosqlite_patch(
        monkeypatch,
        [{"fen": STARTING_FEN, "ply": 0, "cnt": 1}],
    )

    caplog.set_level(logging.DEBUG)
    # The α route uses logger named after the module.
    caplog.set_level(logging.WARNING, logger="chess_coach.gateway.routes.repertoire_recommendations")

    alpha_resp = _issue(
        app,
        "POST",
        "/v1/repertoire/no_book_player/recommendations?color=white&limit=5",
        headers=AUTH,
    )
    assert alpha_resp.status_code == 200, alpha_resp.text

    # No WARNING-level lines from the α route should be present. The
    # §3.4 "no stored book" branch emits DEBUG ("recommendations: no
    # stored book..."), which is fine. WARNING would indicate a real
    # problem (e.g., the route failed to read the books_dir).
    warning_lines = [
        rec for rec in caplog.records
        if rec.levelno >= logging.WARNING
        and rec.name == "chess_coach.gateway.routes.repertoire_recommendations"
    ]
    assert not warning_lines, (
        f"unexpected WARNING-level logs from α route: "
        f"{[(r.levelname, r.getMessage()) for r in warning_lines]}"
    )

    shutil.rmtree(tmp_data_dir, ignore_errors=True)
