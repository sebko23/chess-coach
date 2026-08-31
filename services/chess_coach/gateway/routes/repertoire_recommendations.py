"""Repertoire recommendations — engine-powered gap analysis, with optional
Polyglot opening-book augmentation (FU-7, α + protocol option (a) +
blending (iv)).

POST /v1/repertoire/{player}/recommendations

Engine-powered baseline (BBF-87.2): reads gap positions (ply 6-16, never
played by player) and runs Stockfish to suggest the best move for each,
ranked by urgency.

FU-7 additive field on the request (no response echo):
  - ``polyglot_book_path`` (optional): caller-supplied path to a Polyglot
    ``.bin`` opening book. When provided, the route augments engine
    suggestions with book entries for the same FEN, surfaced as additional
    ``RecommendationItem`` entries with ``source = "book"`` (or ``"both"``
    when the engine also surfaced that UCI). The caller decides ordering.

Honest framing (per the FU-7 design directive, 2026-08-07):
  This is the FIRST STEP toward book-aware repertoire recommendations,
  NOT "repertoire management." It accepts a per-call book path only,
  never persists it, never indexes it, never learns from it. The β
  follow-up (persistent-book support, server-managed book state) is
  the Phase 2 trigger point and is tracked in ``OPEN-FOLLOWUPS.md`` as
  ``FU-11``. Do not let this field grow into a "repertoire management"
  surface — that's a different (and much larger) feature.

Blending policy (iv) — no server-side arbitration:
  Each distinct UCI move either side surfaces becomes its own
  ``RecommendationItem`` tagged with ``source``. The route does NOT pick
  a "best" move across engine + book; the caller renders. If the book
  has the FEN, every distinct book entry is yielded; if the engine
  produces multipv=N PVs, every distinct engine move is yielded. They
  union by UCI string. ``"both"`` only when engine and book surface the
  exact same UCI.

Error handling for bad book paths:
  - Directory path (e.g. caller passes a directory where a ``.bin`` file is
    expected) -> HTTP 400 with code ``client.bad_request``. Pre-checked via
    ``os.path.isdir()`` BEFORE ``chess.polyglot.open_reader()`` because on
    Linux that call silently returns an empty reader (the library's
    ``_EmptyMmap`` workaround at ``chess/polyglot.py:330`` swallows the
    OSError from ``mmap`` on a directory fd), which would otherwise fall
    through to the engine-only 200 path. Platform-deterministic 400.
  - ``FileNotFoundError``, ``PermissionError``, ``IsADirectoryError``,
    ``OSError`` from ``open_reader`` -> HTTP 400 with code
    ``client.bad_request``. The caller supplied the path; failure to
    read it is caller error, not server error.
  - ``Exception`` from ``find_all`` (catches malformed-but-readable
    .bin files whose entries don't parse) -> HTTP 400 with code
    ``client.bad_request``, same rationale.
  - Empty / valid .bin with no entry for the queried FEN -> NOT an
    error; the engine-only path runs as if no book was supplied, with
    each item tagged ``source = "engine"``. That is the normal
    "book doesn't cover this position" case.
"""
# ruff: noqa: B008  -- FastAPI Depends() in argument defaults is the intended pattern; flagged uniformly across all route handlers.
from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from chess_coach.engine_orch.pool import EnginePool
from chess_coach.errors.codes import ErrorCode
from chess_coach.protocol_types.analysis import AnalysisRequest

from ..auth import require_bearer
from ..route_guard import route_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/repertoire", tags=["repertoire"])


# Source-of-truth tag for whether a recommendation came from the engine,
# the book, or both (when both surfaced the same UCI for the same FEN).
# No server-side arbitration: caller decides precedence.
SourceT = Literal["engine", "book", "both"]


def _pool(request: Request) -> EnginePool:
    return request.app.state.engine_pool


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


class RecommendationItem(BaseModel):
    fen: str
    ply: int
    priority: Literal["critical", "important", "normal"]
    best_move_uci: str | None
    best_move_san: str | None
    score_cp: int | None
    depth_reached: int
    alternatives_uci: list[str]
    alternatives_san: list[str]
    # FU-7 additive fields:
    # - ``source`` distinguishes engine-backed vs book-backed vs both-agreed
    #   recommendations. Always present (engine is the always-on baseline).
    # - ``book_weight`` is the Polyglot entry's weight when ``source in
    #   {"book", "both"}``; ``None`` when source == "engine" only.
    source: SourceT = "engine"
    book_weight: int | None = None


class RecommendationsResponse(BaseModel):
    player_name: str
    color: str
    total_gaps: int
    recommendations: list[RecommendationItem]


