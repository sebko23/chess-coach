"""Integration tests for BBF-FU-11b: the per-player book routes.

Routes under test (per the BBF-FU-11 decision brief §3.2):

  - PUT    /v1/repertoire/{player}/book   (write, requires BOOKS_WRITE)
  - GET    /v1/repertoire/{player}/book   (metadata, read-only)
  - DELETE /v1/repertoire/{player}/book   (remove, requires BOOKS_WRITE)

Coverage (8 tests, all directly traceable to the brief's §3.2 test list):

  1. PUT then GET then DELETE — full lifecycle round-trip.
  2. PUT overwrites — second PUT replaces the first.
  3. GET on no-book — returns 404 with client.not_found.
  4. DELETE on no-book — returns 200 with ``{"deleted": false, ...}``.
  5. Write-scope required — a read-only token is rejected with 401
     on PUT/DELETE; a write-scope token is accepted.
  6. Player-name normalization — ``/v1/repertoire/default/book`` and
     ``/v1/repertoire/ebassti/book`` resolve to the same file.
  7. Illegal move rejected — PUT body with FEN+UCI mismatch returns
     400 with client.bad_request.
  8. Large book round-trip — 10k entries written, read back, all
     decode correctly.

Test infrastructure mirrors the α integration test at
``test_repertoire_recommendations_polyglot.py`` (hand-rolled
``_make_app_with_engine`` helper, autouse auth fixture, no real
Stockfish on PATH). The book routes don't need an engine pool, so
the helper is simpler: just the FastAPI app with a fresh
``data_dir`` and the central exception handlers installed.

Auth fixture design note
-------------------------

The PUT and DELETE endpoints require the BOOKS_WRITE scope. The GET
endpoint requires only bearer auth (any scope or no scope). To
exercise both paths in one test class, each test sets the active
token explicitly before issuing its requests, and the autouse
``_active_token_lifecycle`` fixture only ensures cleanup. This is
slightly more verbose than a single global fixture, but it makes
each test's auth requirement explicit at the call site.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from chess_coach.gateway.auth import set_active_token
from chess_coach.gateway.config import GatewaySettings
from chess_coach.gateway.exception_handlers import install_exception_handlers
from chess_coach.gateway.routes.repertoire_book import router as book_router

# Convenience constants: a write-scope token and a read-only token.
# The active token in set_active_token() must match the request's
# Bearer value (after the LAST-colon split) for the dep to accept.
WRITE_TOKEN = "devtoken123:BOOKS_WRITE"
READONLY_TOKEN = "devtoken123"
AUTH_WRITE = {"Authorization": f"Bearer {WRITE_TOKEN}"}
AUTH_READONLY = {"Authorization": f"Bearer {READONLY_TOKEN}"}

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture
def _tmp_data_dir() -> Any:
    """Fresh ``data_dir`` for the duration of one test.

    Mirrors the α integration test's per-test isolation: a fresh
    ``GatewaySettings.data_dir`` is set, the books directory is
    auto-created on the first PUT, and the temp dir is removed at
    teardown.
    """
    tmp = tempfile.mkdtemp(prefix="chess_coach_fu11b_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(autouse=True)
def _active_token_lifecycle() -> Any:
    """Default active token is the WRITE token. Tests that need the
    read-only token explicitly call :func:`set_active_token` to swap.

    Most tests issue at least one PUT or DELETE, which require the
    BOOKS_WRITE scope; defaulting to the write-scope token keeps
    those tests simple. The "read-only token rejected" test (5) is
    the only one that swaps to the read-only token.
    """
    set_active_token(WRITE_TOKEN)
    yield
    set_active_token(None)


def _make_app_with_books_dir(books_dir: str) -> FastAPI:
    """Construct a FastAPI() with the book router mounted and a stub settings.

    Returns (app, settings) so tests can introspect the data_dir.
    No engine pool is needed for the book routes (the writer
    doesn't depend on Stockfish).
    """
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(book_router)
    settings = GatewaySettings(data_dir=books_dir)
    app.state.gateway = type("StubGateway", (), {"settings": settings})()
    return app, settings


def _hit(app: FastAPI, method: str, path: str, **kw) -> Any:
    """Issue a request through an ASGI transport; return the response."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# -----------------------------------------------------------------------
# 1. PUT then GET then DELETE — full lifecycle round-trip
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_get_delete_lifecycle(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """Write a 3-entry book, read metadata back, delete it."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        # 1. PUT — write a 3-entry book
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[
                {"fen": STARTING_FEN, "uci_move": "e2e4", "weight": 100},
                {"fen": STARTING_FEN, "uci_move": "d2d4", "weight": 50},
                {"fen": STARTING_FEN, "uci_move": "g1f3", "weight": 75},
            ],
            headers=AUTH_WRITE,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player"] == "ebassti"
        assert body["entry_count"] == 3
        assert body["size_bytes"] == 48  # 3 entries * 16 bytes

        # 2. GET — read metadata back
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player"] == "ebassti"
        assert body["entry_count"] == 3
        assert body["size_bytes"] == 48
        assert "last_modified" in body
        # last_modified is ISO-8601 UTC
        from datetime import datetime
        datetime.fromisoformat(body["last_modified"])  # raises if malformed

        # 3. DELETE — remove the book
        r = await ac.delete(
            "/v1/repertoire/ebassti/book", headers=AUTH_WRITE
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player"] == "ebassti"
        assert body["deleted"] is True

        # 4. GET on now-empty — 404
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 404, r.text
        assert "client.not_found" in r.text


# -----------------------------------------------------------------------
# 2. PUT overwrites — second PUT replaces the first
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_overwrites(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """A second PUT replaces the first; entry_count reflects the latest write."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        # First PUT: 5 entries
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}] * 5,
            headers=AUTH_WRITE,
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 5

        # Second PUT: 1 entry
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[{"fen": STARTING_FEN, "uci_move": "d2d4"}],
            headers=AUTH_WRITE,
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 1

        # GET: should reflect the second PUT
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 1
        assert r.json()["size_bytes"] == 16


