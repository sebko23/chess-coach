"""Lichess import route.

Protocol §4.x:
  POST /v1/import/lichess — fetch games from Lichess API by username and import
  into the local games/positions DB.

Uses the public Lichess API (no OAuth required for public game export at
https://lichess.org/api#tag/Games/operation/apiGamesUser).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import aiohttp
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import chess.pgn

from chess_coach.errors.codes import ErrorCode
from chess_coach.gateway.auth import require_bearer

_log = logging.getLogger(__name__)

router = APIRouter(tags=["lichess"], dependencies=[Depends(require_bearer)])

LICHESS_API = "https://lichess.org/api/games/user/{username}"


class LichessImportRequest(BaseModel):
    username: str
    max_games: int = Field(default=50, ge=1, le=500)
    perf_type: str | None = None
    rated: bool | None = None


class LichessImportResult(BaseModel):
    username: str
    games_fetched: int
    imported_count: int
    errors: list[str]


async def _fetch_games_ndjson(
    username: str, max_games: int,
    perf_type: str | None, rated: bool | None,
) -> list[dict]:
    """Fetch game objects from the Lichess API as NDJSON."""
    params: dict[str, str | int] = {
        "max": max_games,
        "pgn_in_json": "true",
        "moves": "true",
        "tags": "true",
        "opening": "true",
        "clocks": "false",
        "evals": "false",
    }
    if perf_type:
        params["perfType"] = perf_type
    if rated is not None:
        params["rated"] = str(rated).lower()

    url = LICHESS_API.format(username=username)
    headers = {"Accept": "application/x-ndjson"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 404:
                raise HTTPException(
                    404,
                    detail={
                        "code": ErrorCode.NOT_FOUND.value,
                        "message": f"Lichess user '{username}' not found",
                    },
                )
            if resp.status == 429:
                raise HTTPException(
                    429,
                    detail={
                        "code": ErrorCode.RATE_LIMITED.value,
                        "message": "Lichess API rate limit hit; try again later",
                    },
                )
            if resp.status != 200:
                body = await resp.text()
                raise HTTPException(
                    resp.status,
                    detail={
                        "code": ErrorCode.UPSTREAM_ERROR.value,
                        "message": f"Lichess API error: {body[:200]}",
                    },
                )

            text = await resp.text()
    objs: list[dict] = []
    for line in text.split(chr(10)):
        line = line.strip()
        if line:
            try:
                objs.append(json.loads(line))
            except json.JSONDecodeError:
                _log.warning("Skipping unparseable Lichess line: %.80s", line)
    return objs


def _parse_game(obj: dict) -> tuple[str, dict, str] | None:
    """Parse a Lichess NDJSON game object."""
    pgn_raw = obj.get("pgn", "")
    if not pgn_raw:
        return None

    game_id = obj.get("id", str(uuid.uuid4()))
    players = obj.get("players", {})
    white_user = players.get("white", {}).get("user", {}).get("name")
    black_user = players.get("black", {}).get("user", {}).get("name")

    ts = obj.get("createdAt") or obj.get("lastMoveAt")
    date_str: str | None = None
    if ts:
        try:
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    perf = obj.get("perf", "game")
    game = {
        "id": game_id,
        "white": white_user,
        "black": black_user,
        "result": obj.get("winner"),
        "date": date_str,
        "event": obj.get("event") or f"Lichess {perf}",
        "site": f"https://lichess.org/{game_id}",
    }
    return game_id, game, pgn_raw


async def _insert_game(
    db: aiosqlite.Connection, game: dict, pgn_raw: str,
):
    """Insert a single game and all its positions into the DB."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    await db.execute(
        """INSERT OR IGNORE INTO games
           (id, pgn_raw, white, black, date, event, site, result,
            import_status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            game["id"], pgn_raw,
            game.get("white"), game.get("black"),
            game.get("date"), game.get("event"), game.get("site"), game.get("result"),
            now, now,
        ),
    )

    import io
    pgn_io = io.StringIO(pgn_raw)
    try:
        parsed = chess.pgn.read_game(pgn_io)
    except Exception:
        return
    if not parsed:
        return

    board = parsed.board()
    await db.execute(
        "INSERT OR IGNORE INTO positions (id, game_id, fen, ply, is_mainline) VALUES (?, ?, ?, 0, 1)",
        (f"{game['id']}:0", game["id"], board.fen()),
    )
    for ply, move in enumerate(parsed.mainline_moves(), 1):
        board.push(move)
        move_san = board.san(move)
        await db.execute(
            "INSERT OR IGNORE INTO positions (id, game_id, fen, move_uci, move_san, ply, is_mainline) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (f"{game['id']}:{ply}", game["id"], board.fen(), move.uci(), move_san, ply),
        )


@router.post("/v1/import/lichess", response_model=LichessImportResult)
async def import_lichess(body: LichessImportRequest, request: Request):
    """Fetch games from Lichess and import into the local DB."""
    settings = request.app.state.gateway.settings
    games_fetched = 0
    imported_count = 0
    errors: list[str] = []

    try:
        objs = await _fetch_games_ndjson(
            body.username, body.max_games, body.perf_type, body.rated,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            502,
            detail={
                "code": ErrorCode.UPSTREAM_ERROR.value,
                "message": f"Failed to fetch from Lichess: {exc}",
            },
        )

    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        for obj in objs:
            games_fetched += 1
            result = _parse_game(obj)
            if result is None:
                errors.append(f"Game #{games_fetched}: no PGN data")
                continue
            gid, game_data, pgn_raw = result
            try:
                await _insert_game(db, game_data, pgn_raw)
                imported_count += 1
            except Exception as exc:
                errors.append(f"Game {gid}: {exc}")
        await db.commit()

    return LichessImportResult(
        username=body.username,
        games_fetched=games_fetched,
        imported_count=imported_count,
        errors=errors,
    )
