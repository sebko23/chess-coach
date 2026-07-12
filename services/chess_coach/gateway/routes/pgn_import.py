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

BBF-9: also insert one `positions` row per ply (mirroring `lichess_import.py`)
and synchronously analyze each game's starting position, writing one
`analyses` row per game so /v1/games/{id}/eval-graph has real data and the
Coach panel can render a real starting-position analysis.

BBF-14: extend synchronous analysis to every mainline ply up to `max_plies`
(default 200) so newly-imported games have populated eval graphs beyond ply 0.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone

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
    depth: int = Field(8, ge=1, le=30)
    max_games: int = Field(500, ge=1, le=5000)
    max_plies: int = Field(200, ge=1, le=1000, description="Cap on plies analyzed per game")


class ImportedGame(BaseModel):
    game_id: str
    white: str | None
    black: str | None
    result: str | None
    event: str | None
    date: str | None


class PgnImportResponse(BaseModel):
    import_id: str
    imported_count: int        # rows actually inserted into games
    failed_count: int          # game INSERTs that failed
    total_games: int
    positions_count: int       # NEW: total positions inserted across all games
    analyzed_count: int        # NEW: starting positions that got engine analysis
    analysis_failed_count: int # NEW: starting positions whose analysis failed
    results: list[ImportedGame]


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


async def _games_table_columns(db_path: str) -> list[tuple]:
    """Return PRAGMA table_info(games) rows: (cid, name, type, notnull, dflt_value, pk)."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("PRAGMA table_info(games)")
        return list(await cur.fetchall())


async def _positions_table_columns(db_path: str) -> list[tuple]:
    """Return PRAGMA table_info(positions) rows."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("PRAGMA table_info(positions)")
        return list(await cur.fetchall())


