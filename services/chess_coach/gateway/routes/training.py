"""Training / spaced-repetition routes.

Cards are managed by a fixed "default" player name for the single-user
Phase 2.  The queue endpoint returns due cards ordered by FSRS priority;
the review endpoint updates FSRS parameters after a learner response.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from chess_coach.errors.codes import ErrorCode
from chess_coach.gateway.auth import require_bearer

router = APIRouter(tags=["training"], dependencies=[Depends(require_bearer)])

_DEFAULT_PLAYER = "default"

# ── PGN header extraction helpers ──────────────────────────────────────


def _extract_pgn_header(pgn_raw: str, tag: str) -> str | None:
    """Extract a PGN header value like [ECO "B10"] -> "B10"."""
    m = re.search(rf'\[{tag} "([^"]+)"\]', pgn_raw)
    return m.group(1) if m else None


# ── Pydantic models ────────────────────────────────────────────────────

class CardOut(BaseModel):
    id: str
    card_type: str
    reference_id: str
    fen: str | None = None
    move_san: str | None = None
    game_id: str | None = None
    white: str | None = None
    black: str | None = None
    eco: str | None = None
    opening: str | None = None
    stability: float
    difficulty: float
    retrievability: float
    reviews: int
    lapses: int
    due: str
    last_review: str | None = None


class QueueResponse(BaseModel):
    due_count: int
    cards: list[CardOut]


class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=4)


class ReviewResponse(BaseModel):
    id: str
    new_stability: float
    new_difficulty: float
    new_retrievability: float
    new_reviews: int
    new_due: str


class SeedRequest(BaseModel):
    player: str = "default"


# ── FSRS-5 simplified ──────────────────────────────────────────────────

def _fsrs_next(
    rating: int,
    stability: float,
    difficulty: float,
    retrievability: float,
    reviews: int,
) -> tuple[float, float, float, str]:
    """Simplified FSRS-5 update — scaffolding for Phase 2."""
    factor = {1: 0.6, 2: 0.8, 3: 1.0, 4: 1.3}[rating]
    new_stability = max(0.1, stability * factor)
    new_difficulty = max(1.0, min(10.0, difficulty + (5 - rating) * 0.5))
    new_retrievability = min(1.0, retrievability + 0.15 * (rating - 2))
    interval_days = int(new_stability * 1.5)
    due_dt = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=interval_days)
    return new_stability, new_difficulty, new_retrievability, due_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Routes ─────────────────────────────────────────────────────────────

@router.get("/v1/training/queue/{player}", response_model=QueueResponse)
async def get_queue(player: str, request: Request, limit: int = 20):
    """Return up to limit due training cards for player.
    When player='default' (no specific player on the Windows host),
    aggregate due cards across ALL players."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row

        # SQL: JOIN with games to get player names; ECO/opening done in Python
        base_sql = (
            "SELECT tc.id, tc.card_type, tc.reference_id, "
            "g.id AS game_id, "
            "g.white, g.black, "
            "g.pgn_raw, "
            "tc.stability, tc.difficulty, "
            "tc.retrievability, tc.reviews, tc.lapses, tc.due, tc.last_review "
            "FROM training_cards tc "
            "LEFT JOIN games g ON g.id = substr(tc.reference_id, 1, instr(tc.reference_id, ':')"
            "  - 1)"
        )
        count_sql = "SELECT COUNT(*) FROM training_cards tc"
        due_clause = " tc.due <= strftime('%Y-%m-%dT%H:%M:%fZ','now')"

        if player and player != 'default':
            where = f"WHERE tc.player_name = ? AND{due_clause}"
            params = (player, limit)
        else:
            where = f"WHERE{due_clause}"
            params = (limit,)

        # Queue query
        cur = await db.execute(f"{base_sql} {where} ORDER BY due ASC, stability ASC LIMIT ?", params)
        rows = [dict(r) for r in await cur.fetchall()]

        # Enrich with ECO/opening extracted from PGN
        cards = []
        for r in rows:
            pgn_raw = r.pop('pgn_raw', None)
            if pgn_raw:
                r['eco'] = _extract_pgn_header(pgn_raw, 'ECO')
                r['opening'] = _extract_pgn_header(pgn_raw, 'Opening')
            else:
                r['eco'] = None
                r['opening'] = None
            cards.append(CardOut(**r))

        # Count query
        if player and player != 'default':
            count_params = (player,)
        else:
            count_params = ()
        cur2 = await db.execute(f"{count_sql} {where}", count_params)
        due_count = (await cur2.fetchone())[0]

    return QueueResponse(due_count=due_count, cards=cards)


@router.post("/v1/training/review/{card_id}", response_model=ReviewResponse)
async def review_card(card_id: str, body: ReviewRequest, request: Request):
    """Submit a review rating; update FSRS parameters."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT stability, difficulty, retrievability, reviews, lapses "
            "FROM training_cards WHERE id = ?", (card_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": ErrorCode.NOT_FOUND.value, "message": f"Card {card_id} not found"},
            )
        s, d, r, revs, _ = row["stability"], row["difficulty"], row["retrievability"], row["reviews"], row["lapses"]
        ns, nd, nr, ndue = _fsrs_next(body.rating, s, d, r, revs)
        nrev = revs + 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        await db.execute(
            "UPDATE training_cards SET stability=?, difficulty=?, retrievability=?, "
            "reviews=?, last_review=?, due=?, updated_at=? WHERE id=?",
            (ns, nd, nr, nrev, now, ndue, now, card_id),
        )
        await db.commit()
    return ReviewResponse(id=card_id, new_stability=ns, new_difficulty=nd, new_retrievability=nr, new_reviews=nrev, new_due=ndue)


@router.post("/v1/training/seed-from-blunders")
async def seed_from_blunders(body: SeedRequest, request: Request):
    """Create training cards from blunder positions."""
    settings = request.app.state.gateway.settings
    created = 0
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        rows = await db.execute_fetchall(
            "SELECT DISTINCT p.id AS pos_id, p.fen "
            "FROM positions p "
            "JOIN analyses a ON a.position_id = p.id "
            "WHERE (a.classification LIKE '%blunder%' OR ABS(COALESCE(a.cp_delta,0)) > 150) "
            "AND p.id NOT IN (SELECT reference_id FROM training_cards WHERE card_type='position' AND player_name=?) "
            "LIMIT 100",
            (body.player,),
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        for pos_id, _fen in rows:
            cid = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO training_cards (id, player_name, card_type, reference_id, due, created_at, updated_at) "
                "VALUES (?, ?, 'position', ?, ?, ?, ?)",
                (cid, body.player, pos_id, now, now, now),
            )
            created += 1
        await db.commit()
    return {"data": {"created": created}}
