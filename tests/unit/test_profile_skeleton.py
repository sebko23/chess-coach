"""Smoke test for the chess_coach.profile package skeleton (BBF-54).

This test proves the package skeleton imports cleanly and
that every name listed in `__all__` is importable. It does
NOT exercise any metric logic -- that's BBF-56+.

This test is intentionally minimal so that:
  - `gateway-boot` CI can run it in <1s.
  - Future BBFs (BBF-56, BBF-57, BBF-58, BBF-59) replace
    the `NotImplementedError` raises with real
    implementations; this test continues to pass because
    it doesn't call the stub functions.
  - The `__all__` list in `__init__.py` and the actual
    module exports stay in sync -- if a future BBF adds a
    function but forgets to add it to `__all__`, the
    explicit `from chess_coach.profile import ...` will
    fail at import time.

The test mirrors the BBF-43 boot regression test pattern
(small, fast, asserts a structural property, runs in the
`gateway-boot` CI job).
"""
from __future__ import annotations

import pytest


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


def test_profile_package_all_exports_importable() -> None:
    """Every name in chess_coach.profile.__all__ must be importable.

    Guards against the case where a future BBF adds a
    function to the package but forgets to expose it in
    `__init__.py`'s `__all__` (or, more dangerously,
    adds it to `__all__` without defining it in a
    submodule).
    """
    from chess_coach import profile

    # __all__ exists and is a list of strings
    assert hasattr(profile, "__all__")
    assert isinstance(profile.__all__, list)
    for name in profile.__all__:
        assert isinstance(name, str), f"{name!r} in __all__ is not a string"

    # Every name in __all__ is actually importable
    for name in profile.__all__:
        assert hasattr(profile, name), (
            f"chess_coach.profile.{name} is in __all__ but not "
            f"defined. Add `from .submodule import {name}` to "
            f"chess_coach/profile/__init__.py, or remove it from __all__."
        )


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


def test_profile_stub_functions_raise_not_implemented() -> None:
    """Every BBF-54 stub function raises NotImplementedError.

    This is the explicit "no metric logic shipped yet"
    marker. BBF-56+ will replace these with real
    implementations; this test will need to be updated
    to call the real functions with known fixtures.
    """
    from chess_coach.profile import (
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

    # Statistical primitives (BBF-56)
    with pytest.raises(NotImplementedError, match="BBF-56"):
        cohens_d([1.0, 2.0, 3.0], null_value=2.0)
    with pytest.raises(NotImplementedError, match="BBF-56"):
        bootstrap_ci([1.0, 2.0, 3.0])

    # Stats (BBF-57 for the first 5, BBF-58 for decision_fatigue)
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

    # Tilt (BBF-58)
    with pytest.raises(NotImplementedError, match="BBF-58"):
        sequence_based_tilt([("W", None)])

    # Archetypes (BBF-59)
    with pytest.raises(NotImplementedError, match="BBF-59"):
        cluster_archetotypes({})