async def _analyses_table_columns(db_path: str) -> list[tuple]:
    """Return PRAGMA table_info(analyses) rows."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("PRAGMA table_info(analyses)")
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
    # chess.pgn only exposes parsed objects, so split crudely on blank-line
    # boundaries that separate PGN games; each block is what we'll store in pgn_raw.
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


async def _insert_analysis_row(
    db: aiosqlite.Connection,
    import_id: str,
    position_id: str,
    depth: int,
    result,
    analyses_cols: list[tuple],
    analyses_notnull: set[str],
) -> bool:
    """Insert one engine analysis row for an already-computed result."""
    score_cp = None
    score_mate = None
    pv0 = result.pvs[0] if result.pvs else None
    if pv0 and pv0.score:
        if pv0.score.kind == "cp":
            score_cp = pv0.score.value
        elif pv0.score.kind == "mate":
            score_mate = pv0.score.value

    analyses_row: dict[str, object] = {
        "id": f"{position_id}:stockfish:{depth}",
        "position_id": position_id,
        "engine_id": "stockfish",
        "depth": depth,
        "score_cp": score_cp,
        "score_mate": score_mate,
        "best_move": pv0.moves[0] if pv0 and pv0.moves else None,
        "pv_moves": ",".join(pv0.moves) if pv0 and pv0.moves else None,
        "result_json": result.model_dump_json(),
        "classification": "book",
        "cp_delta": 0,
    }

    # Backfill any other NOT NULL analyses column lacking a value.
    for col in analyses_notnull:
        if col in analyses_row:
            continue
        default = next((c[4] for c in analyses_cols if c[1] == col), None)
        if default is not None and default != "":
            continue
        analyses_row[col] = ""

    cols_csv = ", ".join(analyses_row.keys())
    placeholders = ", ".join("?" for _ in analyses_row)
    sql = f"INSERT OR IGNORE INTO analyses ({cols_csv}) VALUES ({placeholders})"
    try:
        cur = await db.execute(sql, list(analyses_row.values()))
        if cur.rowcount == 1:
            return True
        logger.warning(
            "pgn-import %s: analyses rowcount=%s for %s",
            import_id,
            cur.rowcount,
            position_id,
        )
    except aiosqlite.IntegrityError as exc:
        logger.warning(
            "pgn-import %s: IntegrityError for %s: %s",
            import_id,
            position_id,
            exc,
        )
    except Exception as exc:
        logger.warning(
            "pgn-import %s: analyses insert failed for %s: %s",
            import_id,
            position_id,
            exc,
        )
    return False


async def _analyze_position(
    db: aiosqlite.Connection,
    pool,
    analysis_request_cls,
    import_id: str,
    position_id: str,
    fen: str,
    depth: int,
    analyses_cols: list[tuple],
    analyses_notnull: set[str],
) -> bool:
    """Run Stockfish for one position and insert its analysis row."""
    try:
        req = analysis_request_cls(fen=fen, depth=depth, engine_id="stockfish")
        result = await pool.analyze(req, "stockfish")
    except Exception as exc:
        logger.warning(
            "pgn-import %s: analyze failed for %s: %s",
            import_id,
            position_id,
            exc,
        )
        return False

    return await _insert_analysis_row(
        db,
        import_id,
        position_id,
        depth,
        result,
        analyses_cols,
        analyses_notnull,
    )


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

    For each successfully-inserted game we also:
      - insert one `positions` row per ply (ply=0 is the starting position).
      - synchronously analyze plies 0..max_plies so /v1/games/{id}/eval-graph
        has real data immediately.
    """
    import_id = str(uuid.uuid4())
    results: list[ImportedGame] = []
    failed: list[tuple[str, str]] = []  # (game_id, reason)
    positions_count = 0
    analyzed_count = 0
    analysis_failed_count = 0

    db_path = _db_path(request)
    pgn_io = io.StringIO(body.pgn)
    pgn_blocks = _split_games(body.pgn)

    # Engine pool: may be None if the gateway never finished initializing it.
    pool = getattr(request.app.state, "engine_pool", None)

    # --- Introspect games, positions, analyses schemas once ---
    games_cols = await _games_table_columns(db_path)
    games_notnull = {row[1] for row in games_cols if row[3] == 1}

    try:
        positions_cols = await _positions_table_columns(db_path)
    except Exception as exc:
        logger.warning("pgn-import %s: positions table missing: %s", import_id, exc)
        positions_cols = []
    positions_notnull = {row[1] for row in positions_cols if row[3] == 1}

    try:
        analyses_cols = await _analyses_table_columns(db_path)
    except Exception as exc:
        logger.warning("pgn-import %s: analyses table missing: %s", import_id, exc)
        analyses_cols = []
    analyses_notnull = {row[1] for row in analyses_cols if row[3] == 1}

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

        # Per-game raw PGN block (best-effort: i-th block if available, else full text).
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
        # ====================================================================
        # 1) Insert games (one DB connection, single commit at the end).
        # ====================================================================
        for i, _game, row in parsed_games:
            game_id = row["id"]

            values: dict[str, object] = dict(row)
            for col in games_notnull:
                if col in values:
                    continue
                default = next((c[4] for c in games_cols if c[1] == col), None)
                if default is not None and default != "":
                    continue  # column has a SQL default; SQLite will fill it
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

            # ================================================================
            # 2) Insert positions (one per mainline ply).
            # ================================================================
            positions = _walk_game(_game)

            # Backfill NOT NULL columns with safe defaults.
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

            # ================================================================
            # 3) Synchronously analyze positions 0..N (capped by max_plies).
            # ================================================================
            if pool is None:
                analysis_failed_count += min(len(positions), body.max_plies + 1)
                logger.warning(
                    "pgn-import %s: engine_pool not initialized; skipping analysis for %s",
                    import_id, game_id,
                )
                continue

            try:
                # Import lazily so the engine protocol types don't have to be
                # importable at module load time.
                from chess_coach.protocol_types.analysis import AnalysisRequest
            except Exception as exc:
                analysis_failed_count += min(len(positions), body.max_plies + 1)
                logger.warning(
                    "pgn-import %s: AnalysisRequest import failed for %s: %s",
                    import_id, game_id, exc,
                )
                continue

            for ply, fen, _move_uci, _move_san in positions[: body.max_plies + 1]:
                position_id = f"{game_id}:{ply}"
                ok = await _analyze_position(
                    db,
                    pool,
                    AnalysisRequest,
                    import_id,
                    position_id,
                    fen,
                    body.depth,
                    analyses_cols,
                    analyses_notnull,
                )
                if ok:
                    analyzed_count += 1
                else:
                    analysis_failed_count += 1

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
