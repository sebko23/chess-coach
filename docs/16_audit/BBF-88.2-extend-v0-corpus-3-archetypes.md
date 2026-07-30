# BBF-88.2 — Extend v0 archetype corpus to cover all 7 standard archetypes

**Author:** Hermes session 2026-07-30
**Branch:** starting from `main@6480b24` (post-BBF-86.x-final).
**Parent:** BBF-86 release-readiness audit; addresses external-review §13.2 Tier 4 #11.
**Brief scope:** "extend v0 corpus to cover 3 missing archetypes
(Tactician, Wildcard, Specialist)".

---

## 0. Background and the silent failure mode

BBF-88.x (`b843fca`, PR #27) shipped the v0 archetype gold corpus
(8 entries spanning 4 of 7 archetypes: Endgame Specialist, Grinder,
Positional Player, Tilter). The remaining 3 archetypes —
**Tactician, Wildcard, Specialist** — are documented in
`tests/gold/archetypes/v0/corpus.json`'s `_metadata.WARNING` as
"honest gaps."

BBF-86.5 (`881c435`, PR #33) closed the most acute user impact of
this gap by adding a `min_confidence=0.3` floor in `_knn_classify`
(`services/chess_coach/profile/archetypes.py:166-199`): users whose
metric vector falls in the missing-cluster region now receive
`label="Unknown"` rather than a nearest-neighbor from one of the 4
covered archetypes. The 0.3 floor is intentionally conservative.

What remains is the **production truth gap**:

- The corpus is honest about its 4-of-7 coverage.
- The kNN returns "Unknown" for the missing 3 archetype clusters.
- The user sees `Unknown` instead of their actual archetype.
- A `Tactician` (high tactical, low opening breadth) reports
  `Unknown` and the app shows no coaching guidance tuned to that
  style.

This BBF closes the production truth gap by extending the v0 corpus
to cover all 7 standard archetypes.

---

## 1. The fix

**Three changes:**

1. **`tests/gold/archetypes_with_analyses_fixtures.py`**: extend the
   `_player_per_archetype` builder to synthesize per-archetype
   score_cp trajectories for Tactician, Wildcard, and Specialist
   (the missing 3). The `ARCHETYPE_TRAITS` dictionary at lines
   72-115 already declares all 7 archetypes with their trait
   parameters (start_score, end_score, blunder_rate, etc.); the
   missing piece is the per-archetype player builder / sample
   sizing. Adapt the existing pattern for the 3 missing archetypes.

2. **`tests/gold/archetypes/v0/corpus.json`**: re-emit by running
   `scripts/curate_archetype_gold_auto.py` against the extended
   fixture. Expect a corpus with **at least 12 entries** spanning
   all 7 archetypes (2 per archetype is the BBF-75 size rule).
   Update `_metadata.WARNING` to remove the "Tactician, Wildcard,
   Specialist not labeled" clause and replace with "all 7 standard
   archetypes covered (12 entries, kNN-bootstrapped provenance)."

3. **`scripts/validate_archetype_gold.py`**: re-run
   `validate_archetype_gold --version v0 --json` to confirm
   `complete: true`. The validator already accepts auto-provenance
   corpora (BBF-88.x exemption) and enforces `_MIN_AUTO_ENTRIES=1`,
   `_MAX_AUTO_ENTRIES=30`. The expected new size is 12-14 entries,
   well within both bounds. No validator code change is required
   if the 7-of-7 coverage target is met.

---

## 2. Files BBF-88.2 touches

| File | Type | LOC est |
|---|---|---|
| `tests/gold/archetypes_with_analyses_fixtures.py` | EDIT | +~80 LOC: 3 new archetype builder branches, mirroring existing 4. |
| `tests/gold/archetypes/v0/corpus.json` | RE-EMIT | data only; ~12 new entries + metadata tweak. |
| `scripts/curate_archetype_gold_auto.py` | EDIT (optional) | +~20 LOC: ensure all 7 archetype traits get sampled at fixture call time; surface n_per_archetype in the log. |
| `tests/unit/test_archetype_gold_corpus.py` | EDIT | +~30 LOC: round-trip test asserting all 7 STANDARD_ARCHETYPES appear in v0 entries. |
| `tests/unit/test_archetype_knn.py` | EDIT (optional) | +~50 LOC: confidence-floor test exercising a Tactician-shaped metric vector; expects either a `Tactician` label with confidence ≥ 0.3 OR a regression of the confidence-floor behavior. |
| `docs/20_datasets/archetype-gold-v1.md` | EDIT | +~40 LOC: v0 appendix update (Tactician/Wildcard/Specialist coverage now shipped). |

Total: **~220 LOC** of code+data, plus 1 generator run.

---

## 3. NOT touched

- **Production default version** (`services/chess_coach/profile/archetypes.py:143`
  hard-codes `load_archetype_gold("v1")`). This BBF ships the
  expanded v0 corpus **alongside** v1, mirroring BBF-88.x's
  "alongside_v1" strategy. The default-flip to v0 is a separate
  decision (BBF-86.7 territory, see §4 cross-ref).
- **kNN algorithm**. Euclidean + z-scored + k=3 + threshold 2.0 +
  min_confidence 0.3 stay as-is. The expanded corpus may *raise*
  the average confidence for users in the previously-missing
  clusters; that is the desired effect, not an algorithm change.
- **BBF-86.5 confidence floor**. Stays at 0.3 unless the leaf
  review of this BBF flags a need to retune.
- **BBF-87.2 narrative corpus regen**. Independent workstream.

---

## 4. Honest disclosures

1. **The metric vectors remain kNN-bootstrapped from v1.** The
   shape-correct synthetic score_cp trajectories produce realistic
   clusters, but the labels are still derived from the v1
   placeholder via `_knn_classify`. By project decision there is no
   human-curator path. The honest gap is "metric vectors are real
   (production SQL pipeline), labels are auto-bootstrapped from v1."
   This BBF does not close that gap; it only widens coverage.

2. **The 3 new archetype entries may be near-duplicates of
   existing ones.** Tactician's trait shape (high tactical,
   mid blunder, low opening breadth) overlaps with the
   already-shipped Tilter cluster. Wildcard (high blunder,
   high opening breadth) overlaps with Tilter as well. The
   expanded corpus may not actually be 7-distinct-clusters
   in metric-vector space; it may be 4-5 with 3 new
   "edge" entries. The kNN will assign labels; the
   `min_confidence` floor remains the safety net.

3. **The expanded corpus is a "ship the data we have" BBF, not
   "ship real labelled data."** A future BBF-88.3 (or similar)
   would either (a) hand-curate a v1 with chess-expert labels
   or (b) commission a labeled dataset from an external service.
   This BBF explicitly defers that.

---

## 5. Ship gate

1. Extend `tests/gold/archetypes_with_analyses_fixtures.py` to
   cover the 3 missing archetypes.
2. Re-run `scripts/curate_archetype_gold_auto.py`.
3. Re-run `scripts/validate_archetype_gold.py --version v0 --json`
   and confirm `complete: true` with all 7 labels present.
4. Add a unit test asserting all 7 STANDARD_ARCHETYPES appear in v0
   entries.
5. Update `docs/20_datasets/archetype-gold-v1.md` v0 appendix.
6. `git diff --numstat HEAD~1..HEAD` per the BBF-84A reflex.
7. Leaf review mandatory per §13.5 (touches user-facing data).
8. User-named `go BBF-88.2` → squash-merge per BBF-sprint contract.

---

## 6. Per BBF-sprint contract

This BBF is **data + tests + docs**, no production code change.
The v0 corpus file changes; production still loads v1. The fix
takes effect when BBF-86.7 (corpus versioning) lands and flips
the default to v0.

Leaf review is mandatory per the §13.5 meta-pattern: this BBF
touches user-facing data. The two nits to watch for:
(a) the validator's `_MIN_AUTO_ENTRIES` rule must still pass;
(b) the production code must still load v1 (no accidental
flips). Both are quick file:line checks.

---

## 7. Reference

External review §13.2 (this BBF as Tier 4):
> "BBF-88.2 — extend v0 corpus to cover 3 missing archetypes
> (Tactician, Wildcard, Specialist)."

External review §5.2 (silent failure mode framing):
> "A future BBF-88.2 can extend the synthetic fixture to produce
> the missing archetype shapes."

BBF-88.x shipped code: `b843fca` (PR #27) — auto-derived archetype
gold v0 corpus.

BBF-86.5 shipped code: `881c435` (PR #33) — confidence floor in
`_knn_classify`.

BBF-86.7 cross-reference: corpus self-describing version + Dockerfile
build-time flag (Tier 4 held back per §13.2). The default-flip
from v1 to v0 belongs in BBF-86.7's scope, not here.
