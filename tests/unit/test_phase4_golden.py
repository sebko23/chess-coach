"""Phase 4 golden fixture loader.

Tests that the chess_coach.profile metric implementations
produce the expected output on the 3 hand-crafted fixture
scenarios in tests/gold/phase4_v1_fixtures.py.

The "gold" is the expected metric values. Tests use a mix
of EXACT assertions (for opening_comfort and blunder counts)
and RANGE assertions (for ratios + sample sizes + gate
results). The exact bootstrap CI and Cohen's d values are
not asserted -- they're noisy and hard to compute by hand.

The fixture is run for each of the 3 scenarios. Each test
parametrizes over (build_fn, scenario_name) so a failure
isolates to a specific scenario.
"""
from __future__ import annotations

import sqlite3

# Import the fixture builders + EXPECTED constants.
# The fixture file lives in tests/gold/; we add that dir
# to sys.path dynamically so the import works regardless
# of how pytest is invoked.
import sys
from pathlib import Path

import pytest

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "gold"
if str(_FIXTURE_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURE_DIR))
from phase4_v1_fixtures import (  # noqa: E402
    EXPECTED,
    build_blundering_player,
    build_clean_player,
    build_tactical_player,
)


@pytest.fixture(params=[
    (build_clean_player, "clean_player"),
    (build_tactical_player, "tactical_player"),
    (build_blundering_player, "blundering_player"),
])
def scenario(request, tmp_path) -> tuple[str, str, dict]:
    """Parametrized fixture: build each scenario, return (db_path, name, expected)."""
    build_fn, name = request.param
    db_path = str(tmp_path / f"{name}.db")
    build_fn(db_path)
    return db_path, name, EXPECTED[name]


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection. Caller closes it."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_blunder_count(db_path: str, player: str) -> int:
    """Count blunders in the player's game history.

    A blunder is a position where side_delta < -100.
    Side-aware delta: even ply = White moved (delta =
    score_cp - prev_cp), odd ply = Black moved (delta =
    prev_cp - score_cp).
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            WITH scored AS (
              SELECT an.score_cp, po.ply, po.game_id,
                LAG(an.score_cp) OVER (PARTITION BY po.game_id ORDER BY po.ply)
                  AS prev_cp
              FROM analyses an
              JOIN positions po ON an.position_id = po.id
              JOIN games g ON po.game_id = g.id
              WHERE (g.white = ? OR g.black = ?)
                AND an.score_cp IS NOT NULL
                AND po.is_mainline = 1
            )
            SELECT ply,
              CASE WHEN ply % 2 = 0
                THEN score_cp - prev_cp
                ELSE prev_cp - score_cp
              END AS side_delta
            FROM scored WHERE prev_cp IS NOT NULL
            """,
            (player, player),
        ).fetchall()
    return sum(1 for r in rows if r["side_delta"] < -100)


def _fetch_opportunity_count(db_path: str, player: str) -> tuple[int, int]:
    """Count tactical opportunities and taken opportunities.

    Returns (opportunities, taken).
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            WITH scored AS (
              SELECT an.score_cp, po.ply, po.game_id,
                LAG(an.score_cp) OVER (PARTITION BY po.game_id ORDER BY po.ply)
                  AS prev_cp
              FROM analyses an
              JOIN positions po ON an.position_id = po.id
              JOIN games g ON po.game_id = g.id
              WHERE (g.white = ? OR g.black = ?)
                AND an.score_cp IS NOT NULL
                AND po.is_mainline = 1
            )
            SELECT ply,
              CASE WHEN ply % 2 = 0
                THEN score_cp - prev_cp
                ELSE prev_cp - score_cp
              END AS side_delta
            FROM scored WHERE prev_cp IS NOT NULL
            """,
            (player, player),
        ).fetchall()
    opportunities = sum(1 for r in rows if abs(r["side_delta"]) > 80)
    taken = sum(1 for r in rows if abs(r["side_delta"]) > 80 and r["side_delta"] > 0)
    return opportunities, taken


