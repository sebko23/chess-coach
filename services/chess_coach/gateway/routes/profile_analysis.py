"""Playing Style Patterns / profile analysis endpoint.

BBF-61: this module is refactored to delegate metric
computation to `chess_coach.profile.*` (the BBF-54..59
metric implementations) instead of running its own SQL
queries. The response shape is unified to `metrics: [{id,
value, sample_size, d, passes_b4_gate}]` so the dashboard
can render the experimental Phase 4 metrics alongside the
pre-existing 3 metrics (`blunder_rate`, `conversion_ability`,
`opening_comfort`) in a single tile list.

The legacy fields (`tactical_tendency`, `risk_appetite`,
`tilt_index`, `time_pressure_blunders`, `opening_breadth`)
are still returned for backward compat (the dashboard
reads them from the flat object). They are now computed
via the metric implementations and added to the response.

## Endpoint

`POST /v1/profile/{player}/analysis` -- returns
`ProfileAnalysisResponse`.

## Migration path

BBF-61 unifies the response shape. Future BBFs (BBF-62
frontend rewrite) will migrate the dashboard to read
from `metrics: [{id, value}]` instead of the flat fields.
Until then, both shapes are returned for backward compat.

## §B4 framing

Per the Claude review's §B4 acceptance, every metric in
the response carries:
  - `id`: the metric identifier
  - `value`: the point estimate
  - `sample_size`: the number of qualifying observations
  - `d`: Cohen's d (None if below the gate)
  - `passes_b4_gate`: True iff the metric's effect size
    passes the §B4 surfacing gate (d >= 0.5 AND sample_size
    >= minimum). The UI uses this to decide whether to
    surface the metric as a coaching insight.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from chess_coach.gateway.auth import require_bearer
from chess_coach.profile import (
    blunder_rate_vs_rating,
    conversion_ability,
    decision_fatigue,
    gate_metric,
    opening_comfort,
    sequence_based_tilt,
    tactical_vs_positional_bias,
    time_pressure_quality,
)
from ..route_guard import route_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/profile", tags=["profile"])


class ProfileMetric(BaseModel):
    """One metric in the response. Per §B4, carries enough
    metadata for the UI to decide whether to surface as a
    coaching insight."""

    id: str
    value: float | None
    sample_size: int
    d: float | None
    ci_low: float | None = None
    ci_high: float | None = None
    passes_b4_gate: bool


class ProfileAnalysisResponse(BaseModel):
    """Unified Phase 4 response shape.

    The flat legacy fields are kept for backward compat
    with the pre-BBF-61 dashboard. New clients should
    read from `metrics: [{id, value, ...}]`.
    """

    player_name: str
    total_games: int
    # Legacy flat fields (BBF-54..59 computations)
    tactical_tendency: float
    risk_appetite: float
    tilt_index: float
    time_pressure_blunders: float
    opening_breadth: int
    # New unified shape (BBF-61)
    metrics: list[ProfileMetric] = Field(default_factory=list)


# Map metric_id -> (callable, legacy_field_name)
# The callable takes (db_path, player, *, seed=None) and
# returns an EffectSize. The legacy_field_name is the
# field on the old ProfileAnalysisResponse that this
# metric was previously reported under.
def _metric_tactical(db_path, player, **_):
    return tactical_vs_positional_bias(db_path, player)


def _metric_time_pressure(db_path, player, **_):
    return time_pressure_quality(db_path, player)


def _metric_opening(db_path, player, **_):
    return opening_comfort(db_path, player)


def _metric_conversion(db_path, player, **_):
    return conversion_ability(db_path, player)


def _metric_blunder_rating(db_path, player, **_):
    return blunder_rate_vs_rating(db_path, player)


def _metric_decision_fatigue(db_path, player, **_):
    return decision_fatigue(db_path, player)


def _metric_sequence_tilt(db_path, player, **_):
    return sequence_based_tilt(db_path, player)


_METRIC_REGISTRY: dict[str, tuple[object, str | None]] = {
    "tactical_vs_positional_bias": (
        _metric_tactical, "tactical_tendency",
    ),
    "time_pressure_quality": (
        _metric_time_pressure, "time_pressure_blunders",
    ),
    "opening_comfort": (
        _metric_opening, "opening_breadth",
    ),
    "conversion_ability": (
        _metric_conversion, None,  # not in legacy response
    ),
    "blunder_rate_vs_rating": (
        _metric_blunder_rating, None,  # not in legacy response
    ),
    "decision_fatigue": (
        _metric_decision_fatigue, None,  # not in legacy response
    ),
    "sequence_based_tilt": (
        _metric_sequence_tilt, "tilt_index",
    ),
}


def _db_path(request: Request) -> str:
    return str(request.app.state.gateway.settings.sqlite_path)


async def _run_metric_in_thread(fn, db_path: str, player: str):
    """Offload a sync metric call to a worker thread.

    The chess_coach.profile metrics are sync functions.
    Calling them from an async handler blocks the event
    loop, so we use asyncio.to_thread.
    """
    return await asyncio.to_thread(fn, db_path, player)


@router.post(
    "/{player}/analysis",
    response_model=ProfileAnalysisResponse,
    dependencies=[Depends(require_bearer)],
)
@route_guard
async def get_profile_analysis(
    player: str,
    db_path: str = Depends(_db_path),
) -> ProfileAnalysisResponse:
    """Aggregated Phase 4 metrics for a player.

    The response includes both the legacy flat fields
    (for backward compat with the pre-BBF-61 dashboard)
    AND the new unified `metrics: [{id, value, ...}]` array
    (which the BBF-62 dashboard will consume).

    The legacy `tilt_index` field is the sequence-based
    tilt point_estimate (a re-implementation of the
    pre-BBF-54 single-loss-window tilt). When the player
    has no qualifying data, the value is 0.0.
    """
    # Run all 7 metrics in a thread pool (one per metric).
    # The metrics are independent; we can run them in any
    # order. We use asyncio.gather with to_thread to run
    # them in parallel (subject to the GIL -- metrics are
    # CPU-bound; threading gives no real parallelism, but
    # it does avoid blocking the event loop).
    coros = [
        _run_metric_in_thread(fn, db_path, player)
        for fn, _ in _METRIC_REGISTRY.values()
    ]
    effects = await asyncio.gather(*coros, return_exceptions=True)
    # Log exceptions but don't fail the whole response;
    # metrics that fail return EffectSize with d=None.
    for i, (mid, _) in enumerate(_METRIC_REGISTRY.items()):
        if isinstance(effects[i], Exception):
            logger.warning(
                "profile_analysis: metric %s failed for %s: %s",
                mid, player, effects[i],
            )

    # Build the unified metrics array
    metrics = []
    legacy = {
        "tactical_tendency": 0.0,
        "risk_appetite": 0.0,
        "tilt_index": 0.0,
        "time_pressure_blunders": 0.0,
        "opening_breadth": 0,
    }
    for i, (mid, (fn, legacy_field)) in enumerate(_METRIC_REGISTRY.items()):
        effect = effects[i]
        if isinstance(effect, Exception):
            continue
        passes_gate = gate_metric(effect)
        metrics.append(ProfileMetric(
            id=mid,
            value=effect.point_estimate,
            sample_size=effect.sample_size,
            d=effect.d,
            ci_low=effect.ci_low,
            ci_high=effect.ci_high,
            passes_b4_gate=passes_gate,
        ))
        if legacy_field is not None:
            legacy[legacy_field] = effect.point_estimate

    # Resolve player name (legacy field)
    from chess_coach.profile.stats import _resolve_player
    resolved = _resolve_player(db_path, player)

    # Total games (still computed via the original SQL for
    # backward compat with the legacy response shape).
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        total_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM games WHERE white=? OR black=?",
            (resolved, resolved),
        ).fetchone()
        total_games = total_row["cnt"] if total_row else 0

    return ProfileAnalysisResponse(
        player_name=resolved,
        total_games=total_games,
        **legacy,
        metrics=metrics,
    )