# -----------------------------------------------------------------------
# 3. GET on no-book — 404 with client.not_found
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_on_no_book_returns_404(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """GET on a player that has no stored book returns 404."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "GET", "/v1/repertoire/ebassti/book") as ac:
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 404, r.text
        body = r.json()
        # The exception handler wraps the HTTPException's dict detail
        # in the protocol's error envelope: body["error"]["code"].
        assert body["error"]["code"] == "client.not_found"
        # The dict detail is stringified into the message; the player
        # name is in the message text.
        assert "ebassti" in body["error"]["message"]


# -----------------------------------------------------------------------
# 4. DELETE on no-book — idempotent
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_on_no_book_is_idempotent(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """DELETE on a no-book player returns 200 with ``{"deleted": false}``."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "DELETE", "/v1/repertoire/ebassti/book") as ac:
        r = await ac.delete(
            "/v1/repertoire/ebassti/book", headers=AUTH_WRITE
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player"] == "ebassti"
        assert body["deleted"] is False
        assert body["reason"] == "no book stored"


# -----------------------------------------------------------------------
# 5. Write-scope required — read-only token rejected on PUT/DELETE
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readonly_token_rejected_on_write_endpoints(_tmp_data_dir) -> None:  # noqa: PT019
    """A read-only token (no scope) cannot PUT or DELETE; only GET works."""
    set_active_token(READONLY_TOKEN)
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        # PUT with read-only token -> 401
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_READONLY,
        )
        assert r.status_code == 401, r.text
        assert "BOOKS_WRITE" in r.text or "scope" in r.text.lower()

        # DELETE with read-only token -> 401
        r = await ac.delete(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 401, r.text

        # GET with read-only token -> 404 (auth passes, no book to find)
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 404, r.text

    # Now write a book with a write-scope token and re-test the read paths
    set_active_token(WRITE_TOKEN)
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
        assert r.status_code == 200

    # Restore the read-only token for cleanup
    set_active_token(READONLY_TOKEN)
    async with _hit(app, "GET", "/v1/repertoire/ebassti/book") as ac:
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 1


# -----------------------------------------------------------------------
# 6. Player-name normalization — "default" -> "ebassti"
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_player_normalizes_to_ebassti(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """``/v1/repertoire/default/book`` and ``/v1/repertoire/ebassti/book``
    write to the same file (the α route's default-alias convention)."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/default/book") as ac:
        # PUT via "default"
        r = await ac.put(
            "/v1/repertoire/default/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
        assert r.status_code == 200, r.text
        assert r.json()["player"] == "ebassti"  # normalized in response

        # GET via "ebassti" — finds the file
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 200, r.text
        assert r.json()["entry_count"] == 1

        # PUT via "ebassti" — overwrites
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[
                {"fen": STARTING_FEN, "uci_move": "e2e4"},
                {"fen": STARTING_FEN, "uci_move": "d2d4"},
            ],
            headers=AUTH_WRITE,
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 2

        # GET via "default" — sees the overwrite
        r = await ac.get(
            "/v1/repertoire/default/book", headers=AUTH_READONLY
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 2


@pytest.mark.asyncio
async def test_invalid_player_name_rejected(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """Player names with ``.`` / ``/`` / ``\\`` are rejected with 400
    to prevent path traversal. ``ebassti`` is also valid."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/../etc/passwd/book") as ac:
        # httpx normalizes "..%2F" but rejects literal ".." segments
        # in the URL. We test with a name that's syntactically OK in
        # the URL but fails the regex: "foo.bar" contains a ".".
        r = await ac.put(
            "/v1/repertoire/foo.bar/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
        assert r.status_code == 400, r.text
        assert "client.bad_request" in r.text


# -----------------------------------------------------------------------
# 7. Illegal move rejected — writer's ValueError becomes 400
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_illegal_move_returns_400(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """A FEN+UCI pair where the UCI is not legal from the FEN returns 400."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        # e2e4 is NOT legal from the "after e4" position (the e2 pawn
        # has already moved; only e4 is on e4).
        AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[{"fen": AFTER_E4_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
        assert r.status_code == 400, r.text
        assert "client.bad_request" in r.text
        assert "legal" in r.text.lower()


@pytest.mark.asyncio
async def test_weight_out_of_range_returns_400(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """A weight > 65535 is rejected at the Pydantic validation layer
    (the BookEntryIn model has ``le=0xFFFF``) AND at the writer layer.
    Either way the response is 400."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        # weight=100000 exceeds 0xFFFF; Pydantic returns 422.
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4", "weight": 100000}],
            headers=AUTH_WRITE,
        )
        # FastAPI's default 422 for Pydantic validation errors is the
        # right shape; we don't downgrade to 400 because the writer
        # would have rejected this too, but the error surfaced one
        # layer earlier.
        assert r.status_code in (400, 422), r.text


# -----------------------------------------------------------------------
# 8. Large book round-trip — 10k entries written, read back
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_large_book_round_trip(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """A 10k-entry book writes, reads back, and entry_count is exact."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    # 10k entries of the same FEN+UCI is a stress test for the
    # writer's sort loop, the writer's binary output, and the
    # file_size/16 entry_count math on the GET path. All four
    # paths handle 10k entries in <1s on a normal machine.
    entries = [{"fen": STARTING_FEN, "uci_move": "e2e4", "weight": 100}] * 10000
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        t0 = time.monotonic()
        r = await ac.put(
            "/v1/repertoire/ebassti/book",
            json=entries,
            headers=AUTH_WRITE,
        )
        elapsed = time.monotonic() - t0
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entry_count"] == 10000
        assert body["size_bytes"] == 16 * 10000
        assert elapsed < 5.0, f"PUT took {elapsed:.2f}s, expected <5s"

        # Read back
        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 10000
        assert r.json()["size_bytes"] == 16 * 10000

        # And the writer's own round-trip property holds: open the
        # .bin via python-chess and find_all() returns all 10k
        # entries (the writer does NOT dedupe by zobrist key; it
        # writes every BookEntry the caller supplies, then sorts by
        # key for the bisect to work). The find_all() yields each
        # entry whose key matches, in file order; we get all 10000
        # back because the writer does not dedupe.
        path = f"{_tmp_data_dir}/books/ebassti.bin"
        import chess.polyglot
        with chess.polyglot.open_reader(path) as reader:
            hits = list(reader.find_all(chess.Board(STARTING_FEN)))
        assert len(hits) == 10000  # no dedup; the writer writes all entries
        # Every hit has the same key (same FEN) and same UCI
        for h in hits:
            assert h.move.uci() == "e2e4"
            assert h.weight == 100


# -----------------------------------------------------------------------
# 9. Empty book (zero entries) is a valid PUT
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_book_is_valid(_tmp_data_dir, _active_token_lifecycle) -> None:  # noqa: PT019
    """A PUT with an empty list writes a 0-byte file; subsequent
    finds return nothing. Mirrors the writer's existing test for
    empty books at the route layer."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", "/v1/repertoire/ebassti/book") as ac:
        r = await ac.put(
            "/v1/repertoire/ebassti/book", json=[], headers=AUTH_WRITE
        )
        assert r.status_code == 200, r.text
        assert r.json()["entry_count"] == 0
        assert r.json()["size_bytes"] == 0

        r = await ac.get(
            "/v1/repertoire/ebassti/book", headers=AUTH_READONLY
        )
        assert r.status_code == 200
        assert r.json()["entry_count"] == 0
        assert r.json()["size_bytes"] == 0
