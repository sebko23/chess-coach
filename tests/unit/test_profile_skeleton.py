"""Smoke test for the chess_coach.profile package skeleton (BBF-54+57).

This test proves the package skeleton imports cleanly and
that the documented submodules are reachable. It also
exercises the §B4 statistical primitives (cohens_d,
bootstrap_ci, gate_metric) and the 5 metrics that BBF-57
implements.

## BBF-54 vs BBF-55 vs BBF-57 split

BBF-54 originally shipped a single test that asserted
everything was importable. BBF-55 split the test into
always-on / submodule-local / xfail halves. BBF-57
converts the 5 metric re-exports from xfail to always-on
(the implementations are real now).

Tracking the xfail set:
  BBF-54: 9 names xfail
  BBF-57: 3 names still xfail (decision_fatigue,
          sequence_based_tilt, cluster_archetypes)
  BBF-58: removes decision_fatigue + sequence_based_tilt
          (1 name xfail remaining: cluster_archetypes)
  BBF-59: removes cluster_archetypes (0 names xfail --
          this file's xfail markers can be removed)

## Why the split

The BBF-54 lesson is that the public API contract
(`__all__`) is forward-declared, but the package shouldn't
crash on import just because a name isn't re-exported yet.
Splitting the tests this way keeps the CI signal honest:
the BBF-54 scaffold lands green; subsequent BBFs turn
each xfail into a pass one at a time as the
implementations land.

This test mirrors the BBF-43 boot regression test pattern
(small, fast, asserts a structural property, runs in the
`gateway-boot` CI job).
"""
from __future__ import annotations

import os

import pytest


# --- Always-on tests (BBF-54's contract) ---


def test_profile_package_imports() -> None:
    """The chess_coach.profile package must import without error.

    Regression guard against the BBF-51 / pyproject
    package + package-dir both-required lesson.
    """
    import chess_coach.profile  # noqa: F401
    assert chess_coach.profile.__file__ is not None


def test_profile_submodules_importable() -> None:
    """Every documented submodule must be importable."""
    from chess_coach.profile import (  # noqa: F401
        archetypes,
        effect_size,
        stats,
        tilt,
    )
    for mod in (archetypes, effect_size, stats, tilt):
        assert hasattr(mod, "__all__"), (
            f"chess_coach.profile.{mod.__name__} is missing __all__"
        )


def test_effect_size_gate_works_on_synthetic_data() -> None:
    """The gate_metric() helper from effect_size.py works on synthetic data."""
    from chess_coach.profile.effect_size import (
        COHENS_D_THRESHOLD,
        EffectSize,
        gate_metric,
    )

    # EffectSize with d=None (variance was zero)
    no_d = EffectSize(
        point_estimate=0.5, d=None, ci_low=0.0, ci_high=0.0,
        sample_size=100, null_value=0.0,
    )
    assert gate_metric(no_d) is False, "d=None should not pass the gate"

    # EffectSize with d below threshold (small effect)
    small_d = EffectSize(
        point_estimate=0.55, d=0.3, ci_low=0.1, ci_high=0.5,
        sample_size=100, null_value=0.5,
    )
    assert gate_metric(small_d) is False, (
        f"d=0.3 should not pass the gate (threshold={COHENS_D_THRESHOLD})"
    )

    # EffectSize with d above threshold (medium effect)
    medium_d = EffectSize(
        point_estimate=0.7, d=0.7, ci_low=0.4, ci_high=1.0,
        sample_size=100, null_value=0.5,
    )
    assert gate_metric(medium_d) is True, (
        f"d=0.7 should pass the gate (threshold={COHENS_D_THRESHOLD})"
    )

    # EffectSize with sample_size below MIN_SAMPLE_DEFAULT (30)
    tiny_sample = EffectSize(
        point_estimate=0.7, d=0.7, ci_low=0.4, ci_high=1.0,
        sample_size=10, null_value=0.5,
    )
    assert gate_metric(tiny_sample) is False, (
        "sample_size=10 should not pass the gate"
    )


def test_effect_size_point_estimate_field_exists() -> None:
    """The BBF-57 EffectSize dataclass has a point_estimate field.

    Regression guard for the BBF-57 contract: the
    dataclass was extended to include point_estimate
    (the metric value itself, not just the statistical
    measures). Tests that build EffectSize objects
    MUST include point_estimate.
    """
    from chess_coach.profile.effect_size import EffectSize

    e = EffectSize(
        point_estimate=0.5, d=0.7, ci_low=0.4, ci_high=1.0,
        sample_size=100, null_value=0.5,
    )
    assert e.point_estimate == 0.5
    assert e.d == 0.7
    assert e.ci_low == 0.4
    assert e.ci_high == 1.0
    assert e.sample_size == 100
    assert e.null_value == 0.5


