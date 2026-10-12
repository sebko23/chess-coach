"""Routes for per-player Polyglot ``.bin`` book storage.

BBF-FU-11b — Tier 2 of the FU-11 (β = server-managed persistent book
support) sequencing per the decision brief at
``docs/16_audit/BBF-FU-11-polyglot-persistent-book-decision.md``.

Endpoints
---------

- ``PUT /v1/repertoire/{player}/book`` — write a Polyglot ``.bin`` for
  the named player. Body is a JSON list of ``BookEntryIn`` objects.
  Requires ``BOOKS_WRITE`` scope.
- ``GET /v1/repertoire/{player}/book`` — return metadata (size,
  entry count, last-modified) for the named player's stored book.
  No scope required (read-only-equivalent).
- ``DELETE /v1/repertoire/{player}/book`` — remove the named player's
  stored book. Idempotent: returns ``{"deleted": false, ...}`` if no
  book was stored. Requires ``BOOKS_WRITE`` scope.

Storage location: ``<data_dir>/books/<player>.bin`` per the
``GatewaySettings.books_dir`` property added in this BBF.

Player name normalization: the α route (``repertoire_recommendations.py``)
resolves ``"default"`` to ``"ebassti"`` before using the name. We
follow the same convention here, so a caller can use either
``/v1/repertoire/default/book`` or ``/v1/repertoire/ebassti/book`` and
both write to the same file.

Path safety: player names are validated to reject ``.``, ``/``,
``\\``, and the empty string. This prevents a caller from passing
``../foo`` and writing outside ``books_dir``. The α route does not
do this kind of validation because it only READS the name (for the
SQLite query), but the β route WRITES files and so must guard
against traversal.

This module depends on:
- :func:`chess_coach.gateway.auth.require_bearer_with_scope` (BBF-FU-11a)
- :class:`chess_coach.repertoire.polyglot_writer.BookEntry`
- :func:`chess_coach.repertoire.polyglot_writer.write_polyglot_writer`
- :class:`chess_coach.gateway.config.GatewaySettings`

A note on the FastAPI dep pattern
---------------------------------

FastAPI's ``dependencies=[Depends(...)]`` in the route decorator
expects a **synchronous callable**. Our :func:`require_bearer_with_scope`
is ``async def`` and takes two args: ``scope`` (a string constant)
and ``authorization`` (FastAPI-managed). When we write
``Depends(require_bearer_with_scope("BOOKS_WRITE"))``, the call
returns a coroutine, which is not a callable for FastAPI's purpose
(``assert callable(depends.dependency)`` fails at route-registration
time).

The fix is the standard FastAPI pattern for "parameterized dep":
a thin async wrapper that closes over the scope arg and calls the
underlying dep. The wrapper is itself async (because the underlying
dep is async), so the result is a coroutine — but FastAPI accepts
async deps via this wrapper pattern, just not via the bare-call
pattern. See ``_require_books_write`` below for the implementation.
"""
# ruff: noqa: B008  -- FastAPI Depends() in argument defaults is the intended pattern; flagged uniformly across all route handlers.
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from chess_coach.errors.codes import ErrorCode
from chess_coach.gateway.auth import (
    require_bearer,
    require_bearer_with_scope,
)
from chess_coach.repertoire.polyglot_writer import (
    BookEntry,
    write_polyglot_book,
)

from ..route_guard import route_guard
from .repertoire_recommendations import DEFAULT_PLAYER

logger = logging.getLogger(__name__)

# Scope string for the BOOKS_WRITE dep. Match the convention in the
# BBF-FU-11 decision brief and the BBF-FU-11a auth.py module docstring.
BOOKS_WRITE_SCOPE = "BOOKS_WRITE"

# Polyglot entry size, per the writer's constant. Hard-coded here so
# the GET metadata path doesn't need to import the writer's private
# constant. (The writer's ENTRY_SIZE = 16 is a public-looking constant
# but moving it to a shared location would be scope creep for this BBF.)
_POLYGLOT_ENTRY_SIZE = 16

# Player-name validation: reject any name that contains characters
# which would let a caller traverse the books_dir filesystem. The α
# route uses these names as DB identifiers, but the β route uses
# them as filesystem path components, so the validation is stricter.
_PLAYER_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

router = APIRouter(prefix="/v1/repertoire", tags=["repertoire", "book"])


# --- FastAPI dep wrappers ----------------------------------------------------


