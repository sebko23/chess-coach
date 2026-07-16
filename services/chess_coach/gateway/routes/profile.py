"""Player profile / statistics routes."""
from __future__ import annotations

import asyncio
import logging

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from chess_coach.gateway.auth import require_bearer
from chess_coach.profile import (
    EffectSize,
    blunder_rate_vs_rating,
    cluster_archetypes,
    conversion_ability,
    decision_fatigue,
    opening_comfort,
    sequence_based_tilt,
    tactical_vs_positional_bias,
    time_pressure_quality,
    ArchetypeAssignment,
)
from ..route_guard import route_guard

logger = logging.getLogger(__name__)
router = APIRouter(tags=["profile"], dependencies=[Depends(require_bearer)])


class ProfileStats(BaseModel):
    player_name: str
    total_games: int
    wins: int
    losses: int
    draws: int
    total_analyses: int
    blunder_count: int
    training_cards_due: int


@router.get("/v1/profile/{player}", response_model=ProfileStats)
@route_guard
async def get_profile(player: str, request: Request):
    """Aggregated statistics for a player."""
    settings = request.app.state.gateway.settings
    async with aiosqlite.connect(str(settings.sqlite_path)) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            "SELECT COUNT(*) FROM games WHERE white = ? OR black = ?", (player, player)
        )
        total_games = (await cur.fetchone())[0]

        result_rows = await db.execute_fetchall(
            "SELECT result, COUNT(*) as cnt FROM games "
            "WHERE (white = ? OR black = ?) GROUP BY result",
            (player, player),
        )
        wins = sum(r[1] for r in result_rows if r[0] == "1-0")
        losses = sum(r[1] for r in result_rows if r[0] == "0-1")
        draws = sum(r[1] for r in result_rows if r[0] == "1/2-1/2")

        cur = await db.execute("SELECT COUNT(*) FROM analyses")
        total_analyses = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM analyses "
            "WHERE classification LIKE '%blunder%' OR ABS(COALESCE(cp_delta,0)) > 150"
        )
        blunder_count = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM training_cards "
            "WHERE player_name = ? AND due <= strftime('%Y-%m-%dT%H:%M:%fZ','now')",
            (player,),
        )
        training_cards_due = (await cur.fetchone())[0]

    return ProfileStats(
        player_name=player,
        total_games=total_games,
        wins=wins,
        losses=losses,
        draws=draws,
        total_analyses=total_analyses,
        blunder_count=blunder_count,
        training_cards_due=training_cards_due,
    )


# --- BBF-60: /v1/profile/{player}/explain/{metric} ---
# Per §B4 rule 4 of docs/13_review_response/response-to-review.md,
# every metric dashboard tile ships with an "Explain" view that
# shows methodology + raw inputs + intermediate values. This
# endpoint is the API surface for that view.
#
# The response shape is the same for all 6 metrics + the
# archetype clusterer, modulo a few metric-specific fields.
# The methodology text is loaded from a per-metric section
# of docs/15_methodology/profile-metrics-v1.md (BBF-60
# introduces the doc).

class MetricExplainResponse(BaseModel):
    """§B4 rule 4: methodology + raw inputs + intermediate values.

    Fields:
      player_name: The player this explanation is for.
      metric_id: The metric name (e.g.
          "tactical_vs_positional_bias"). One of the 6
          metrics + "archetypes" + "sequence_based_tilt".
      effect: The EffectSize result from running the
          metric. shape: (point_estimate, d, ci_low,
          ci_high, sample_size, null_value). For the
          archetype clusterer, this carries the
          confidence in [0, 1] (not a per-metric
          EffectSize).
      passes_b4_gate: True iff gate_metric() returns
          True. For the archetype clusterer, this is
          True iff confidence > 0.4.
      methodology: The full text of the metric's
          methodology section (from
          docs/15_methodology/profile-metrics-v1.md).
      raw_inputs: A dict of the raw inputs to the
          metric (player name, db path, SQL filter
          parameters). The keys are metric-specific.
      intermediate_values: A dict of intermediate
          values computed during the metric's run
          (e.g. for tactical_vs_positional_bias:
          {'opportunities': 50, 'taken': 31, 'rate': 0.62}).
      caveats: A list of strings describing caveats
          (e.g. "Sample size is below the §B4
          threshold; the metric's point estimate is
          not surfaced as a coaching insight").
    """

    player_name: str
    metric_id: str
    effect: dict
    passes_b4_gate: bool
    methodology: str
    raw_inputs: dict
    intermediate_values: dict
    caveats: list[str] = Field(default_factory=list)