def _priority(score_cp: int | None) -> Literal["critical", "important", "normal"]:
    if score_cp is None:
        return "normal"
    # score from White's perspective; large positive means White is winning
    if abs(score_cp) >= 150:
        return "critical"
    if abs(score_cp) >= 100:
        return "important"
    return "normal"


def _fen_to_color(fen: str) -> str:
    """Return 'white' or 'black' depending on whose turn it is."""
    parts = fen.split()
    return "white" if len(parts) > 1 and parts[1] == "w" else "black"


def _uci_to_san(fen: str, uci: str) -> str:
    """Convert a UCI move (e.g. 'e2e4') to SAN (e.g. 'e4'). Falls back to UCI."""
    try:
        import chess
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        if move in board.legal_moves:
            return board.san(move)
    except (ImportError, ValueError) as exc:
        logger.debug("Falling back to UCI for move %s: %s", uci, exc)
    return uci


def _book_moves_for_fen(book_path: str, fen: str) -> list[tuple[str, int]]:
    """Return [(uci, weight), ...] for every Polyglot entry that matches the FEN.

    Raises ``HTTPException(400)`` if the book cannot be read or does not
    parse. A valid book with zero entries for the queried FEN returns an
    empty list (the normal "book doesn't cover this position" case is
    NOT an error).
    """
    import chess
    import chess.polyglot

    board = chess.Board(fen)
    # Pre-check for directory paths: chess.polyglot.open_reader() on Linux
    # silently returns an empty reader for a directory fd (the library's
    # _EmptyMmap workaround at chess/polyglot.py:330 swallows the OSError
    # from mmap on a directory), which would otherwise fall through to the
    # engine-only 200 path. This pre-check makes the 400 platform-deterministic.
    if os.path.isdir(book_path):
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.BAD_REQUEST.value,
                "message": (
                    f"polyglot_book_path is a directory: {book_path}"
                ),
            },
        )
    try:
        with chess.polyglot.open_reader(book_path) as reader:
            entries = list(reader.find_all(board))
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.BAD_REQUEST.value,
                "message": (
                    f"polyglot_book_path is not a readable Polyglot .bin file: {exc}"
                ),
            },
        ) from exc
    except Exception as exc:  # malformed-but-readable .bin, parse errors, etc.
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.BAD_REQUEST.value,
                "message": (
                    f"polyglot_book_path did not parse as a Polyglot .bin file: {exc}"
                ),
            },
        ) from exc
    return [(entry.move.uci(), entry.weight) for entry in entries]