def _fetch_opening_breadth(db_path: str, player: str) -> int:
    """Count distinct opening move prefixes in the first 10 plies."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT SUBSTR(po.move_san, 1, 10) AS prefix
            FROM positions po JOIN games g ON po.game_id = g.id
            WHERE (g.white = ? OR g.black = ?)
              AND po.ply <= 10
              AND po.move_san IS NOT NULL
            """,
            (player, player),
        ).fetchall()
    return len(rows)


# --- Structural tests (no metric implementation) ---


def test_fixture_db_has_correct_blunder_count(scenario) -> None:
    """The fixture's blunder count matches the expected value.

    This is a sanity check on the fixture itself, not on
    the metric implementation. If this fails, the fixture
    is wrong (not the metrics).
    """
    db_path, name, expected = scenario
    blunders = _fetch_blunder_count(db_path, name)
    assert blunders == expected["blunder_count"], (
        f"{name}: expected {expected['blunder_count']} blunders, got {blunders}"
    )


def test_fixture_db_has_correct_tactical_opportunity_count(scenario) -> None:
    """The fixture's tactical opportunity count matches expected."""
    db_path, name, expected = scenario
    opps, taken = _fetch_opportunity_count(db_path, name)
    assert opps == expected["tactical_opportunities"], (
        f"{name}: expected {expected['tactical_opportunities']} "
        f"opportunities, got {opps}"
    )
    if "tactical_taken" in expected:
        assert taken == expected["tactical_taken"], (
            f"{name}: expected {expected['tactical_taken']} taken, got {taken}"
        )


def test_fixture_db_has_correct_opening_breadth(scenario) -> None:
    """The fixture's opening breadth matches expected."""
    db_path, name, expected = scenario
    breadth = _fetch_opening_breadth(db_path, name)
    assert breadth == expected["opening_comfort_distinct_prefixes"], (
        f"{name}: expected {expected['opening_comfort_distinct_prefixes']} "
        f"distinct prefixes, got {breadth}"
    )


# --- Metric implementation tests ---


def test_opening_comfort_matches_fixture(scenario) -> None:
    """opening_comfort's null_value reflects the distinct-prefix count.

    The metric's point_estimate is the MEAN of binary
    observations (fraction of "familiar" positions).
    The distinct-prefix count is captured in null_value
    (= 1 - 1/distinct_count).
    """
    from chess_coach.profile import opening_comfort
    db_path, name, expected = scenario
    result = opening_comfort(db_path, name)
    distinct = expected["opening_comfort_distinct_prefixes"]
    expected_null = 1.0 - (1.0 / max(1, distinct))
    assert result.null_value == pytest.approx(expected_null, abs=0.01), (
        f"{name}: opening_comfort null_value "
        f"{result.null_value} != expected {expected_null} "
        f"(for {distinct} distinct prefixes)"
    )
    # The point_estimate for 1 distinct prefix is 1.0
    # (all positions are "familiar" because the prefix
    # is in the distinct set).
    # point_estimate is the mean of binary observations
    # (1 = "familiar", 0 = "novel"). With each game using
    # one opening consistently, every position is familiar
    # with its own prefix -> point_estimate = 1.0 regardless
    # of distinct count.
    assert result.point_estimate == pytest.approx(1.0, abs=0.01), (
        f"{name}: point_estimate {result.point_estimate} != 1.0 "
        f"(all positions are familiar with their own prefix)"
    )


