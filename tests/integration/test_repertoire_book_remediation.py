"""Integration + unit proof for the FU-11 remediation (2026-11-04).

Covers the blockers that the BBF-FU-11b/c implementation did not
prove:

  1. The write-scope request semantics at the HTTP boundary (the
     request's own credential must carry ``BOOKS_WRITE``).
  2. The deterministic HTTP 400 for request-boundary validation.
  3. Atomic replacement — an injected failure preserves the previous
     valid book and leaves no temporary artifact.
  4. Canonical containment and symlink safety across PUT, GET,
     DELETE and the recommendations fallback.
  5. Malformed stored-file metadata — never reported as an empty book.
  6. Real application-factory route registration.
  7. An INDEPENDENT public-format Polyglot parser, so interoperability
     is not proven by a ``python-chess`` self-round-trip.

The independent parser in section 7 is deliberately written against the
public format description (https://hgm.nubati.net/book_format.html) and
NOT against the writer's own code: it re-implements the byte layout
from the spec text, so a project-written file is proven consumable by
a standard Polyglot reader.
"""
from __future__ import annotations

import os
import shutil
import struct
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from chess_coach.gateway.auth import set_active_token
from chess_coach.gateway.config import GatewaySettings
from chess_coach.gateway.exception_handlers import install_exception_handlers
from chess_coach.gateway.routes.repertoire_book import router as book_router
from chess_coach.repertoire.book_storage import (
    MalformedBookBytesError,
    atomic_replace_bytes,
    entry_count_from_size,
    resolve_book_path,
)

WRITE_TOKEN = "devtoken123:BOOKS_WRITE"
READONLY_TOKEN = "devtoken123"
AUTH_WRITE = {"Authorization": f"Bearer {WRITE_TOKEN}"}
AUTH_READONLY = {"Authorization": f"Bearer {READONLY_TOKEN}"}
# The unscoped request against a SCOPED configured credential — the
# case the remediation must reject.
AUTH_UNSCOPED_REQUEST = {"Authorization": f"Bearer {READONLY_TOKEN}"}

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
BOOK_URL = "/v1/repertoire/ebassti/book"


# ----------------------------------------------------------------------
# An INDEPENDENT public-format Polyglot parser
# ----------------------------------------------------------------------
#
# Written from the public spec, not from the writer's code:
#   "A Polyglot book is a series of 'entries' of 16 bytes
#      key    uint64
#      move   uint16
#      weight uint16
#      learn  uint32
#    All integers are stored highest byte first (regardless of size)
#    The entries are ordered according to key. Lowest key first."
# (https://hgm.nubati.net/book_format.html)
#
# The move field is the public Polyglot encoding: the 16-bit value is
# (from_square << 6) | to_square, with squares numbered 0..63 in
# raster-scan order (a1=0, h1=7, a2=8, ... h8=63).


def independent_parse_book(data: bytes) -> list[dict[str, int]]:
    """Decode a Polyglot book with an independent, spec-derived parser.

    Returns one dict per entry with ``key``, ``from_square``,
    ``to_square``, ``weight`` and ``learn``. Raises ``ValueError`` if
    the payload is not a whole number of 16-byte entries.
    """
    if len(data) % 16 != 0:
        raise ValueError(f"not a whole number of 16-byte entries: {len(data)}")
    entries: list[dict[str, int]] = []
    for offset in range(0, len(data), 16):
        key, move, weight, learn = struct.unpack(">QHHI", data[offset : offset + 16])
        entries.append(
            {
                "key": key,
                "from_square": (move >> 6) & 0x3F,
                "to_square": move & 0x3F,
                "weight": weight,
                "learn": learn,
            }
        )
    return entries