# Map metric_id -> (callable, methodology_section_name)
# The callable takes (db_path, player, **kwargs) and returns
# an EffectSize (or ArchetypeAssignment for "archetypes").
# The methodology_section_name is the H2 heading in
# docs/15_methodology/profile-metrics-v1.md for this
# metric (used to slice the doc into per-metric sections).
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

_METRIC_REGISTRY: dict[str, tuple[object, str]] = {
    "tactical_vs_positional_bias": (
        _metric_tactical,
        "tactical_vs_positional_bias",
    ),
    "time_pressure_quality": (
        _metric_time_pressure,
        "time_pressure_quality",
    ),
    "opening_comfort": (
        _metric_opening,
        "opening_comfort",
    ),
    "conversion_ability": (
        _metric_conversion,
        "conversion_ability",
    ),
    "blunder_rate_vs_rating": (
        _metric_blunder_rating,
        "blunder_rate_vs_rating",
    ),
    "decision_fatigue": (
        _metric_decision_fatigue,
        "decision_fatigue",
    ),
    "sequence_based_tilt": (
        _metric_sequence_tilt,
        "sequence_based_tilt",
    ),
}


def _load_methodology_for(metric_id: str) -> str:
    """Load the methodology section for a given metric.

    Reads `docs/15_methodology/profile-metrics-v1.md` from
    the repo root and slices out the section for the
    given metric. Returns a generic fallback string if
    the section isn't found (so the endpoint never
    fails because of a missing doc).

    The doc is loaded once per process and cached.
    """
    if not hasattr(_load_methodology_for, "_cache"):
        _load_methodology_for._cache = {}  # type: ignore[attr-defined]
    cache: dict = _load_methodology_for._cache  # type: ignore[attr-defined]
    if metric_id in cache:
        return cache[metric_id]
    # Locate the doc file. The path is resolved relative
    # to the package root (services/chess_coach/gateway/
    # routes/profile.py -> 4 levels up to the repo root).
    from pathlib import Path
    doc_path = (
        Path(__file__).resolve().parents[3]
        / "docs" / "15_methodology" / "profile-metrics-v1.md"
    )
    if not doc_path.is_file():
        cache[metric_id] = (
            f"Methodology doc not found at {doc_path}. "
            f"See docs/15_methodology/profile-metrics-v1.md."
        )
        return cache[metric_id]
    text = doc_path.read_text(encoding="utf-8")
    # Slice: the section for `metric_id` runs from
    # "## <metric_id>" to the next "## " heading.
    section_start = f"## {metric_id}"
    if section_start not in text:
        cache[metric_id] = (
            f"Methodology section for {metric_id!r} not "
            f"found in {doc_path}."
        )
        return cache[metric_id]
    start = text.index(section_start)
    # Find the next H2 after start
    rest = text[start + len(section_start):]
    next_h2 = rest.find("\n## ")
    if next_h2 == -1:
        section_text = rest
    else:
        section_text = rest[:next_h2]
    cache[metric_id] = section_text.strip()
    return cache[metric_id]


def _effect_to_dict(effect: EffectSize) -> dict:
    """Serialize an EffectSize dataclass to a JSON-friendly dict.

    The endpoint returns a dict rather than the Pydantic
    model directly so the response shape is stable
    regardless of the EffectSize dataclass evolution
    (BBF-56 added point_estimate; future BBFs may add
    more fields -- a Pydantic model would break).
    """
    return {
        "point_estimate": effect.point_estimate,
        "d": effect.d,
        "ci_low": effect.ci_low,
        "ci_high": effect.ci_high,
        "sample_size": effect.sample_size,
        "null_value": effect.null_value,
    }


def _archetype_to_dict(assignment: ArchetypeAssignment) -> dict:
    """Serialize an ArchetypeAssignment to a dict."""
    return {
        "label": assignment.label,
        "confidence": assignment.confidence,
        "archetype_scores": assignment.archetype_scores,
        "effect_size": _effect_to_dict(assignment.effect_size),
    }


def _gate_passes(effect: EffectSize) -> bool:
    """Return True iff the EffectSize passes the §B4 gate."""
    from chess_coach.profile import gate_metric
    return gate_metric(effect)


async def _run_metric_in_thread(
    fn, db_path: str, player: str
):
    """Run a sync metric function in a worker thread.

    The chess_coach.profile metrics are sync functions.
    Calling them from an async handler blocks the event
    loop, so we offload to a thread. For the small
    metric queries (~50ms) this is fine; for the
    archetype clusterer (which loads the L-2 corpus
    from disk) it's also fine because the load is
    cached after the first call.
    """
    return await asyncio.to_thread(fn, db_path, player)


