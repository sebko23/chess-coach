# Profile Metrics Methodology v1

**Status:** v1, Phase 4 finish (BBF-60).
**Sprint:** BBF-54..62 (Phase 4 finish).
**Source-of-truth:** [`docs/13_review_response/response-to-review.md` §B4](../../13_review_response/response-to-review.md)
**Implementation:** [`services/chess_coach/profile/`](../../services/chess_coach/profile/)

## Scope

This document is the methodology reference for the 6 Phase 4
metrics + the sequence-based tilt detector + the archetype
clusterer. Each metric gets a section that documents:

- **Hypothesis (H1)**: what the metric is supposed to measure
- **Null hypothesis (H0)**: the expected value under "no
  measurable tendency"
- **Effect-size threshold**: Cohen's d >= 0.5 against H0
  (the §B4 surfacing gate; per §B4 rule 3, metrics that
  don't pass this gate are NOT surfaced as coaching
  insights)
- **Sample-size requirement**: minimum number of qualifying
  observations for the metric to be meaningful
- **Computation**: SQL query + Python steps
- **Caveats**: known limitations + what the metric does NOT
  measure

This document is also the source for the §B4 rule 4 endpoint
[`/v1/profile/{player}/explain/{metric}`](../../services/chess_coach/gateway/routes/profile.py):
the endpoint slices this doc per H2 heading and returns the
section text + the EffectSize + intermediate values.

## Per-metric index

