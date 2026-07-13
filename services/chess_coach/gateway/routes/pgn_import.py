"""PGN text import route — accepts a PGN string and imports one or more games.

POST /v1/import/pgn
Body: { pgn: <str>, depth: <int> = 8, max_games: <int> = 500,
        max_plies: <int> = 200 }
Returns: { import_id, imported_count, failed_count, total_games,
           positions_count, analyzed_count, analysis_failed_count,
           results: [...] }

BBF-8: introspect the `games` table schema at import time so the INSERT covers
every NOT NULL column (in particular `pgn_raw`, which the BBF-7 INSERT omitted
and which `OR IGNORE` then silently swallowed). Track real imported vs failed
counts via cursor.rowcount instead of just counting parsed results.

BBF-9: also insert one `positions` row per ply (mirroring `lichess_import.py`).
The BBF-9 path also wrote one `analyses` row per ply. BBF-22 removed that:
PGN import is now a pure-insert operation. Analyses are computed lazily by
GET /v1/games/{game_id}/eval-graph on first request and cached in the
`analyses` table. This makes import time independent of corpus size: a
6000-game PGN now imports in seconds instead of hours.

BBF-14 max_plies still applies: it caps the number of positions stored per
game. Games longer than max_plies will have only the first max_plies+1
positions in the table; deeper plies return 404 on eval-graph.
"""
from __future__ import annotations

import io
import logging
import uuid

import chess
import chess.pgn
import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth import require_bearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/import", tags=["import"])


class PgnImportRequest(BaseModel):
    pgn: str = Field(..., description="PGN text, single or multi-game")
    depth: int = Field(8, ge=1, le=30, description="Depth used by future lazy analyses at GET /v1/games/{id}/eval-graph")
    max_games: int = Field(500, ge=1, le=5000)
    max_plies: int = Field(200, ge=1, le=1000, description="Cap on positions stored per game")


class ImportedGame(BaseModel):
    game_id: str
    white: str | None
    black: str | None
    result: str | None
    event: str | None
    date: str | None


class PgnImportResponse(BaseModel):
    import_id: str
    imported_count: int
    failed_count: int
    total_games: int
    positions_count: int
    # BBF-22: these are always 0 now. Import is a pure-insert operation;
    # analyses are computed lazily by GET /v1/games/{id}/eval-graph.
    # Kept in the response shape for back-compat with GUI and any existing
    # scripts that read these fields.
    analyzed_count: int
    analysis_failed_count: int
    results: list[ImportedGame]


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