async def _require_books_write(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """FastAPI dep: require ``BOOKS_WRITE`` scope on the bearer token.

    Thin wrapper around :func:`require_bearer_with_scope` that closes
    over the scope name. FastAPI requires the wrapper to be async
    (because the underlying dep is async) and to take only
    FastAPI-managed parameters (``authorization`` here, declared with
    ``Header(alias="Authorization")`` so FastAPI reads it from the
    HTTP header, NOT from a query string). See the module docstring's
    "note on the FastAPI dep pattern" section for the rationale.
    """
    await require_bearer_with_scope(BOOKS_WRITE_SCOPE, authorization=authorization)


# --- request/response models -------------------------------------------------


class BookEntryIn(BaseModel):
    """One Polyglot book entry as it arrives in the PUT body.

    Mirrors :class:`chess_coach.repertoire.polyglot_writer.BookEntry`
    (the dataclass the writer consumes). Validated at the boundary
    so the writer's ``ValueError`` checks become 400s, not 500s.
    """

    fen: str = Field(
        ...,
        description=(
            "FEN string for the position. Must parse as a legal chess "
            "position by python-chess's Board constructor."
        ),
    )
    uci_move: str = Field(
        ...,
        description=(
            "UCI move string (e.g., 'e2e4'). Must be a legal move from "
            "the FEN. Validated against the writer's encoding rules."
        ),
    )
    weight: int = Field(
        default=100,
        ge=0,
        le=0xFFFF,
        description="Polyglot weight 0..65535. Defaults to 100 (hand-curated).",
    )
    learn: int = Field(
        default=0,
        ge=0,
        le=0xFFFFFFFF,
        description=(
            "Polyglot learn field (4 bytes, engine learning data). "
            "Default 0 for hand-curated books."
        ),
    )


class PutBookResponse(BaseModel):
    player: str
    size_bytes: int
    entry_count: int


class GetBookResponse(BaseModel):
    player: str
    size_bytes: int
    entry_count: int
    last_modified: str  # ISO-8601 UTC


class DeleteBookResponse(BaseModel):
    player: str
    deleted: bool
    reason: str | None = None


# --- helpers -----------------------------------------------------------------


def _resolve_player(player: str) -> str:
    """Resolve the player path param to a filesystem-safe name.

    Mirrors the α route's ``"ebassti" if player == "default" else player``
    (per ``repertoire_recommendations.py:242``). Validates the result
    against ``_PLAYER_NAME_RE`` to prevent path traversal.

    Raises ``HTTPException(400)`` on invalid input.
    """
    resolved = DEFAULT_PLAYER if player == "default" else player
    if not _PLAYER_NAME_RE.match(resolved):
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.BAD_REQUEST.value,
                "message": (
                    f"Invalid player name: {player!r}. "
                    f"Must match {_PLAYER_NAME_RE.pattern!r}."
                ),
            },
        )
    return resolved


def _books_dir(request: Request) -> Path:
    """Return the configured books directory, creating it on first read.

    The directory is created lazily here (not at gateway startup)
    so test environments that never call a book route don't create
    the directory. Tests that do call a book route get a fresh
    per-test ``data_dir`` (per ``tests/conftest.py:_isolate_env``)
    so the lazy creation is per-test.
    """
    settings = request.app.state.gateway.settings
    books = settings.books_dir
    books.mkdir(parents=True, exist_ok=True)
    return books


def _book_path(books: Path, player: str) -> Path:
    return books / f"{player}.bin"


def _file_size_and_mtime(path: Path) -> tuple[int, float]:
    """Return ``(size_bytes, mtime_epoch)`` for the file at ``path``.

    Raises ``FileNotFoundError`` if the file doesn't exist. Caller
    is responsible for catching.
    """
    stat = path.stat()
    return stat.st_size, stat.st_mtime


def _entry_count_from_size(size_bytes: int) -> int:
    """Number of Polyglot entries implied by the file size.

    Each entry is 16 bytes (8-byte key + 2-byte move + 2-byte weight +
    4-byte learn). An empty book is 0 bytes = 0 entries. A file
    whose size is not a multiple of 16 is malformed; we surface this
    as 0 (caller may want to flag it) and rely on the writer's
    16-byte invariant to prevent new malformations.
    """
    if size_bytes % _POLYGLOT_ENTRY_SIZE != 0:
        logger.warning(
            "Book file size %d is not a multiple of %d; treating as 0 entries.",
            size_bytes,
            _POLYGLOT_ENTRY_SIZE,
        )
        return 0
    return size_bytes // _POLYGLOT_ENTRY_SIZE


# --- endpoints ---------------------------------------------------------------


