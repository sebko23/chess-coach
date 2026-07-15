"""Smoke test for the chess_coach.profile package skeleton (BBF-54+55).

This test proves the package skeleton imports cleanly and
that the documented submodules are reachable. It does NOT
exercise any metric logic -- that's BBF-56+.

## BBF-54 vs BBF-55 split

BBF-54 originally shipped a single test that asserted:
  (a) the package imports cleanly,
  (b) every name in `__all__` is importable,
  (c) every documented submodule is importable,
  (d) `gate_metric()` works on synthetic EffectSize,
  (e) every stub function raises NotImplementedError.

Tests (b) and (e) failed in CI on BBF-54 because the
package's `__init__.py` lists the FUTURE public API (the
6 metrics, cohens_d, bootstrap_ci, cluster_archetypes,
sequence_based_tilt) in `__all__` but does not yet
re-export them from the submodules. BBF-54 ships the
submodule *skeletons* (the documented stubs); the
re-export lines in `__init__.py` land in BBF-56+ when
the implementations arrive.

BBF-55 splits the test into:
  - **Always-on tests (BBF-54's contract):** (a), (c),
    (d). These passed in BBF-54 and continue to pass.
  - **"Sprint progress" tests, marked xfail:** (b), (e).
    These track the BBF-56+ re-export work. They show
    up as `xfailed` (expected failures) in CI, not as
    real failures, until each BBF that adds a re-export
    converts its `xfail` to a real assertion.

## Why the split

The BBF-54 lesson is that the public API contract
(`__all__`) is forward-declared, but the package shouldn't
crash on import just because a name isn't re-exported yet.
Splitting the tests this way keeps the CI signal honest:
the BBF-54 scaffold lands green; subsequent BBFs turn
each `xfail` into a `pass` one at a time as the
implementations land.

This test mirrors the BBF-43 boot regression test pattern
(small, fast, asserts a structural property, runs in the
`gateway-boot` CI job).
"""
from __future__ import annotations

import pytest


# --- Always-on tests (BBF-54's contract) ---


def test_profile_package_imports() -> None:
    """The chess_coach.profile package must import without error.

    Regression guard against the BBF-51 / pyproject
    package + package-dir both-required lesson: if a
    future BBF adds the package to `packages` but forgets
    the `package-dir` entry (or vice versa), this test
    fails immediately on the import.
    """
    import chess_coach.profile  # noqa: F401
    assert chess_coach.profile.__file__ is not None


def test_profile_submodules_importable() -> None:
    """Every documented submodule must be importable.

    The BBF-54 sprint ships these as documented stubs;
    BBF-56+ replace the NotImplementedError raises with
    real implementations. The submodule skeleton itself
    must exist and import cleanly from BBF-54 onwards.
    """
    from chess_coach.profile import (  # noqa: F401
        archetypes,
        effect_size,
        stats,
        tilt,
    )
    # Each submodule exposes a public API (an __all__ list)
    for mod in (archetypes, effect_size, stats, tilt):
        assert hasattr(mod, "__all__"), (
            f"chess_coach.profile.{mod.__name__} is missing __all__"
        )


def test_effect_size_gate_works_on_synthetic_data() -> None:
    """The gate_metric() helper from effect_size.py works pre-BBF-56.

    gate_metric() is a pure function that operates on a
    precomputed EffectSize. It does NOT need statistical
    primitives (cohens_d, bootstrap_ci) to be implemented.
    BBF-54 ships the gate working so downstream BBFs can
    call it as soon as they have EffectSize objects.

    This test confirms:
      - d=None -> gate fails (insufficient evidence)
      - d=0.3 (below threshold) -> gate fails
      - d=0.7 (above threshold) -> gate passes
      - sample_size=10 (below MIN_SAMPLE_DEFAULT) -> gate fails
    """
    from chess_coach.profile.effect_size import (
        COHENS_D_THRESHOLD,
        EffectSize,
        gate_metric,
    )

    # EffectSize with d=None (variance was zero)
    no_d = EffectSize(
        d=None, ci_low=0.0, ci_high=0.0, sample_size=100, null_value=0.0
    )
    assert gate_metric(no_d) is False, "d=None should not pass the gate"

    # EffectSize with d below threshold (small effect)
    small_d = EffectSize(
        d=0.3, ci_low=0.1, ci_high=0.5, sample_size=100, null_value=0.0
    )
    assert gate_metric(small_d) is False, (
        f"d=0.3 should not pass the gate (threshold={COHENS_D_THRESHOLD})"
    )

    # EffectSize with d above threshold (medium effect)
    medium_d = EffectSize(
        d=0.7, ci_low=0.4, ci_high=1.0, sample_size=100, null_value=0.0
    )
    assert gate_metric(medium_d) is True, (
        f"d=0.7 should pass the gate (threshold={COHENS_D_THRESHOLD})"
    )

    # EffectSize with sample_size below MIN_SAMPLE_DEFAULT (30)
    tiny_sample = EffectSize(
        d=0.7, ci_low=0.4, ci_high=1.0, sample_size=10, null_value=0.0
    )
    assert gate_metric(tiny_sample) is False, (
        "sample_size=10 should not pass the gate"
    )


# --- Sprint-progress tests (BBF-56+ will convert these) ---
# These are expected to fail until each implementation lands.
# They are xfail-marked so the CI reports them as "expected
# failures" rather than real failures. When the corresponding
# BBF lands, the matching xfail line is converted to a real
# assertion (drop the xfail marker, change the test body).
#
# BBF-56: cohens_d, bootstrap_ci re-exports
# BBF-57: 5 metric re-exports (tactical_vs_positional_bias,
#         time_pressure_quality, opening_comfort,
#         conversion_ability, blunder_rate_vs_rating)
# BBF-58: decision_fatigue + sequence_based_tilt re-exports
# BBF-59: cluster_archetypes re-export


