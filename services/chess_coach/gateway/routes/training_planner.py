"""Training planner endpoint.

GET /v1/training/schedule/{player}?days=7&daily_minutes=30

Generates a prioritized multi-day study schedule from due training cards.
Prioritises by urgency (low retrievability + high difficulty first),
caps new cards at 30% of daily budget, and balances card types.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Literal

import aiosqlite
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from ..auth import require_bearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/training", tags=["training"])


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


# Average minutes per card by type
MINUTES_PER_CARD: dict[str, float] = {
    "position": 2.0,
    "opening_gap": 1.5,
    "concept": 2.5,
}
DEFAULT_MINUTES = 2.0


class ScheduledCard(BaseModel):
    id: str
    card_type: str
    reference_id: str
    stability: float
    difficulty: float
    retrievability: float
    reviews: int
    lapses: int
    due: str
    priority_score: float
    is_new: bool


class DayPlan(BaseModel):
    day: int
    date: str
    cards: list[ScheduledCard]
    estimated_minutes: float
    new_cards: int
    review_cards: int
    card_type_breakdown: dict[str, int]


class TrainingScheduleResponse(BaseModel):
    player_name: str
    days: int
    daily_minutes: int
    total_cards_scheduled: int
    total_due: int
    schedule: list[DayPlan]


def _priority_score(stability: float, difficulty: float,
                    retrievability: float, days_overdue: float) -> float:
    """Higher score = more urgent to review.

    Formula weights:
    - Low retrievability (forgetting risk) — most important
    - High difficulty (harder to relearn) — secondary
    - Days overdue — tertiary
    - Low stability (short-term memory) — minor factor
    """
    forgetting_risk = max(0.0, 1.0 - retrievability)
    overdue_factor = min(days_overdue / 7.0, 1.0)  # cap at 7 days
    difficulty_factor = difficulty / 10.0
    stability_factor = max(0.0, 1.0 - (stability / 10.0))
    return (
        forgetting_risk * 0.5 +
        overdue_factor * 0.25 +
        difficulty_factor * 0.15 +
        stability_factor * 0.10
    )


@router.get(
    "/schedule/{player}",
    response_model=TrainingScheduleResponse,
    dependencies=[Depends(require_bearer)],
)
async def get_training_schedule(
    player: str,
    days: int = Query(7, ge=1, le=30),
    daily_minutes: int = Query(30, ge=5, le=180),
    db_path: str = Depends(_db_path),
) -> TrainingScheduleResponse:
    """Generate a prioritized multi-day training schedule."""

    now = datetime.now(timezone.utc)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Resolve default player
        if player == "default":
            row = await db.execute_fetchall(
                """SELECT white AS player, COUNT(*) as cnt FROM games
                   WHERE white != '?' GROUP BY white
                   UNION ALL
                   SELECT black AS player, COUNT(*) as cnt FROM games
                   WHERE black != '?' GROUP BY black
                   ORDER BY cnt DESC LIMIT 1"""
            )
            resolved = row[0]["player"] if row else "default"
        else:
            resolved = player

        # Fetch all due cards within the planning window
        window_end = now + timedelta(days=days)
        if resolved == "default":
            cards_raw = await db.execute_fetchall(
                """SELECT id, card_type, reference_id, stability, difficulty,
                          retrievability, reviews, lapses, due, last_review
                   FROM training_cards
                   WHERE due <= ?
                   ORDER BY due ASC""",
                (window_end.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",),
            )
        else:
            cards_raw = await db.execute_fetchall(
                """SELECT id, card_type, reference_id, stability, difficulty,
                          retrievability, reviews, lapses, due, last_review
                   FROM training_cards
                   WHERE player_name = ? AND due <= ?
                   ORDER BY due ASC""",
                (resolved, window_end.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"),
            )

    total_due = len(cards_raw)

    # Score and sort all cards
    scored = []
    for c in cards_raw:
        try:
            due_dt = datetime.fromisoformat(c["due"].replace("Z", "+00:00"))
        except Exception:
            due_dt = now
        days_overdue = max(0.0, (now - due_dt).total_seconds() / 86400)
        is_new = c["reviews"] == 0
        score = _priority_score(
            c["stability"], c["difficulty"],
            c["retrievability"], days_overdue
        )
        scored.append({
            "id": c["id"],
            "card_type": c["card_type"] or "position",
            "reference_id": c["reference_id"],
            "stability": c["stability"],
            "difficulty": c["difficulty"],
            "retrievability": c["retrievability"],
            "reviews": c["reviews"],
            "lapses": c["lapses"],
            "due": c["due"],
            "priority_score": round(score, 4),
            "is_new": is_new,
        })

    # Sort: highest priority first
    scored.sort(key=lambda x: x["priority_score"], reverse=True)

    # Build daily schedule
    schedule: list[DayPlan] = []
    card_idx = 0

    for day_num in range(1, days + 1):
        day_date = (now + timedelta(days=day_num - 1)).strftime("%Y-%m-%d")
        day_cards: list[ScheduledCard] = []
        day_minutes = 0.0
        new_card_budget = int(daily_minutes * 0.30 / DEFAULT_MINUTES)
        new_cards_added = 0
        type_counts: dict[str, int] = {}

        # Pass 1: add review cards (not new)
        temp_idx = card_idx
        while temp_idx < len(scored) and day_minutes < daily_minutes:
            c = scored[temp_idx]
            if not c["is_new"]:
                mins = MINUTES_PER_CARD.get(c["card_type"], DEFAULT_MINUTES)
                if day_minutes + mins <= daily_minutes:
                    day_cards.append(ScheduledCard(**c))
                    day_minutes += mins
                    type_counts[c["card_type"]] = type_counts.get(c["card_type"], 0) + 1
            temp_idx += 1

        # Pass 2: fill remaining time with new cards
        temp_idx = card_idx
        while temp_idx < len(scored) and day_minutes < daily_minutes and new_cards_added < new_card_budget:
            c = scored[temp_idx]
            if c["is_new"] and c not in [dc.model_dump() for dc in day_cards]:
                mins = MINUTES_PER_CARD.get(c["card_type"], DEFAULT_MINUTES)
                if day_minutes + mins <= daily_minutes:
                    day_cards.append(ScheduledCard(**c))
                    day_minutes += mins
                    new_cards_added += 1
                    type_counts[c["card_type"]] = type_counts.get(c["card_type"], 0) + 1
            temp_idx += 1

        # Advance card_idx past cards assigned to this day
        assigned_ids = {c.id for c in day_cards}
        while card_idx < len(scored) and scored[card_idx]["id"] in assigned_ids:
            card_idx += 1

        schedule.append(DayPlan(
            day=day_num,
            date=day_date,
            cards=day_cards,
            estimated_minutes=round(day_minutes, 1),
            new_cards=new_cards_added,
            review_cards=len(day_cards) - new_cards_added,
            card_type_breakdown=type_counts,
        ))

    total_scheduled = sum(len(d.cards) for d in schedule)

    return TrainingScheduleResponse(
        player_name=resolved,
        days=days,
        daily_minutes=daily_minutes,
        total_cards_scheduled=total_scheduled,
        total_due=total_due,
        schedule=schedule,
    )