@router.put(
    "/{player}/book",
    response_model=PutBookResponse,
    status_code=200,
    dependencies=[Depends(_require_books_write)],
)
@route_guard
async def put_book(
    player: str,
    body: list[BookEntryIn],
    request: Request,
) -> PutBookResponse:
    """Write a per-player Polyglot ``.bin`` book.

    Body is a JSON list of ``BookEntryIn`` objects. The route converts
    each to the writer's ``BookEntry`` dataclass and delegates the
    actual byte writing to
    :func:`chess_coach.repertoire.polyglot_writer.write_polyglot_book`.

    The writer validates:
      - each move is legal from the FEN (writer raises ``ValueError``)
      - each weight is in 0..65535 (writer raises ``ValueError``)

    Both writer exceptions become 400 responses with the protocol
    error envelope (``client.bad_request``). Path-traversal attempts
    (player name with ``.`` or ``/``) are rejected at the boundary
    with a 400 before the writer is called.

    Requires ``BOOKS_WRITE`` scope. Per the BBF-FU-11a auth design,
    a token with no scope (plain ``devtoken123``) is read-only and
    fails this dep with 401.

    Empty body (zero entries) is a valid write — produces a 0-byte
    file at the path. Per the writer, an empty book round-trips as
    ``find_all() -> []`` for every FEN (handled by the library's
    ``_EmptyMmap`` fallback).
    """
    resolved = _resolve_player(player)
    books = _books_dir(request)
    path = _book_path(books, resolved)

    # Convert the Pydantic list to the writer's dataclass list. The
    # writer's _build_entry_bytes does the actual move legality check
    # (against a Board constructed from the FEN); if a BookEntry's
    # uci_move is illegal from its FEN, the writer raises ValueError
    # which we surface as 400.
    entries: list[BookEntry] = [
        BookEntry(
            fen=item.fen,
            uci_move=item.uci_move,
            weight=item.weight,
            learn=item.learn,
        )
        for item in body
    ]
    try:
        size_bytes = write_polyglot_book(entries, str(path))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.BAD_REQUEST.value,
                "message": str(exc),
            },
        ) from exc
    logger.info(
        "book.put: player=%s entries=%d size_bytes=%d path=%s",
        resolved,
        len(entries),
        size_bytes,
        path,
    )
    return PutBookResponse(
        player=resolved,
        size_bytes=size_bytes,
        entry_count=len(entries),
    )


@router.get(
    "/{player}/book",
    response_model=GetBookResponse,
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def get_book(
    player: str,
    request: Request,
) -> GetBookResponse:
    """Return metadata for the named player's stored book.

    Returns 404 if no book is stored. The body of the .bin file is
    NOT returned (use PUT + read locally, or open the file via a
    separate admin tool). This is the design from the BBF-FU-11
    decision brief §3.2: "returns the metadata (size, mtime, entry
    count) WITHOUT returning the binary content."

    Requires ``require_bearer`` (any authed caller, including
    read-only tokens). No scope check.
    """
    resolved = _resolve_player(player)
    books = _books_dir(request)
    path = _book_path(books, resolved)
    try:
        size_bytes, mtime_epoch = _file_size_and_mtime(path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.NOT_FOUND.value,
                "message": f"No book stored for player: {resolved!r}.",
            },
        ) from exc
    last_modified = datetime.fromtimestamp(mtime_epoch, tz=UTC).isoformat()
    return GetBookResponse(
        player=resolved,
        size_bytes=size_bytes,
        entry_count=_entry_count_from_size(size_bytes),
        last_modified=last_modified,
    )


@router.delete(
    "/{player}/book",
    response_model=DeleteBookResponse,
    status_code=200,
    dependencies=[Depends(_require_books_write)],
)
@route_guard
async def delete_book(
    player: str,
    request: Request,
) -> DeleteBookResponse:
    """Remove the named player's stored book.

    Idempotent: returns ``{"deleted": false, "reason": "no book stored"}``
    if the file does not exist. The caller does not need to check
    before calling.

    Requires ``BOOKS_WRITE`` scope.
    """
    resolved = _resolve_player(player)
    books = _books_dir(request)
    path = _book_path(books, resolved)
    try:
        path.unlink()
        logger.info("book.delete: player=%s path=%s", resolved, path)
        return DeleteBookResponse(player=resolved, deleted=True)
    except FileNotFoundError:
        logger.info("book.delete: player=%s (no book stored)", resolved)
        return DeleteBookResponse(
            player=resolved,
            deleted=False,
            reason="no book stored",
        )
