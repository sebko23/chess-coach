# Archetype Gold v1 — Curation Guide

**Status:** BBF-75 curation kit. The shipped corpus is still a synthetic placeholder until a domain expert replaces it.
**Path:** `tests/gold/archetypes/v1/corpus.json`
**Loader:** `chess_coach.datasets.archetype_gold` (re-exported from `libs/chess_coach/datasets/archetype_gold.py`)

## Goal

Create an initial set of 20-40 player-archetype reference vectors that the kNN classifier at `services/chess_coach/profile/archetypes.py` uses to label real players. Each entry must pair an archetype label with a 6-metric vector (plus the optional `sequence_based_tilt`) drawn from a real player whose behavior was manually verified.

This is a human curation task. Automation may check structure, dense IDs, duplicate IDs, and the placeholder-marker contract, but it must not invent player metric values, archetype labels, or corpus entries.

## Acceptance bar

Every entry must satisfy all of these conditions:

1. **Real player.** Each entry corresponds to a real player whose per-game metrics were computed from a verifiable game set. Use your own games with consent, public game sets with explicit permission, or labelled benchmark data. Never invent a metric vector.
2. **Original label assignment.** Each `archetype_label` must be one of the 7 `STANDARD_ARCHETYPES` and must match the player's actual play pattern. If a player does not clearly fit any archetype, do not add an entry for them.
3. **All 6 required metrics present and finite.** `tactical_vs_positional_bias`, `time_pressure_quality`, `opening_comfort`, `conversion_ability`, `blunder_rate_vs_rating`, `decision_fatigue`. The optional `sequence_based_tilt` is required only for `Tilter` entries.
4. **Unique identity.** IDs are dense (`AG-v1-0001`, `AG-v1-0002`, ...) and both ID and metrics-vector are unique within v1.
5. **No placeholder markers.** A completed entry must not contain `STUB`, `PLACEHOLDER`, `n/a`, or `replace via BBF-75`. The `_metadata.WARNING: "SYNTHETIC PLACEHOLDER"` block must be removed entirely.
6. **Balanced seed.** The completed 20-40 entry seed must include at least 2 entries per non-Unknown archetype (Tactician, Positional Player, Grinder, Wildcard, Specialist, Tilter, Endgame Specialist). This is the strict validator's per-label minimum; an archetype with only 1 entry will not pass the completion gate.

## Entry schema

```json
{
  "id": "AG-v1-0001",
  "archetype_label": "Tactician",
  "metrics": {
    "tactical_vs_positional_bias": 0.70,
    "time_pressure_quality": 0.10,
    "opening_comfort": 5,
    "conversion_ability": 0.65,
    "blunder_rate_vs_rating": 0.15,
    "decision_fatigue": 0.05,
    "sequence_based_tilt": 0.05
  }
}
```

Required fields:

- `id`: string matching `AG-v1-NNNN` (zero-padded, dense from 1).
- `archetype_label`: one of `STANDARD_ARCHETYPES` (Tactician, Positional Player, Grinder, Wildcard, Specialist, Tilter, Endgame Specialist). `Unknown` is reserved for kNN low-confidence outputs and is never a real label.
- `metrics`: dict containing the 6 required keys with finite numeric values in plausible range (-1e6 < v < 1e6). `sequence_based_tilt` is optional but expected for `Tilter` entries.

The kNN algorithm uses these 6 dimensions (z-scored against the corpus mean/std). Missing dimensions in the input are treated as at-mean during classification, so a complete metrics dict is the contract.

## Archetype definitions

| Label | Defining pattern |
|-------|------------------|
| Tactician | High `tactical_vs_positional_bias`, low `opening_comfort` (narrow repertoire) |
| Positional Player | Low `tactical_vs_positional_bias`, low `blunder_rate_vs_rating`, high `opening_comfort` (broad) |
| Grinder | High `conversion_ability`, low `decision_fatigue` |
| Wildcard | High `opening_comfort`, low `conversion_ability` (plays many openings, doesn't close) |
| Specialist | Very low `opening_comfort` (1-2 openings), high `conversion_ability` |
| Tilter | High `sequence_based_tilt` (winrate drops sharply after a loss streak) |
| Endgame Specialist | Low `blunder_rate_vs_rating` in deep plies |

These are operational definitions, not strict thresholds. A real player who sits between Tactician and Positional Player should be omitted rather than forced into one bucket.

## Curation workflow

1. Pick one player and one archetype. Confirm the archetype fits the player's real play, not a desired archetype.
2. Compute the 6 metrics from a verifiable game set (at least 30 games per player, per the §B4 statistical-rigor rule).
3. Assign the next dense ID and write the entry.
4. Add 1-2 more real players for the same archetype until ≥ 2 entries per label.
5. After all entries land, delete the `_metadata` block (or set it to a non-placeholder object).
6. Run the validation command below.
7. Inspect the final diff before committing.

## Validation

From the repository root, using an isolated project environment:

```bash
python scripts/validate_archetype_gold.py
python scripts/validate_archetype_gold.py --json
pytest tests/unit/test_archetype_gold_corpus.py tests/unit/test_validate_archetype_gold_script.py -q
```

On this Windows host, invoke the project interpreter explicitly if `python` is not available, for example:

```powershell
.\.venv\Scripts\python.exe scripts\validate_archetype_gold.py
.\.venv\Scripts\python.exe -m pytest tests\unit\test_archetype_gold_corpus.py tests\unit\test_validate_archetype_gold_script.py -q
```

The strict validator fails while any placeholder marker remains, while the corpus is below 20 or above 40 entries, while any non-Unknown archetype has fewer than 2 entries, or while any required metric is missing. That is intentional: BBF-75 is not complete until the real corpus has replaced every stub and contains 20-40 entries with ≥ 2 per non-Unknown label.

## Review checklist

Before declaring BBF-75 complete:

- [ ] 20-40 entries load successfully.
- [ ] Every entry's `metrics` dict contains all 6 required keys with finite numeric values.
- [ ] No duplicate IDs.
- [ ] IDs are dense and ordered from `AG-v1-0001`.
- [ ] Every `archetype_label` is in `STANDARD_ARCHETYPES` (no `Unknown` entries).
- [ ] Each non-Unknown label has ≥ 2 entries.
- [ ] No placeholder marker remains anywhere in the corpus.
- [ ] `_metadata.WARNING` has been removed.
- [ ] Every player in the corpus is a real person with a verifiable game set.
- [ ] Every metric was computed from real games, not estimated or invented.
- [ ] `scripts/validate_archetype_gold.py` exits 0.
- [ ] `pytest tests/unit/test_archetype_gold_corpus.py tests/unit/test_validate_archetype_gold_script.py -q` passes.

## Out of scope

- Automatically generating the 20-40 reference vectors.
- Scraping player data without verifiable consent.
- Fabricating archetype labels from cluster outputs.
- Modifying the kNN algorithm in `services/chess_coach/profile/archetypes.py`.
- Adding a 7th archetype; the `STANDARD_ARCHETYPES` tuple is fixed.

## Related documentation

- [`L2-gold-v1.md`](L2-gold-v1.md) — sibling corpus spec (chess positions, not player metrics).
- [`../15_methodology/profile-metrics-v1.md`](../15_methodology/profile-metrics-v1.md) — methodology for each of the 6 metrics.
- [`../../CHANGELOG.md`](../../CHANGELOG.md) — BBF-66 kNN swap + BBF-75 entry.
- [`../../10_roadmap/phase-plan-v2.md`](../../10_roadmap/phase-plan-v2.md) — Phase 4 "Playing Style Patterns" plan.