@router.get(
    "/v1/profile/{player}/explain/{metric_id}",
    response_model=MetricExplainResponse,
)
@route_guard
async def explain_metric(player: str, metric_id: str, request: Request):
    """§B4 rule 4: methodology + raw inputs + intermediate values.

    Returns the EffectSize result + a full methodology
    text + raw inputs + intermediate values for one
    metric. The dashboard's "Explain" view links to
    this endpoint.

    Special case: metric_id == "archetypes" returns the
    ArchetypeAssignment (no EffectSize, just a
    label + confidence + per-archetype scores).
    """
    if metric_id not in _METRIC_REGISTRY and metric_id != "archetypes":
        from starlette.exceptions import HTTPException
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown metric_id {metric_id!r}. "
                f"Known: {sorted(_METRIC_REGISTRY.keys()) + ['archetypes']}"
            ),
        )
    settings = request.app.state.gateway.settings
    db_path = str(settings.sqlite_path)
    methodology = _load_methodology_for(metric_id)
    caveats: list[str] = []
    raw_inputs = {
        "player": player,
        "db_path": db_path,
        "metric_id": metric_id,
    }

    if metric_id == "archetypes":
        # Special case: archetypes clusterer. It takes a
        # metrics dict, not a (db_path, player) pair. We
        # compute the 6 metric values first, then pass
        # them to cluster_archetypes.
        from chess_coach.profile import cluster_archetypes
        metric_values: dict[str, float] = {}
        intermediate: dict = {}
        # Run the 6 metrics (skip sequence_based_tilt --
        # it's a separate dimension, not part of the
        # 6-metric vector). Use the _METRIC_REGISTRY
        # entries directly.
        for mid, (mfn, _) in _METRIC_REGISTRY.items():
            if mid == "sequence_based_tilt":
                continue
            effect = await _run_metric_in_thread(mfn, db_path, player)
            metric_values[mid] = effect.point_estimate
            intermediate[mid] = {
                "point_estimate": effect.point_estimate,
                "d": effect.d,
                "sample_size": effect.sample_size,
            }
        assignment = await asyncio.to_thread(
            cluster_archetypes, metric_values
        )
        raw_inputs["metric_values"] = metric_values
        # Defer to the canonical BBF-65.2 gate field on the assignment.
        # The cluster_archetypes() function (in services/chess_coach/profile/archetypes.py)
        # computes passes_b4_gate correctly per §B4 rules: False for Unknown labels
        # (rule 3: below-threshold MUST NOT surface), otherwise gate_metric(effect)
        # with min_sample_size=1 (cluster assignments are single observations,
        # not 30-datapoint time-series metrics).
        from chess_coach.profile import COHENS_D_THRESHOLD  # used by the §B4 caveat text below
        passes_gate = assignment.passes_b4_gate
        if not passes_gate:
            caveats.append(
                f"Archetype assignment confidence "
                f"{assignment.confidence:.2f} is below the "
                f"§B4 gate ({COHENS_D_THRESHOLD}). Rendered "
                f"as 'Inconclusive' rather than as a coaching "
                f"insight."
            )
        return MetricExplainResponse(
            player_name=player,
            metric_id=metric_id,
            effect=_archetype_to_dict(assignment),
            passes_b4_gate=passes_gate,
            methodology=methodology,
            raw_inputs=raw_inputs,
            intermediate_values=intermediate,
            caveats=caveats,
        )

    fn, section_name = _METRIC_REGISTRY[metric_id]
    effect = await _run_metric_in_thread(fn, db_path, player)
    if not _gate_passes(effect):
        caveats.append(
            f"Effect size d={effect.d} is below the §B4 "
            f"threshold (0.5), or sample_size={effect.sample_size} "
            f"is below the metric's minimum requirement. "
            f"The metric's point estimate is NOT surfaced "
            f"as a coaching insight per §B4 rule 3."
        )
    return MetricExplainResponse(
        player_name=player,
        metric_id=metric_id,
        effect=_effect_to_dict(effect),
        passes_b4_gate=_gate_passes(effect),
        methodology=methodology,
        raw_inputs=raw_inputs,
        intermediate_values={
            "point_estimate": effect.point_estimate,
            "sample_size": effect.sample_size,
            "d": effect.d,
        },
        caveats=caveats,
    )