@router.post(
    "/{player}/recommendations",
    response_model=RecommendationsResponse,
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def get_recommendations(
    player: str,
    color: str = Query("white", pattern="^(white|black)$"),
    limit: int = Query(5, ge=1, le=20),
    engine_id: str = Query("stockfish"),
    # FU-7 additive request field: optional path to a Polyglot ``.bin``
    # opening book. None / unset = engine-only baseline (BBF-87.2 path).
    polyglot_book_path: str | None = Query(
        None,
        description=(
            "Optional path to a Polyglot .bin opening book. When provided, "
            "book entries for each gap FEN are surfaced alongside engine "
            "PVs (per FU-7 blending (iv): per-move union, no arbitration). "
            "Caller decides precedence. Per-call only — not persisted."
        ),
    ),
    pool: EnginePool = Depends(_pool),
    db_path: str = Depends(_db_path),
) -> RecommendationsResponse:
    """Return engine-backed move suggestions for repertoire gaps.

    When ``polyglot_book_path`` is supplied, also surface book entries for
    the same FENs as additional recommendations tagged ``source="book"``
    (or ``"both"`` when the engine already surfaced that UCI). Caller
    decides ordering — this route never arbitrates between engine and book.
    """

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        resolved = "ebassti" if player == "default" else player
        side = "w" if color == "white" else "b"
        rows = await db.execute_fetchall(
                """SELECT p.fen, p.ply, COUNT(*) as cnt
                   FROM positions p
                   JOIN games g ON p.game_id = g.id
                   WHERE p.ply BETWEEN 6 AND 16
                     AND (g.white = ? OR g.black = ?)
                     AND SUBSTR(p.fen, INSTR(p.fen, " ") + 1, 1) = ?
                   GROUP BY p.fen, p.ply
                   HAVING cnt < 3
                   ORDER BY p.ply ASC
                   LIMIT ?""",
            (resolved, resolved, side, limit),
        )

    total_gaps = len(rows)

    async def _analyze_row(row: aiosqlite.Row) -> list[RecommendationItem]:
        """Return one or more items per FEN.

        Engine-only path: 1 item tagged ``source="engine"``.
        Engine + book path: N items (N = |engine_moves ∪ book_moves|),
            each tagged ``"engine"`` / ``"book"`` / ``"both"`` per UCI.
        """
        fen = row["fen"]
        ply = row["ply"]

        # Engine analysis (always-on baseline). Failures produce a single
        # ``source="engine"`` item with None fields, mirroring BBF-87.2's
        # prior behavior so the additive change doesn't shift failure shape.
        engine_items: list[RecommendationItem] = []
        try:
            result = await pool.analyze(
                AnalysisRequest(fen=fen, depth=10, multipv=3),
                engine_id=engine_id,
            )
            best_pv = result.pvs[0] if result.pvs else None
            score_cp = None
            if best_pv and best_pv.score.kind == "cp":
                score_cp = best_pv.score.value
            best_move_uci = best_pv.moves[0] if (best_pv and best_pv.moves) else None
            best_move_san = (
                _uci_to_san(fen, best_move_uci) if best_move_uci else None
            )
            depth_reached = best_pv.depth if best_pv else 10
            alternatives_uci: list[str] = []
            alternatives_san: list[str] = []
            for pv in result.pvs[1:]:
                if pv.moves:
                    alt = pv.moves[0]
                    alternatives_uci.append(alt)
                    alternatives_san.append(_uci_to_san(fen, alt))
            # Build a single engine-source item; if book overlap is detected
            # later, this item's source flips to "both" and book-only UCIs
            # are appended as additional "book"-tagged items.
            engine_items.append(
                RecommendationItem(
                    fen=fen,
                    ply=ply,
                    priority=_priority(score_cp),
                    best_move_uci=best_move_uci,
                    best_move_san=best_move_san,
                    score_cp=score_cp,
                    depth_reached=depth_reached,
                    alternatives_uci=alternatives_uci,
                    alternatives_san=alternatives_san,
                    source="engine",
                    book_weight=None,
                )
            )
        except Exception as exc:
            logger.warning("recommendations: analysis failed for fen=%s: %s", fen, exc)
            engine_items.append(
                RecommendationItem(
                    fen=fen,
                    ply=ply,
                    priority="normal",
                    best_move_uci=None,
                    best_move_san=None,
                    score_cp=None,
                    depth_reached=0,
                    alternatives_uci=[],
                    alternatives_san=[],
                    source="engine",
                    book_weight=None,
                )
            )

        # No book path supplied -> single engine item, tagged "engine".
        # Mirrors BBF-87.2 response shape 1:1 (one item per FEN).
        if not polyglot_book_path:
            return engine_items

        # Book path supplied -> augment with book entries. _book_moves_for_fen
        # raises HTTPException(400) on bad/unreadable/unparseable paths, so
        # we don't need to guard the result.
        book_moves = _book_moves_for_fen(polyglot_book_path, fen)

        # If book has no entries for this FEN, the engine item stays
        # source="engine". Same response shape as the no-book path.
        if not book_moves:
            return engine_items

        # Build the per-move union by UCI string. The engine's top-1 may
        # match a book entry; in that case the engine item flips to
        # source="both" with the book's weight. Distinct book moves that
        # the engine did NOT surface become additional items tagged "book".
        engine_top_uci = engine_items[0].best_move_uci
        book_ucis = dict(book_moves)

        if engine_top_uci and engine_top_uci in book_ucis:
            # Engine and book agree on the top-1 UCI -> single "both" item
            # with the book's weight. No additional book-only items beyond
            # what the engine did not surface.
            engine_items[0] = engine_items[0].model_copy(
                update={"source": "both", "book_weight": book_ucis[engine_top_uci]}
            )
            engine_only_ucis: dict[str, int] = {
                uci: weight for uci, weight in book_moves if uci != engine_top_uci
            }
        else:
            # Engine top-1 not in book -> engine item stays source="engine".
            # Every book move becomes a separate "book"-tagged item.
            engine_only_ucis = dict(book_ucis)

        for book_uci, book_weight in engine_only_ucis.items():
            engine_items.append(
                RecommendationItem(
                    fen=fen,
                    ply=ply,
                    priority="normal",  # book has no eval; defer to caller
                    best_move_uci=book_uci,
                    best_move_san=_uci_to_san(fen, book_uci),
                    score_cp=None,  # book entries don't carry eval
                    depth_reached=0,
                    alternatives_uci=[],
                    alternatives_san=[],
                    source="book",
                    book_weight=book_weight,
                )
            )
        return engine_items

    # Flatten: _analyze_row now returns a list per FEN; engine + book may
    # produce multiple items per FEN.
    nested = await asyncio.gather(*[_analyze_row(row) for row in rows])
    recommendations: list[RecommendationItem] = [item for sub in nested for item in sub]
    priority_order = {"critical": 0, "important": 1, "normal": 2}
    recommendations.sort(key=lambda r: priority_order[r.priority])

    return RecommendationsResponse(
        player_name=player,
        color=color,
        total_gaps=total_gaps,
        recommendations=recommendations,
    )