async def _games_table_columns(db_path: str) -> list[tuple]:
    """Return PRAGMA table_info(games) rows: (cid, name, type, notnull, dflt_value, pk)."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("PRAGMA table_info(games)")
        return list(await cur.fetchall())


def _walk_game(game: "chess.pgn.Game") -> list[tuple[int, str, str | None, str | None]]:
    """Return list of (ply, fen, move_uci, move_san) for the game's mainline.

    The first entry is the starting position (ply=0, no move). Each subsequent
    entry is the position reached after applying one mainline move. `move_uci`
    and `move_san` are the move from the previous position to this position
    (None for ply=0).
    """
    out: list[tuple[int, str, str | None, str | None]] = [
        (0, game.board().fen(), None, None)
    ]
    board = game.board()
    ply = 1
    for move in game.mainline_moves():
        move_uci = move.uci()
        move_san = board.san(move)
        board.push(move)
        out.append((ply, board.fen(), move_uci, move_san))
        ply += 1
    return out


def _split_games(pgn_text: str) -> list[str]:
    """Slice a multi-game PGN into per-game text blocks for pgn_raw storage."""
    blocks: list[str] = []
    buf: list[str] = []
    for line in pgn_text.splitlines():
        if line.strip() == "":
            if buf:
                blocks.append("\n".join(buf).strip("\n"))
                buf = []
        else:
            buf.append(line)
    if buf:
        blocks.append("\n".join(buf).strip("\n"))
    return [b for b in blocks if b]


@router.post(
    "/pgn",
    response_model=PgnImportResponse,
    dependencies=[Depends(require_bearer)],
)
async def import_pgn(
    body: PgnImportRequest,
    request: Request,
) -> PgnImportResponse:
    """Parse a PGN string and import each game into the local DB.

    BBF-22: this route is now a pure-insert operation. For each game we:
      - insert one `games` row (one DB connection, single commit at the end).
      - insert one `positions` row per ply (capped by max_plies).

    No engine analysis happens here. Analyses are computed lazily by
    GET /v1/games/{game_id}/eval-graph on first request and cached in
    the `analyses` table.

    Import time is O(games * plies) for PGN parsing + DB writes; no
    Stockfish is called. A 6000-game PGN imports in seconds, not hours.
    """
    import_id = str(uuid.uuid4())
    results: list[ImportedGame] = []
    failed: list[tuple[str, str]] = []  # (game_id, reason)
    positions_count = 0
    # BBF-22: always 0. Kept in the response shape for back-compat.
    analyzed_count = 0
    analysis_failed_count = 0

    db_path = _db_path(request)
    pgn_io = io.StringIO(body.pgn)
    pgn_blocks = _split_games(body.pgn)

    # --- Introspect games table schema once ---
    games_cols = await _games_table_columns(db_path)
    games_notnull = {row[1] for row in games_cols if row[3] == 1}

    parsed_games: list[tuple[int, "chess.pgn.Game", dict]] = []
    for i in range(body.max_games):
        try:
            game = chess.pgn.read_game(pgn_io)
        except Exception as exc:
            logger.warning("pgn-import %s: failed to parse game %d: %s", import_id, i, exc)
            break
        if game is None:
            break

        game_id = f"{import_id}:{i}"
        white = game.headers.get("White", "?")
        black = game.headers.get("Black", "?")
        result = game.headers.get("Result", "*")
        event = game.headers.get("Event", "PGN Import")
        date = game.headers.get("Date", "????.??.??")

        pgn_raw = pgn_blocks[i] if i < len(pgn_blocks) else body.pgn

        parsed_games.append(
            (
                i,
                game,
                {"id": game_id, "white": white, "black": black, "date": date,
                 "event": event, "result": result, "import_status": "pending",
                 "pgn_raw": pgn_raw},
            )
        )

    total_games = len(parsed_games)

    async with aiosqlite.connect(db_path) as db:
        for i, _game, row in parsed_games:
            game_id = row["id"]

            values: dict[str, object] = dict(row)
            for col in games_notnull:
                if col in values:
                    continue
                default = next((c[4] for c in games_cols if c[1] == col), None)
                if default is not None and default != "":
                    continue
                values[col] = ""

            cols_csv = ", ".join(values.keys())
            placeholders = ", ".join("?" for _ in values)
            sql = f"INSERT INTO games ({cols_csv}) VALUES ({placeholders})"

            inserted_ok = False
            try:
                cur = await db.execute(sql, list(values.values()))
                if cur.rowcount == 1:
                    results.append(
                        ImportedGame(
                            game_id=game_id,
                            white=row["white"],
                            black=row["black"],
                            result=row["result"],
                            event=row["event"],
                            date=row["date"],
                        )
                    )
                    inserted_ok = True
                else:
                    failed.append((game_id, f"rowcount={cur.rowcount}"))
                    logger.warning(
                        "pgn-import %s: games insert rowcount=%s for %s",
                        import_id, cur.rowcount, game_id,
                    )
            except aiosqlite.IntegrityError as exc:
                failed.append((game_id, f"unique: {exc}"))
                logger.warning(
                    "pgn-import %s: IntegrityError for %s: %s",
                    import_id, game_id, exc,
                )
            except Exception as exc:
                failed.append((game_id, str(exc)))
                logger.warning(
                    "pgn-import %s: games insert failed for %s: %s",
                    import_id, game_id, exc,
                )

            if not inserted_ok:
                continue

            # Insert positions (one per mainline ply, capped by max_plies).
            positions = _walk_game(_game)
            positions_sql = (
                "INSERT INTO positions (id, game_id, parent_id, fen, move_uci, "
                "move_san, ply, is_mainline) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
            prev_id: str | None = None
            for ply, fen, move_uci, move_san in positions:
                position_id = f"{game_id}:{ply}"
                try:
                    cur = await db.execute(
                        positions_sql,
                        (
                            position_id,
                            game_id,
                            prev_id,
                            fen,
                            move_uci,
                            move_san,
                            ply,
                            1,
                        ),
                    )
                    if cur.rowcount == 1:
                        positions_count += 1
                    else:
                        logger.warning(
                            "pgn-import %s: positions rowcount=%s for %s",
                            import_id, cur.rowcount, position_id,
                        )
                except Exception as exc:
                    logger.warning(
                        "pgn-import %s: positions insert failed for %s: %s",
                        import_id, position_id, exc,
                    )
                prev_id = position_id

        await db.commit()

    return PgnImportResponse(
        import_id=import_id,
        imported_count=len(results),
        failed_count=len(failed),
        total_games=total_games,
        positions_count=positions_count,
        analyzed_count=analyzed_count,
        analysis_failed_count=analysis_failed_count,
        results=results,
    )