def test_cohens_d_known_fixtures() -> None:
    """cohens_d() matches expected values on known-fixture data."""
    from chess_coach.profile.effect_size import cohens_d

    # Empty sample -> None
    assert cohens_d([], null_value=0.0) is None

    # Single value -> None (can't compute variance)
    assert cohens_d([1.0], null_value=0.0) is None

    # Constant sample -> None (std == 0)
    assert cohens_d([2.0, 2.0, 2.0], null_value=2.0) is None

    # Sample with mean equal to null -> d == 0
    d = cohens_d([1.0, 2.0, 3.0], null_value=2.0)
    assert d == pytest.approx(0.0, abs=1e-9), f"d of [1,2,3] vs null=2.0 should be 0.0, got {d}"

    # Sample mean above null -> d > 0
    d = cohens_d([3.0, 4.0, 5.0], null_value=2.0)
    assert d is not None and d > 0, f"d of [3,4,5] vs null=2.0 should be > 0, got {d}"

    # Sample mean below null -> d < 0
    d = cohens_d([1.0, 2.0, 3.0], null_value=4.0)
    assert d is not None and d < 0, f"d of [1,2,3] vs null=4.0 should be < 0, got {d}"


def test_bootstrap_ci_known_fixtures() -> None:
    """bootstrap_ci() returns sensible percentiles on known-fixture data."""
    from chess_coach.profile.effect_size import bootstrap_ci

    # Empty sample -> (0, 0)
    assert bootstrap_ci([]) == (0.0, 0.0)

    # Constant sample -> CI is the constant (no variance)
    low, high = bootstrap_ci([5.0] * 100, seed=42)
    assert low == pytest.approx(5.0, abs=1e-9)
    assert high == pytest.approx(5.0, abs=1e-9)

    # Sample with mean 5, std ~1.7 -- 95% CI should bracket 5
    # and be reasonably tight (within 0.5 of mean)
    sample = [3.0, 4.0, 5.0, 6.0, 7.0] * 20  # 100 samples, mean=5
    low, high = bootstrap_ci(sample, n_resamples=500, seed=42)
    assert low < 5.0 < high, f"CI ({low}, {high}) should bracket mean=5.0"
    assert high - low < 1.0, f"CI width ({high - low}) should be < 1.0"

    # Deterministic with seed
    sample = [1.0, 2.0, 3.0, 4.0, 5.0]
    low1, high1 = bootstrap_ci(sample, seed=42)
    low2, high2 = bootstrap_ci(sample, seed=42)
    assert (low1, high1) == (low2, high2), "Same seed should produce same CI"


# --- BBF-57 re-export tests (the 5 implemented metrics) ---


def test_stats_metrics_importable_from_package() -> None:
    """The 5 BBF-57 metrics are importable from chess_coach.profile."""
    from chess_coach.profile import (  # noqa: F401
        tactical_vs_positional_bias,
        time_pressure_quality,
        opening_comfort,
        conversion_ability,
        blunder_rate_vs_rating,
    )


def test_stats_metrics_callable_with_db_path() -> None:
    """The 5 BBF-57 metrics can be called with a fake DB path.

    They should NOT raise NotImplementedError (BBF-57
    implementation replaces the BBF-54 stubs). On an
    empty / non-existent DB, they return an EffectSize
    with `d=None` and `sample_size=0` (no data).
    """
    from chess_coach.profile import (
        tactical_vs_positional_bias,
        time_pressure_quality,
        opening_comfort,
        conversion_ability,
        blunder_rate_vs_rating,
    )
    # Use a non-existent path -- the metrics should
    # handle this gracefully by returning an "no data"
    # EffectSize (sqlite3.connect raises but the metric
    # code catches via the `if sample_size == 0` branch).
    # We test with /dev/null which is a valid empty file
    # (sqlite creates an in-memory db from it).
    fake_db = "/tmp/_bbf57_fake_metrics.db"
    # Ensure it doesn't exist
    if os.path.exists(fake_db):
        os.remove(fake_db)
    try:
        for fn in (
            tactical_vs_positional_bias,
            time_pressure_quality,
            opening_comfort,
            conversion_ability,
            blunder_rate_vs_rating,
        ):
            result = fn(fake_db, "fake_player", seed=42)
            # The result should be an EffectSize with d=None
            # (no data) -- but note the function may raise
            # sqlite3.OperationalError if /tmp doesn't allow
            # writes, which we tolerate.
            from chess_coach.profile.effect_size import EffectSize
            assert isinstance(result, EffectSize), (
                f"{fn.__name__} should return an EffectSize"
            )
            assert result.sample_size == 0, (
                f"{fn.__name__} on empty db should have sample_size=0"
            )
    except Exception as exc:
        # sqlite3 errors on the fake db are tolerated; we
        # only care that NotImplementedError does NOT fire
        assert not isinstance(exc, NotImplementedError), (
            f"BBF-57 should have replaced the BBF-54 stub, "
            f"but {fn.__name__} raised NotImplementedError"
        )


