"""Sequence-based tilt detection (BBF-54 skeleton).

The pre-existing `tilt_index` field in the
routes/profile_analysis.py response measures ONLY the
"first game after a loss" effect: `max(0, baseline_winrate
- post_loss_winrate)`. The Phase 4 finish replaces this
with a sliding-window tilt detector that captures
sequence-level deterioration (multiple losses in a row
produce a stronger effect than a single loss).

## What this module computes

`sequence_based_tilt(games: list[Game]) -> EffectSize`

where `Game` is a `(result: Literal["W","L","D"],
played_at: datetime)` namedtuple.

The metric computes the post-loss-window winrate for
window sizes N=1, 2, 3, ..., up to a max of 5. The
"sequence tilt" is the maximum negative delta across all
window sizes, normalized against the player's overall
winrate.

## Hypothesis

H1: A player's winrate in games following a streak of N
losses is lower than their overall baseline winrate.

H0: Post-loss-streak winrate equals overall baseline
winrate (no sequence effect).

Effect-size threshold: d >= 0.5 against null=0 (no
difference). Below-threshold metrics MUST NOT surface
as a "you tilt" insight.

## Sample-size requirement

At least 30 games total, with at least 5 loss-streaks
of length >= 2 for the metric to be meaningful.

## Sprint note

BBF-54 ships the module as a documented stub. BBF-58
fills in the implementation. The pre-existing
`tilt_index` field in the legacy route stays in place
during the transition; the new metric is exposed as
`sequence_tilt` alongside the old field for one BBF
cycle so the dashboard can be migrated without a
breaking change.

## Related work

BBF-59 (archetypes) consumes this metric: a player
classified as "Tilter" archetype has a `sequence_tilt`
that passes the §B4 gate.
"""
from __future__ import annotations

from .effect_size import EffectSize


MIN_SAMPLE_TILT = 30         # total games
MIN_LOSS_STREAKS = 5         # loss streaks of length >= 2
MAX_WINDOW = 5               # largest window size to check


def sequence_based_tilt(
    games: list[tuple[str, object]],
) -> EffectSize:
    """Detect sequence-level tilt (sliding window after loss streaks).

    Args:
        games: List of (result, played_at) tuples in
            chronological order. `result` is "W", "L", or
            "D". `played_at` is a datetime (used to
            group games into sessions; games more than
            `session_window_minutes` apart are treated
            as different sessions).

    Returns:
        EffectSize with the point estimate of the maximum
        negative delta across window sizes N=1..MAX_WINDOW.

    BBF-54 stub. BBF-58 implements.
    """
    raise NotImplementedError(
        "sequence_based_tilt is implemented in BBF-58."
    )


__all__ = [
    "MIN_SAMPLE_TILT",
    "MIN_LOSS_STREAKS",
    "MAX_WINDOW",
    "sequence_based_tilt",
]