def _independent_find(data: bytes, key: int) -> list[dict[str, int]]:
    """Binary-search a book by key, exactly as a Polyglot reader does."""
    entries = independent_parse_book(data)
    lo, hi = 0, len(entries)
    while lo < hi:
        mid = (lo + hi) // 2
        if entries[mid]["key"] < key:
            lo = mid + 1
        else:
            hi = mid
    found = []
    for entry in entries[lo:]:
        if entry["key"] != key:
            break
        found.append(entry)
    return found


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def _tmp_data_dir() -> Any:
    tmp = tempfile.mkdtemp(prefix="chess_coach_fu11r_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(autouse=True)
def _active_token_lifecycle() -> Any:
    set_active_token(WRITE_TOKEN)
    yield
    set_active_token(None)


def _make_app_with_books_dir(data_dir: str) -> tuple[FastAPI, GatewaySettings]:
    """A FastAPI() with the book router mounted and a stub settings.

    This mirrors the pre-existing BBF-FU-11b fixture. Section 6 uses
    the REAL application factory instead.
    """
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(book_router)
    settings = GatewaySettings(data_dir=data_dir)
    app.state.gateway = type("StubGateway", (), {"settings": settings})()
    return app, settings


def _hit(app: FastAPI, method: str, url: str) -> Any:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _books_dir(settings: GatewaySettings) -> Path:
    return Path(settings.books_dir)


def _symlinks_supported() -> bool:
    """True when this host can create a symlink.

    Windows requires either Administrator or Developer Mode
    (CreateSymbolicLinkW fails with ERROR_PRIVILEGE_NOT_HELD,
    WinError 1314) unless the developer-mode flag is used, which
    ``os.symlink`` does not expose. The containment logic under test
    is platform-independent, so the symlink-specific assertions are
    skipped where the host cannot create one; the resolver's
    escape-rejection is proved separately by mocking the resolution
    step, which exercises the same branch.
    """
    with tempfile.TemporaryDirectory(prefix="fu11_symcap_") as probe:
        target = Path(probe) / "target.bin"
        target.write_bytes(b"x")
        try:
            (Path(probe) / "link.bin").symlink_to(target)
        except (OSError, NotImplementedError):
            return False
        return True


_SKIP_IF_NO_SYMLINK = pytest.mark.skipif(
    not _symlinks_supported(),
    reason="this host cannot create symlinks (Windows without Developer Mode)",
)


def _write_book_file(settings: GatewaySettings, player: str, payload: bytes) -> Path:
    """Place a raw payload at the player's stored-book path."""
    books = _books_dir(settings)
    books.mkdir(parents=True, exist_ok=True)
    path = books / f"{player}.bin"
    path.write_bytes(payload)
    return path


# ======================================================================
# 1. Authorization at the HTTP boundary
# ======================================================================


@pytest.mark.asyncio
async def test_unscoped_request_rejected_for_put(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """A scoped CONFIGURED credential plus an unscoped REQUEST is rejected.

    This is the core remediation case: before the fix, the request's
    scope was parsed and discarded, so ``Bearer secret`` was accepted
    for a write whenever the configured token was scoped.
    """
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            BOOK_URL,
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_UNSCOPED_REQUEST,
        )
    assert r.status_code == 401, r.text
    # The book must NOT have been written.
    books = Path(settings.books_dir)
    assert not books.exists() or not list(books.glob("*.bin"))


@pytest.mark.asyncio
async def test_unscoped_request_rejected_for_delete(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        await ac.put(
            BOOK_URL,
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
        r = await ac.delete(BOOK_URL, headers=AUTH_UNSCOPED_REQUEST)
    assert r.status_code == 401, r.text
    # The stored book must survive the rejected DELETE.
    assert (Path(settings.books_dir) / "ebassti.bin").exists()


@pytest.mark.asyncio
async def test_readonly_configured_credential_cannot_write(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """A plain configured secret can GET but cannot PUT or DELETE."""
    set_active_token(READONLY_TOKEN)
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r_put = await ac.put(
            BOOK_URL,
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_READONLY,
        )
        r_del = await ac.delete(BOOK_URL, headers=AUTH_READONLY)
    assert r_put.status_code == 401, r_put.text
    assert r_del.status_code == 401, r_del.text


@pytest.mark.asyncio
async def test_readonly_configured_credential_can_get(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """Read-only routes stay backward compatible: a plain configured
    secret authenticates, and a scoped one does too."""
    set_active_token(READONLY_TOKEN)
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    _write_book_file(settings, "ebassti", b"")
    async with _hit(app, "GET", BOOK_URL) as ac:
        r = await ac.get(BOOK_URL, headers=AUTH_READONLY)
    assert r.status_code == 200, r.text
    assert r.json()["entry_count"] == 0


@pytest.mark.asyncio
async def test_scoped_request_credential_can_write(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """``Bearer secret:BOOKS_WRITE`` succeeds when its secret matches
    the configured credential and its scope is exact."""
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            BOOK_URL,
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
    assert r.status_code == 200, r.text
    assert (Path(settings.books_dir) / "ebassti.bin").exists()


# ======================================================================
# 2. Deterministic 400 for request-boundary validation
# ======================================================================


@pytest.mark.asyncio
async def test_weight_out_of_range_returns_exactly_400(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """An out-of-range weight is HTTP 400 — not "400 or 422"."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            BOOK_URL,
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4", "weight": 100000}],
            headers=AUTH_WRITE,
        )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_learn_out_of_range_returns_exactly_400(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """An out-of-range learn value is HTTP 400 too."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            BOOK_URL,
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4", "learn": 2**32}],
            headers=AUTH_WRITE,
        )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_malformed_entry_data_returns_exactly_400(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """A malformed entry (missing the required uci_move) is HTTP 400."""
    app, _ = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            BOOK_URL,
            json=[{"fen": STARTING_FEN}],
            headers=AUTH_WRITE,
        )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_unrelated_route_validation_stays_422(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """The narrow 400 mapping must NOT change other routes' behaviour.

    A router-scoped ``RequestValidationError`` handler is installed on
    the book router only. This test proves the gateway's global 422
    behaviour is intact for a route outside that router.
    """
    from fastapi import FastAPI as _FastAPI

    # A tiny app with a NON-book route that validates its body.
    app = _FastAPI()
    install_exception_handlers(app)

    @app.put("/v1/other")
    async def _other(body: dict[str, int]) -> dict[str, int]:
        return body

    async with _hit(app, "PUT", "/v1/other") as ac:
        r = await ac.put("/v1/other", json={"count": "not-an-int"})
    assert r.status_code == 422, (
        f"the global validation status must stay 422, got {r.status_code}: {r.text}"
    )


# ======================================================================
# 3. Atomic replacement
# ======================================================================


def test_atomic_replace_preserves_old_bytes_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An injected write failure preserves the previous valid bytes."""
    # Use a dedicated subdirectory: the conftest's autouse
    # `_isolate_env` fixture points the gateway's data dir at pytest's
    # `tmp_path`, so that root also holds a `sqlite/` sibling.
    work = tmp_path / "books"
    work.mkdir()
    dest = work / "book.bin"
    dest.write_bytes(b"ORIGINAL-VALID-BOOK")

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise OSError("injected write failure")

    monkeypatch.setattr(os, "fdopen", _boom)
    with pytest.raises(OSError, match="injected write failure"):
        atomic_replace_bytes(dest, b"NEW-BYTES")
    assert dest.read_bytes() == b"ORIGINAL-VALID-BOOK"
    # No temporary artifact left behind in the destination's directory.
    assert sorted(p.name for p in dest.parent.iterdir()) == [dest.name]


def test_atomic_replace_preserves_old_bytes_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An injected REPLACEMENT failure preserves the previous bytes."""
    work = tmp_path / "books"
    work.mkdir()
    dest = work / "book.bin"
    dest.write_bytes(b"ORIGINAL-VALID-BOOK")

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise OSError("injected replacement failure")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="injected replacement failure"):
        atomic_replace_bytes(dest, b"NEW-BYTES")
    assert dest.read_bytes() == b"ORIGINAL-VALID-BOOK"
    # The temporary artifact is removed after the failure.
    assert sorted(p.name for p in dest.parent.iterdir()) == [dest.name]


def test_atomic_replace_succeeds_and_leaves_no_temp(
    tmp_path: Path,
) -> None:
    work = tmp_path / "books"
    work.mkdir()
    dest = work / "book.bin"
    dest.write_bytes(b"OLD")
    written = atomic_replace_bytes(dest, b"NEW")
    assert written == 3
    assert dest.read_bytes() == b"NEW"
    assert sorted(p.name for p in dest.parent.iterdir()) == [dest.name]


def test_writer_preserves_old_book_when_validation_fails(
    tmp_path: Path,
) -> None:
    """A validation error must not touch the previous book."""
    from chess_coach.repertoire.polyglot_writer import BookEntry, write_polyglot_book

    work = tmp_path / "books"
    work.mkdir()
    dest = work / "book.bin"
    dest.write_bytes(b"ORIGINAL-VALID-BOOK")
    bad = BookEntry(fen=STARTING_FEN, uci_move="e2e5")  # illegal from the start
    with pytest.raises(ValueError, match="not legal"):
        write_polyglot_book([bad], str(dest))
    assert dest.read_bytes() == b"ORIGINAL-VALID-BOOK"
    assert sorted(p.name for p in dest.parent.iterdir()) == [dest.name]


# ======================================================================
# 4. Canonical containment and symlink safety
# ======================================================================


def test_resolver_rejects_lexical_traversal(tmp_path: Path) -> None:
    books = tmp_path / "books"
    books.mkdir()
    for name in ("..", "../evil", "a/b", "a\\b", "", "x" * 65):
        with pytest.raises(ValueError, match="Invalid player name"):
            resolve_book_path(books, name)


def test_resolver_rejects_a_destination_that_resolves_outside_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The escape-rejection branch, proved WITHOUT a real symlink.

    ``resolve_book_path`` rejects a destination whose pre-existing
    symlink resolves outside the canonical books root. This test drives
    that exact branch by making the destination LOOK like a symlink
    and making its resolution land outside the root — which is what
    the real-symlink test does on a host that permits symlinks.

    This keeps the containment guarantee covered on every host, rather
    than silently skipping it wherever symlinks are unavailable.
    """
    books = tmp_path / "books"
    books.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"PRE-EXISTING")
    destination = books / "evil.bin"

    real_is_symlink = Path.is_symlink
    real_resolve = Path.resolve

    def _fake_is_symlink(self: Path) -> bool:
        if self == destination:
            return True
        return real_is_symlink(self)

    def _fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self == destination:
            return outside.resolve()
        return real_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "is_symlink", _fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", _fake_resolve)

    with pytest.raises(ValueError, match="escapes"):
        resolve_book_path(books, "evil")


@_SKIP_IF_NO_SYMLINK
def test_resolver_rejects_symlink_escape(tmp_path: Path) -> None:
    """A destination symlinked outside the books root is refused."""
    books = tmp_path / "books"
    books.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"PRE-EXISTING")
    (books / "evil.bin").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        resolve_book_path(books, "evil")


@pytest.mark.asyncio
@_SKIP_IF_NO_SYMLINK
async def test_symlink_escape_is_not_written(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """PUT must not follow a symlink out of the books directory."""
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    books = Path(settings.books_dir)
    books.mkdir(parents=True, exist_ok=True)
    outside = Path(_tmp_data_dir) / "outside.bin"
    outside.write_bytes(b"PRE-EXISTING")
    (books / "evil.bin").symlink_to(outside)

    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            "/v1/repertoire/evil/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
    assert 400 <= r.status_code < 500, r.text
    # The external file is untouched.
    assert outside.read_bytes() == b"PRE-EXISTING"


@pytest.mark.asyncio
@_SKIP_IF_NO_SYMLINK
async def test_symlink_escape_is_not_read(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """GET must not read a target outside the books root."""
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    books = Path(settings.books_dir)
    books.mkdir(parents=True, exist_ok=True)
    outside = Path(_tmp_data_dir) / "outside.bin"
    outside.write_bytes(b"PRE-EXISTING")
    (books / "evil.bin").symlink_to(outside)

    async with _hit(app, "GET", BOOK_URL) as ac:
        r = await ac.get("/v1/repertoire/evil/book", headers=AUTH_READONLY)
    assert 400 <= r.status_code < 500, r.text


@pytest.mark.asyncio
@_SKIP_IF_NO_SYMLINK
async def test_symlink_escape_is_not_deleted(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """DELETE must not unlink a target outside the books root."""
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    books = Path(settings.books_dir)
    books.mkdir(parents=True, exist_ok=True)
    outside = Path(_tmp_data_dir) / "outside.bin"
    outside.write_bytes(b"PRE-EXISTING")
    (books / "evil.bin").symlink_to(outside)

    async with _hit(app, "DELETE", BOOK_URL) as ac:
        r = await ac.delete("/v1/repertoire/evil/book", headers=AUTH_WRITE)
    assert 400 <= r.status_code < 500, r.text
    assert outside.exists(), "the external file must not be deleted"
    assert outside.read_bytes() == b"PRE-EXISTING"


@pytest.mark.asyncio
async def test_default_player_maps_to_ebassti(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """The ``default`` -> ``ebassti`` canonical mapping is preserved."""
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            "/v1/repertoire/default/book",
            json=[{"fen": STARTING_FEN, "uci_move": "e2e4"}],
            headers=AUTH_WRITE,
        )
    assert r.status_code == 200, r.text
    assert r.json()["player"] == "ebassti"
    assert (Path(settings.books_dir) / "ebassti.bin").exists()


# ======================================================================
# 5. Malformed stored-file metadata
# ======================================================================


@pytest.mark.asyncio
async def test_get_never_reports_malformed_as_zero_entries(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """A corrupt stored book must NOT be reported as an empty book."""
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    # 5 bytes: not a multiple of 16.
    _write_book_file(settings, "ebassti", b"\x00\x01\x02\x03\x04")
    async with _hit(app, "GET", BOOK_URL) as ac:
        r = await ac.get(BOOK_URL, headers=AUTH_READONLY)
    assert 400 <= r.status_code < 500, r.text
    assert "client.malformed_book" in r.text
    assert r.json()["error"]["code"] == "client.malformed_book"


@pytest.mark.asyncio
async def test_get_never_returns_binary_content(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """GET returns metadata only."""
    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    _write_book_file(settings, "ebassti", b"\x00" * 32)
    async with _hit(app, "GET", BOOK_URL) as ac:
        r = await ac.get(BOOK_URL, headers=AUTH_READONLY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"player", "size_bytes", "entry_count", "last_modified"}
    assert body["entry_count"] == 2


def test_entry_count_never_fabricates_zero_for_malformed() -> None:
    with pytest.raises(MalformedBookBytesError):
        entry_count_from_size(5)
    assert entry_count_from_size(0) == 0
    assert entry_count_from_size(32) == 2


# ======================================================================
# 6. Real application-factory route registration
# ======================================================================


def test_real_app_factory_exposes_the_three_book_endpoints() -> None:
    """The REAL application factory exposes PUT, GET and DELETE.

    The pre-existing integration fixture mounts the book router
    directly, which does not prove the gateway actually serves these
    routes. This test uses ``create_app``.
    """
    from chess_coach.gateway.app import create_app

    app = create_app()
    # The OpenAPI schema is the version-agnostic route surface. (In
    # FastAPI 0.141 `app.routes` holds `_IncludedRouter` objects, so
    # an included router's routes are NOT flattened into `app.routes`
    # and a naive `app.routes` scan misses them entirely.)
    paths = app.openapi()["paths"]
    assert "/v1/repertoire/{player}/book" in paths, (
        "the real application factory must expose the book route"
    )
    methods = {m.upper() for m in paths["/v1/repertoire/{player}/book"]}
    assert "PUT" in methods
    assert "GET" in methods
    assert "DELETE" in methods


# ======================================================================
# 7. Independent Polyglot-format interoperability
# ======================================================================


@pytest.mark.asyncio
async def test_independent_parser_reads_the_project_written_book(
    _tmp_data_dir: str, _active_token_lifecycle: Any  # noqa: PT019
) -> None:  # noqa: PT019
    """A project-written file is consumable by an INDEPENDENT parser."""
    import chess
    from chess.polyglot import zobrist_hash

    app, settings = _make_app_with_books_dir(_tmp_data_dir)
    async with _hit(app, "PUT", BOOK_URL) as ac:
        r = await ac.put(
            BOOK_URL,
            json=[
                {"fen": STARTING_FEN, "uci_move": "e2e4", "weight": 321},
                {"fen": STARTING_FEN, "uci_move": "d2d4", "weight": 654},
            ],
            headers=AUTH_WRITE,
        )
    assert r.status_code == 200, r.text

    data = (Path(settings.books_dir) / "ebassti.bin").read_bytes()
    entries = independent_parse_book(data)
    assert len(entries) == 2

    # The exact key: the position's zobrist hash.
    expected_key = zobrist_hash(chess.Board(STARTING_FEN))
    assert {e["key"] for e in entries} == {expected_key}

    # The exact move encoding: (from << 6) | to, raster-scan squares.
    # The public Polyglot numbering is a1=0, b1=1, ... h1=7, a2=8, ...
    # h8=63 — the same a1=0 indexing as python-chess's
    # chess.square(file, rank).
    move = chess.Move.from_uci("e2e4")
    e2 = chess.square(4, 1)  # file 4 (e), rank 1 (2) -> 12
    e4 = chess.square(4, 3)  # file 4 (e), rank 3 (4) -> 28
    assert e2 == 12
    assert e4 == 28
    assert (move.from_square, move.to_square) == (e2, e4)
    matching = [e for e in entries if e["from_square"] == e2 and e["to_square"] == e4]
    assert matching, "the e2e4 entry must be decodable by the independent parser"
    assert matching[0]["weight"] == 321
    assert matching[0]["learn"] == 0

    # Lookup by key, as a Polyglot reader does.
    found = _independent_find(data, expected_key)
    assert len(found) == 2
    assert {f["weight"] for f in found} == {321, 654}


def test_independent_parser_rejects_a_malformed_payload() -> None:
    with pytest.raises(ValueError, match="16-byte entries"):
        independent_parse_book(b"\x00" * 5)


def test_entries_are_sorted_by_key_and_use_the_big_endian_layout() -> None:
    """The writer's layout: 16-byte entries, sorted ascending by key."""
    from chess_coach.repertoire.polyglot_writer import BookEntry, write_polyglot_book

    with tempfile.TemporaryDirectory(prefix="fu11_poly_") as tmp:
        path = Path(tmp) / "book.bin"
        entries = [
            BookEntry(fen=STARTING_FEN, uci_move="e2e4", weight=1),
            BookEntry(fen=STARTING_FEN, uci_move="d2d4", weight=2),
            BookEntry(
                fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
                uci_move="e7e5",
                weight=3,
            ),
        ]
        write_polyglot_book(entries, str(path))
        data = path.read_bytes()

    assert len(data) % 16 == 0
    decoded = independent_parse_book(data)
    keys = [d["key"] for d in decoded]
    assert keys == sorted(keys), "entries must be ordered by key, lowest first"
    # The big-endian layout: the first entry's key is the first 8 bytes,
    # most-significant byte first.
    assert struct.unpack(">Q", data[0:8])[0] == keys[0]
    assert struct.unpack("<Q", data[0:8])[0] != keys[0]


def test_empty_book_is_zero_bytes_and_parses_as_no_entries() -> None:
    """The established empty-book representation is preserved."""
    from chess_coach.repertoire.polyglot_writer import write_polyglot_book

    with tempfile.TemporaryDirectory(prefix="fu11_poly_") as tmp:
        path = Path(tmp) / "empty.bin"
        write_polyglot_book([], str(path))
        data = path.read_bytes()
    assert data == b""
    assert independent_parse_book(data) == []