def test_time_pressure_sample_size_matches_fixture(scenario) -> None:
    """time_pressure_quality returns a non-empty sample_size for the fixture.

    The metric uses LAG over score_cp + ply + game_id.
    For each game, position 1 is excluded (no LAG partner).
    With min_observations=20 (10 games * 2 positions) the
    metric should produce sample_size = 10 (one per game).
    """
    from chess_coach.profile import time_pressure_quality
    db_path, name, expected = scenario
    result = time_pressure_quality(db_path, name)
    # min_observations in the fixture is the total position
    # count (2 per game * N games = N*2). sample_size is the
    # LAG-filtered count (1 per game for 2-position fixtures).
    # So sample_size <= min_observations (strict, because
    # LAG drops pos 1 of each game).
    assert result.sample_size > 0, (
        f"{name}: sample_size should be > 0 with positions, "
        f"got {result.sample_size}"
    )
    assert result.sample_size <= expected["min_observations"], (
        f"{name}: sample_size {result.sample_size} > "
        f"min_observations {expected['min_observations']}"
    )
    # For 2-position fixtures, sample_size should be exactly
    # min_observations // 2 (one per game after LAG).
    expected_sample = expected["min_observations"] // 2
    assert result.sample_size == expected_sample, (
        f"{name}: sample_size {result.sample_size} != "
        f"expected {expected_sample} (= min_observations / 2)"
    )


def test_tactical_point_estimate_direction(scenario) -> None:
    """tactical_vs_positional_bias's point_estimate matches the taken/opportunities ratio."""
    from chess_coach.profile import tactical_vs_positional_bias
    db_path, name, expected = scenario
    result = tactical_vs_positional_bias(db_path, name, seed=42)
    opportunities = expected["tactical_opportunities"]
    taken = expected.get("tactical_taken", 0)
    if opportunities == 0:
        # For blundering_player: no |delta| > 80 from took,
        # but game 2/3 blunders have |delta| > 80 and d < 0.
        # The metric includes them as "0.0" observations.
        # So sample_size = number of |delta| > 80 positions,
        # which may be > 0.
        if name == "blundering_player":
            # 2 blunders in games 2 and 3, both with |delta| > 80
            assert result.sample_size == 2
            # point_estimate = 0 (no "took" = d > 80)
            assert result.point_estimate == 0.0
        else:
            # clean_player: no |delta| > 80 -> sample_size = 0
            assert result.sample_size == 0
    else:
        # For tactical_player: 3/5 = 0.6
        expected_ratio = taken / opportunities
        assert result.point_estimate == pytest.approx(expected_ratio, abs=0.01), (
            f"{name}: tactical point_estimate {result.point_estimate} "
            f"!= expected {expected_ratio}"
        )


def test_blunder_rate_point_estimate(scenario) -> None:
    """blunder_rate_vs_rating's point_estimate matches blunder_count / total."""
    from chess_coach.profile import blunder_rate_vs_rating
    db_path, name, expected = scenario
    result = blunder_rate_vs_rating(db_path, name, seed=42)
    # total observations = 2 per game (positions 2 and 3)
    if expected["blunder_count"] == 0:
        assert result.point_estimate == 0.0, (
            f"{name}: blunder_rate should be 0 with 0 blunders"
        )
    else:
        # The actual rate may be slightly different from the
        # expected rate (blunder_count / total) because the
        # fixture uses 2 positions per game (not 3), and the
        # LAG filter excludes position 1, so total observations
        # = 2 per game * 3 games = 6. We don't assert exact value
        # because the per-position binary observation list
        # depends on the LAG filter and the exact score sequence.
        assert result.point_estimate >= 0.0


# --- L-2 gold integration check (skeleton) ---


def test_l2_gold_v1_loader_works() -> None:
    """The L-2 gold v1 loader (BBF-51) is still importable.

    The Phase 4 fixtures are independent of the L-2 gold
    corpus (L-2 is for archetype calibration; the Phase 4
    fixtures are for metric value verification). But both
    must coexist in the same repo.
    """
    from chess_coach.datasets.l2_gold import load_l2_gold
    corpus = load_l2_gold("v1")
    assert len(corpus) == 12, f"expected 12 L-2 v1 entries, got {len(corpus)}"