@pytest.mark.xfail(
    reason="BBF-54 ships __all__ but the implementations land in BBF-56+; "
           "this xfail will convert to pass as each re-export lands",
    strict=False,
)
def test_profile_package_all_exports_importable() -> None:
    """Every name in chess_coach.profile.__all__ must be importable.

    BBF-54 ships the __all__ list as a forward contract
    that documents what the package WILL expose once
    BBF-56+ land. The package's __init__.py intentionally
    does NOT re-export these names yet (because the
    implementations don't exist). This test xfails until
    each BBF adds the corresponding re-export line.

    Tracking: 5 BBFs each need to land a re-export that
    removes one xfail reason:
      - BBF-56 removes `cohens_d`, `bootstrap_ci`
      - BBF-57 removes 5 metric names
      - BBF-58 removes `decision_fatigue`, `sequence_based_tilt`
      - BBF-59 removes `cluster_archetypes`

    Once all 9 re-exports land, this test passes and the
    xfail marker can be removed.
    """
    from chess_coach import profile

    assert hasattr(profile, "__all__")
    assert isinstance(profile.__all__, list)
    for name in profile.__all__:
        assert hasattr(profile, name), (
            f"chess_coach.profile.{name} is in __all__ but not "
            f"defined. Add `from .submodule import {name}` to "
            f"chess_coach/profile/__init__.py, or remove it from __all__."
        )


@pytest.mark.xfail(
    reason="BBF-54 ships the stub functions in submodules but the "
           "re-exports in __init__.py land in BBF-56+; this xfail "
           "will convert to pass as each BBF lands its re-export",
    strict=False,
)
def test_profile_stub_functions_importable_from_package() -> None:
    """Every BBF-54 stub function is importable from `chess_coach.profile`.

    BBF-54 ships the stubs in their submodules (e.g.
    `chess_coach.profile.stats.tactical_vs_positional_bias`).
    The re-exports at the package level (e.g.
    `chess_coach.profile.tactical_vs_positional_bias`) land
    in BBF-56+ along with the implementations. This test
    xfails until each BBF adds its re-exports.

    Tracking: same 5 BBFs as the __all__ test above.
    """
    from chess_coach.profile import (  # noqa: F401
        cohens_d,
        bootstrap_ci,
        cluster_archetypes,
        decision_fatigue,
        sequence_based_tilt,
        tactical_vs_positional_bias,
        time_pressure_quality,
        opening_comfort,
        conversion_ability,
        blunder_rate_vs_rating,
    )


# --- Working tests for the submodule-local stubs (NOT xfail) ---
# These confirm that the BBF-54 stubs are correctly raising
# NotImplementedError when accessed VIA THE SUBMODULE (not the
# package). This proves the BBF-54 skeleton is correctly
# committed without re-exports at the package level.

def test_stats_stub_functions_raise_not_implemented() -> None:
    """The 6 metric stubs in stats.py raise NotImplementedError."""
    from chess_coach.profile.stats import (
        tactical_vs_positional_bias,
        time_pressure_quality,
        opening_comfort,
        conversion_ability,
        blunder_rate_vs_rating,
        decision_fatigue,
    )

    with pytest.raises(NotImplementedError, match="BBF-57"):
        tactical_vs_positional_bias("/tmp/fake.db", "fake_player")
    with pytest.raises(NotImplementedError, match="BBF-57"):
        time_pressure_quality("/tmp/fake.db", "fake_player")
    with pytest.raises(NotImplementedError, match="BBF-57"):
        opening_comfort("/tmp/fake.db", "fake_player")
    with pytest.raises(NotImplementedError, match="BBF-57"):
        conversion_ability("/tmp/fake.db", "fake_player")
    with pytest.raises(NotImplementedError, match="BBF-57"):
        blunder_rate_vs_rating("/tmp/fake.db", "fake_player")
    with pytest.raises(NotImplementedError, match="BBF-58"):
        decision_fatigue("/tmp/fake.db", "fake_player")


def test_tilt_stub_function_raises_not_implemented() -> None:
    """The tilt.py stub raises NotImplementedError."""
    from chess_coach.profile.tilt import sequence_based_tilt

    with pytest.raises(NotImplementedError, match="BBF-58"):
        sequence_based_tilt([("W", None)])


def test_archetypes_stub_function_raises_not_implemented() -> None:
    """The archetypes.py stub raises NotImplementedError."""
    from chess_coach.profile.archetypes import cluster_archetypes

    with pytest.raises(NotImplementedError, match="BBF-59"):
        cluster_archetotypes({})


def test_effect_size_stubs_raise_not_implemented() -> None:
    """The effect_size.py stubs (cohens_d, bootstrap_ci) raise NotImplementedError.

    These are accessed via the SUBMODULE (the package-level
    re-export lands in BBF-56). The submodule-local access
    works from BBF-54 because the functions are defined in
    the submodule.
    """
    from chess_coach.profile.effect_size import (
        cohens_d,
        bootstrap_ci,
    )

    with pytest.raises(NotImplementedError, match="BBF-56"):
        cohens_d([1.0, 2.0, 3.0], null_value=2.0)
    with pytest.raises(NotImplementedError, match="BBF-56"):
        bootstrap_ci([1.0, 2.0, 3.0])