- [tactical_vs_positional_bias](#tactical_vs_positional_bias)
- [time_pressure_quality](#time_pressure_quality)
- [opening_comfort](#opening_comfort)
- [conversion_ability](#conversion_ability)
- [blunder_rate_vs_rating](#blunder_rate_vs_rating)
- [decision_fatigue](#decision_fatigue)
- [sequence_based_tilt](#sequence_based_tilt)
- [archetypes](#archetypes)

## §B4 background

The Claude review of the project (2026-05-19) accepted the
§B4 statistical-rigor rules for Phase 4 metrics in
`response-to-review.md` §B4. The rules are:

  1. **Hypothesis + null hypothesis** per metric.
  2. **Effect-size threshold** (Cohen's d >= 0.5) -- the
     medium effect size per Cohen 1988.
  3. **Below-threshold metrics MUST NOT surface as coaching
     insights**, regardless of p-value.
  4. **Permanent "experimental" label** on every metric
     rendered in the UI.
  5. **Non-clinical disclaimer** on the profile page.
  6. **`/profile/explain/{metric}` endpoint** showing
     methodology + raw inputs + intermediate values.

This doc is the canonical reference for rule 1 (each metric
has H1 + H0 documented here) and rule 6 (the explain
endpoint slices this doc). The other rules are enforced in
the route layer + dashboard.

## Phase 4 "experimental" + non-clinical disclaimer

All metrics ship with a permanent "experimental" badge in
the UI. The profile page includes the following disclaimer:

> "These metrics are experimental. They are not a clinical
> assessment of cognitive function, mental health, or any
> other condition. They are statistical summaries of chess
> game data, intended for chess coaching only. Consult a
> qualified chess coach for interpretation."

The disclaimer is rendered alongside the "Playing Style
Patterns" section header (per §B4, the user-facing label is
"Playing Style Patterns" not "Psychological Profiling"; the
internal module name stays `profile`).

## tactical_vs_positional_bias

### Hypothesis (H1)
The player converts tactical opportunities (positions where
`side_delta > 80` from their POV) at a rate higher than 50%
(the random-guess rate).

### Null hypothesis (H0)
The player converts opportunities at the random-guess rate
(50%). The binary observation list (1 = took the
opportunity, 0 = missed) has mean = 0.5.

### Effect-size threshold
Cohen's d >= 0.5 against null=0.5. Below-threshold metrics
are rendered as "no measurable tactical tendency" rather
than as a coaching insight.

### Sample-size requirement
MIN_SAMPLE_DEFAULT (30) qualifying opportunities. An
"opportunity" is any position where `|side_delta| > 80` from
the player's POV.

### Computation

1. Extract side-aware centipawn deltas from the analyses
   table (even ply = White moved, odd ply = Black moved;
   flip the sign for Black's moves).
2. Filter to positions where `|delta| > 80` (the
   opportunity threshold).
3. Build a binary observation list: 1 if delta > 80 (took
   the opportunity), 0 if delta < -80 (missed it).
4. Compute:
   - `point_estimate` = mean of the binary list
   - `d` = `cohens_d(observations, null_value=0.5)`
   - `ci_low`, `ci_high` = `bootstrap_ci(observations)`

### Caveats
- The 80cp opportunity threshold is a hardcoded constant.
  It is not empirically calibrated against human GMs;
  GM-level players routinely capitalize on smaller
  opportunities.
- The metric does not distinguish between "saw the tactic
  but failed to execute" and "missed the tactic entirely".
  Both produce a "missed" observation.

## time_pressure_quality

### Hypothesis (H1)
The player makes MORE blunders (cp drop > 100) in deep plies
(>30) than in early plies (<=30) -- i.e. time pressure
hurts their play.

### Null hypothesis (H0)
The deep-ply blunder rate equals the early-ply blunder rate
(no time-pressure effect). The binary observation list (1 =
blunder, 0 = not) has mean = 0.

### Effect-size threshold
Cohen's d >= 0.5 against null=0 (no difference). The
point_estimate is `max(0, deep_rate - early_rate)`, so
only positive values (more blunders late) surface as a
"time pressure hurts" insight.

### Sample-size requirement
MIN_SAMPLE_DEFAULT (30) total positions.

### Computation

1. Extract side-aware deltas (same query as
   tactical_vs_positional_bias).
2. Filter to positions with `delta < -100` (blunder).
3. Build a binary observation list: 1 = blunder, 0 = not.
4. Compute:
   - `point_estimate` = mean of the binary list (overall
     blunder rate)
   - `d` = `cohens_d(observations, null_value=0)`
   - `ci` = bootstrap_ci on the binary list

### Caveats
- The metric reports the OVERALL blunder rate, not the
  delta between deep and early. The early/deep split is
  computed but not exposed in the point_estimate.
- The ply-30 boundary is a hardcoded constant. Different
  game types (bullet, blitz, rapid) have different
  effective time pressure curves.

## opening_comfort

### Hypothesis (H1)
The player has played at least K distinct opening patterns
in their first 10 plies (a measure of opening repertoire
breadth).

### Null hypothesis (H0)
The player plays a narrow repertoire (K=1 or 2 openings).
Cohen's d is computed against a null of "expected novelty
rate" derived from the player's distinct-prefix count.

### Effect-size threshold
Cohen's d >= 0.5 against the null. The null value is
`max(0, 1 - 1/distinct_prefix_count)` -- a uniform-
distribution assumption. For a player with 1 distinct
opening, null = 0 (everything is "familiar"). For a player
with 10 distinct openings, null = 0.9 (most positions
are "novel").

### Sample-size requirement
MIN_SAMPLE_OPENING (20) positions in the first 10 plies.

### Computation

1. Extract the player's first-10-plies `move_san` values.
2. Count distinct opening prefixes (first 10 chars of
   move_san).
3. Build a binary observation list: 1 if the position's
   prefix is in the distinct set (familiar), 0 if not
   (novel).
4. Compute:
   - `point_estimate` = mean of the binary list (fraction
     of positions that are familiar openings)
   - `d` = `cohens_d(observations, null_value)`
   - `ci` = bootstrap_ci

### Caveats
- The metric is a "breadth" measure, not a "comfort" measure
  in the strict sense. A high breadth score does NOT mean
  the player is comfortable in those openings -- just
  that they've played them.
- The first-10-plies window is a hardcoded constant.
  Some openings are defined by moves 11-15, not 1-10.

## conversion_ability

### Hypothesis (H1)
The player converts positions where they were winning
(score_cp > 200 from their POV at ply 30+) at a rate
higher than 50% (the random rate).

### Null hypothesis (H0)
The player converts winning positions at the random rate
(50%). The binary observation list (1 = converted to win,
0 = drew or lost) has mean = 0.5.

### Effect-size threshold
Cohen's d >= 0.5 against null=0.5.

### Sample-size requirement
MIN_SAMPLE_CONVERSION (15) qualifying positions.

### Computation

1. Extract the player's positions at ply >= 30 with
   `side_cp > 200` (player was winning).
2. For each game's first qualifying position, check the
   game result from the player's POV.
3. Build a binary observation list: 1 = won, 0 = drew/lost.
4. Compute point_estimate, d, ci as in tactical_vs_positional_bias.

### Caveats
- "Winning" is defined as side_cp > 200 (i.e. +2 pawns
  from the player's POV). GMs routinely convert
  smaller advantages; this metric only catches clear wins.
- The metric does not distinguish between "drew a
  clearly-won position" and "lost a clearly-won position"
  (both are "missed conversions" with d=0).

## blunder_rate_vs_rating

### Hypothesis (H1)
The player's blunder rate (cp drop > 150 per move) is
lower than would be expected for their mean opponent
rating (a "rating-relative" blunder rate).

### Null hypothesis (H0)
The player's blunder rate is at the rating-expected level.
The expected level is a linear function of opponent rating:
`expected = max(0, 0.20 - (mean_opp_rating - 1500) * 0.0001)`.

### Effect-size threshold
Cohen's d >= 0.5 against the rating-expected rate.

### Sample-size requirement
MIN_SAMPLE_DEFAULT (30) positions.

### Computation

1. Probe the `games` table for rating columns
   (white_elo, black_elo, or schema variants). If no
   rating info is available, the metric returns
   `EffectSize(d=None, sample_size=0, ...)` and the UI
   renders "no rating data" rather than a number.
2. Compute the player's mean opponent rating.
3. Compute the expected blunder rate from the linear
   model above.
4. Extract side-aware deltas, build a binary observation
   list (1 = blunder = delta < -150, 0 = not).
5. Compute point_estimate (the actual rate), d
   (against the expected rate), ci.

### Caveats
- The linear model is a placeholder. The methodology
  doc (BBF-60) will document the empirical basis. The
  current model assumes 20% blunder rate at 1500 ELO,
  dropping 0.01% per 100 ELO above 1500. This is NOT
  empirically calibrated.
- Different rating systems (Lichess, Chess.com, FIDE)
  have different blunder-rate curves. The current
  model is rating-system-agnostic.

## decision_fatigue

### Hypothesis (H1)
The player's blunder rate INCREASES as move count grows
within a single session (a session = a calendar date's
worth of games).

### Null hypothesis (H0)
Blunder rate is constant across move counts within a
session. The regression coefficient of blunder rate vs
normalized session position is 0.

### Effect-size threshold
The standardized regression coefficient (slope * SD(X)
/ SD(resid)) >= 0.5. Only positive slopes (blunders
increase with move count) are surfaced as "decision
fatigue" insights.

### Sample-size requirement
MIN_SAMPLE_DECISION_FATIGUE (50) total positions across
all sessions.

### Computation

1. Group games into sessions by `games.date` (PGN Date
   tag). Games on the same date form one session.
2. For each session, compute the normalized session
   position (0 at session start, 1 at session end) for
   each mainline position.
3. Build a binary observation list (1 = blunder = delta
   < -100, 0 = not) and a matching normalized position
   list.
4. Compute the regression coefficient of blunder rate
   vs normalized position.
5. Cohen's d is the standardized coefficient.

### Caveats
- Session boundaries are calendar-date based, not
  "session-window based" (the original BBF-54 spec said
  session_window_minutes=120 but the implementation uses
  `games.date` for simplicity). Players who play across
  midnight may have artificial session boundaries.
- A single long game can dominate the regression if it
  has many positions.
- The metric does not distinguish "decision fatigue
  within a single game" from "decision fatigue across
  consecutive games in a session" -- both contribute
  to the regression.

## sequence_based_tilt

### Hypothesis (H1)
A player's winrate in games following a streak of N
consecutive losses is lower than their overall baseline
winrate.

### Null hypothesis (H0)
Post-loss-streak winrate equals overall baseline winrate
(no sequence effect). Cohen's d is computed on the binary
(won=1, lost/drawn=0) observation list against the
player's overall baseline winrate as the null.

### Effect-size threshold
Standardized deviation from baseline >= 0.5. The
point_estimate is `max(0, baseline - worst_window_winrate)`,
so only positive values (winrate drop) surface as a
"tilt" insight.

### Sample-size requirement
MIN_SAMPLE_TILT (30) total games AND MIN_LOSS_STREAKS (5)
loss-streaks of length >= 2.

### Computation

1. Fetch the player's games in chronological order
   (by `COALESCE(games.date, games.created_at)`).
2. Convert each game to the player's POV: W, L, or D.
3. Build loss-streaks (maximal runs of L).
4. For each window size N=1..MAX_WINDOW (5):
   - For each game, check if the previous N games were
     all losses.
   - If yes, count this game as a "post-loss-streak of N"
     position.
5. Build a binary observation list across all window
   sizes: 1 if the player won the post-streak game, 0
   otherwise.
6. Compute point_estimate (max delta from baseline), d
   (standardized), ci.

### Caveats
- The metric replaces the legacy `tilt_index` field in
  the routes/profile_analysis.py response. The legacy
  field stays in place during the transition.
- "Streak" detection is reset by draws (D) and wins
  (W). A streak of L-L-D-L-L is two separate 1-loss
  streaks, not one 3-loss streak.

## archetypes

### Hypothesis
A player's 6-metric vector matches one of 7 standard
archetype shapes (Tactician, Positional Player, Grinder,
Wildcard, Specialist, Tilter, Endgame Specialist) or
"Unknown".

### Computation

1. Compute the 6 metric values for the player.
2. Score every archetype (each has 2-3 "signature" metric
   values defining its canonical shape).
3. Pick the archetype with the highest score (>= 0.4).
   Otherwise "Unknown".

### Effect-size threshold
`confidence > 0.4` (the minimum score for a confident
non-Unknown assignment). Below-threshold assignments
are rendered as "Inconclusive".

### Caveats
- The implementation is a heuristic shape-match, NOT
  kNN against the L-2 gold corpus. L-2 v1 has only 12
  positions (5 opening / 4 middlegame / 3 endgame) which
  is too small for kNN. The kNN implementation is
  deferred to a future BBF when L-2 grows.
- Archetype labels are EXPERIMENTAL. They are a
  clustering result, not a measurement. The UI renders
  the label with the "experimental" badge.
- The canonical shape definitions were hand-coded for
  BBF-59. Empirical validation against the L-2 v2
  corpus is a future work item.

## Archetype cluster (BBF-65)

**Hypothesis.** A player's 6-metric vector places them in one of a small
number of stylistic archetypes (Tactician, Positional Player, Grinder,
Wildcard, Specialist, Tilter, Endgame Specialist). This is a CLUSTERING
result, not a measurement.

**Null hypothesis.** A player's metric vector is no closer to any
archetype shape than the population of archetypes treats as typical.

**Effect-size threshold.** Cohen's d >= 0.5 against the OTHER
archetypes' score distribution (synthesized null). Below-threshold
assignments surface as `passes_b4_gate=False` so the UI can render
"Inconclusive" instead of a confident false-label.

**Sample-size requirement.** The cluster uses the 6 available
metric-vector components. If fewer than 2 metrics are present,
the cluster falls back to "Unknown" without surfacing a label.

**Confidence band.** `archetype_scores` carries the full top-N
score vector (one entry per `STANDARD_ARCHETYPES` archetype, plus
"Unknown"). The `/explain` endpoint renders the top-3 nearest.

**Note.** The current implementation is kNN classification (k=3,
z-scored Euclidean) against the archetype-labelled reference corpus at
`tests/gold/archetypes/v*/corpus.json` (BBF-66). Heuristic shape-matching
(BBF-59) is RETIRED -- not kept as a fallback -- per the Q1 strategic
decision. Single source of truth.

The v1 corpus is a **SYNTHETIC PLACEHOLDER** (see the
`_metadata.WARNING` block in the corpus file). Confidence values from
kNN against this corpus are NOT validated against real chess data.
A follow-on BBF replaces placeholders with real hand-labelled entries.

Implementation:

- `services/chess_coach/profile/archetypes.py` (BBF-59 ship; BBF-65
  patches Cohen's d computation + `passes_b4_gate` field).
- Route handler `services/chess_coach/gateway/routes/profile.py`'s
  `explain_metric(metric_id="archetypes")` branch -- the BBF-65.3
  route patch reads the canonical `assignment.passes_b4_gate` field
  instead of re-deriving.
- Tests:
  - `tests/unit/test_profile_tilt_archetypes.py` (22 tests: 6 heuristic
    shape-match + 4 BBF-65.1 d/cap tests + 2 BBF-65.2 gate tests + 10 misc).
  - `tests/integration/test_profile_archetypes_integration.py`
    (2 route-level integration tests, marked `@pytest.mark.slow`,
    ~3 min real-DB latency).
- `tests/gold/archetypes/v1/corpus.json` (SYNTHETIC PLACEHOLDER corpus,
    14 entries / 2 per `STANDARD_ARCHETYPES` archetype).
- `libs/chess_coach/datasets/archetype_gold.py` (corpus loader +
    validator mirroring `l2_gold.py` shape).
- `tests/unit/test_archetype_knn.py` (6 kNN unit tests).
- `tests/unit/test_archetype_gold_corpus.py` (5 loader unit tests).

**Distance metric (kNN):** z-scored Euclidean on the 7 metric
dimensions (`tactical_vs_positional_bias`, `time_pressure_quality`,
`opening_comfort`, `conversion_ability`, `blunder_rate_vs_rating`,
`decision_fatigue`, `sequence_based_tilt`). Per-dimension z-scores are
computed from the corpus mean/std. Distance is restricted to dimensions
present in BOTH the input and each reference vector (so missing metrics
don't penalize distance). k=3 nearest neighbours vote on the label;
mean distance > 2.0 z-score units returns "Unknown".