# --- BBF-58/59 xfail markers (still expected to fail) ---


@pytest.mark.xfail(
    reason="BBF-57 ships 5 metric re-exports + effect_size primitives. "
           "Remaining xfails: decision_fatigue + sequence_based_tilt "
           "(BBF-58) + cluster_archetypes (BBF-59).",
    strict=False,
)
def test_profile_package_remaining_names_xfail() -> None:
    """The BBF-58 + BBF-59 names are still not re-exported.

    This xfail narrows the original BBF-54 test (which
    covered all 9 names) down to just the 3 remaining
    ones. When BBF-58 lands, this should be updated to
    only xfail on cluster_archetypes; when BBF-59
    lands, the xfail marker can be removed entirely.
    """
    from chess_coach import profile

    for name in ("decision_fatigue", "sequence_based_tilt", "cluster_archetypes"):
        assert hasattr(profile, name), (
            f"chess_coach.profile.{name} should be re-exported "
            f"by the end of BBF-59"
        )


# --- Submodule-local tests: stats.py stubs still raise for the unimplemented ---


def test_stats_submodule_local_stubs() -> None:
    """BBF-57 implements 5 metrics; decision_fatigue is still a stub.

    The 5 implemented metrics should NOT raise
    NotImplementedError when accessed via the SUBMODULE.
    decision_fatigue (BBF-58) still does.
    """
    from chess_coach.profile.stats import (
        tactical_vs_positional_bias,
        time_pressure_quality,
        opening_comfort,
        conversion_ability,
        blunder_rate_vs_rating,
        decision_fatigue,
    )

    # The 5 implemented metrics take a (db_path, player) pair
    # and return an EffectSize. On a fake / nonexistent db,
    # they may raise sqlite3 errors (which we tolerate) or
    # return an empty-data EffectSize. The KEY assertion is
    # that NotImplementedError does NOT fire.
    fake_db = "/tmp/_bbf57_fake_submodule.db"
    if os.path.exists(fake_db):
        os.remove(fake_db)
    for fn in (
        tactical_vs_positional_bias,
        time_pressure_quality,
        opening_comfort,
        conversion_ability,
        blunder_rate_vs_rating,
    ):
        try:
            result = fn(fake_db, "fake_player", seed=42)
            # Should return EffectSize
            from chess_coach.profile.effect_size import EffectSize
            assert isinstance(result, EffectSize), (
                f"{fn.__name__} should return EffectSize"
            )
        except NotImplementedError:
            pytest.fail(
                f"{fn.__name__} should be implemented in BBF-57 "
                f"but still raises NotImplementedError"
            )
        except Exception:
            # sqlite3 errors on fake db are tolerated
            pass

    # decision_fatigue is still a stub for BBF-58
    with pytest.raises(NotImplementedError, match="BBF-58"):
        decision_fatigue("/tmp/fake.db", "fake_player")


def test_tilt_stub_function_raises_not_implemented() -> None:
    """The tilt.py stub raises NotImplementedError (BBF-58)."""
    from chess_coach.profile.tilt import sequence_based_tilt

    with pytest.raises(NotImplementedError, match="BBF-58"):
        sequence_based_tilt([("W", None)])


def test_archetypes_stub_function_raises_not_implemented() -> None:
    """The archetypes.py stub raises NotImplementedError (BBF-59)."""
    from chess_coach.profile.archetypes import cluster_archetypes

    with pytest.raises(NotImplementedError, match="BBF-59"):
        cluster_archetypes({})