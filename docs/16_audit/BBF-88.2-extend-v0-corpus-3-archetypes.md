# BBF-88.2 — Extend v0 archetype corpus to cover all 7 standard archetypes

**Author:** Hermes session 2026-07-30
**Branch:** starting from `main@6480b24` (post-BBF-86.x-final).
**Parent:** BBF-86 release-readiness audit; addresses external-review §13.2 Tier 4 #11.
**Brief scope:** "extend v0 corpus to cover 3 missing archetypes
(Tactician, Wildcard, Specialist)".

**Amended 2026-07-30 (BBF-88.2a):** §1 step 1 retired (fixture is
already complete); §1 step 2 amended to the real data path;
§2 file list updated; §4 honest disclosure updated. The
original brief claimed a "missing-fixture-piece" gap that does
not exist — see `docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-07-30-bbf-88-2-scope.md`
for the category-error analysis. The external reviewer (2026-07-30)
approved Path A: author 6 hand-curated synthetic entries directly
into the v0 corpus with a new `synthetic_shape_curated` provenance
strategy.

---

## 0. Background and the silent failure mode

BBF-88.x (`b843fca`, PR #27) shipped the v0 archetype gold corpus
(8 entries spanning 4 of 7 archetypes: Endgame Specialist, Grinder,
Positional Player, Tilter). The remaining 3 archetypes —
**Tactician, Wildcard, Specialist** — were documented in
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

1. **`scripts/validate_archetype_gold.py`**: teach the validator
   about a new `synthetic_shape_curated` provenance strategy. The
   validator requires shape-curated entries to carry an
   `archetype_trait_source` field in `_provenance` and logs a
   WARNING when any shape-curated entries are present so operators
   see the new strategy in their validation output. The WARNING
   is advisory and does not fail the corpus. (~30 LOC)

2. **`tests/gold/archetypes/v0/corpus.json`**: add 6 hand-curated
   entries spanning Tactician (×2), Wildcard (×2), and Specialist
   (×2). Each entry's metric vector is derived from the
   `ARCHETYPE_TRAITS[archetype]` shape contract (start_score,
   end_score, blunder_rate, opening_breadth_index, etc.) so the
   entry sits in a distinctive region of metric-vector space. Each
   entry carries `_provenance.strategy: "synthetic_shape_curated"`
   and `_provenance.archetype_trait_source: "ARCHETYPE_TRAITS[archetype]"`.
   Update `_metadata.WARNING` to remove the "Tactician, Wildcard,
   Specialist not labeled" clause and document the dual-provenance
   structure. (~120 LOC of data, no generator run)

3. **`tests/unit/test_archetype_gold_corpus.py`**: add two new
   tests:
   - `test_v0_all_7_archetypes_covered` — every `STANDARD_ARCHETYPES`
     label appears in the v0 corpus. Prevents regression.
   - `test_v0_shape_curated_entries_have_archetype_trait_source` —
     every shape-curated entry documents its trait source.
   (~40 LOC)

**Note on §1 step 1 (retired):** The original brief claimed the
fixture was "missing 3 archetype builder branches" and the "missing
piece is the per-archetype player builder / sample sizing." This is
**incorrect**. `tests/gold/archetypes_with_analyses_fixtures.py:72-115`
already declares all 7 archetypes in `ARCHETYPE_TRAITS`, and
`build_player` works for any archetype key. The actual 4-of-7 gap
came from the kNN-bootstrap against v1 placeholder, which clusters
around 4 archetype shapes. Extending the fixture would not have
changed the v0 corpus. The 6 hand-curated entries (step 2) are
what closes the gap.

**Note on §1 step 2 (amended):** The original brief said
"re-emit by running `scripts/curate_archetype_gold_auto.py` against
the extended fixture." The generator reads from user-local PGN
inputs (`tests/gold/archetypes/v0/corpus.json:10-13` lists
`C:/Users/i3/Desktop/lichess_ebassti_2026-03-05.pgn` and similar
host-local paths) and cannot be re-run end-to-end in any
environment other than the original author's host. The
`synthetic_shape_curated` strategy is the only environment-agnostic
data path.

---

## 2. Files BBF-88.2a touches

| File | Type | LOC est |
|---|---|---|
| `tests/gold/archetypes/v0/corpus.json` | EDIT | +~120 LOC: 6 new entries + metadata tweak. |
| `scripts/validate_archetype_gold.py` | EDIT | +~30 LOC: new `_SHAPE_CURATED_STRATEGY` constant + per-entry validation + WARNING log. |
| `tests/unit/test_archetype_gold_corpus.py` | EDIT | +~40 LOC: 2 new tests (7-of-7 coverage, shape-curated provenance). |

Total: **~190 LOC** of code+data. No fixture edit. No generator run.

---

## 3. NOT touched

- **Production default version** (`services/chess_coach/profile/archetypes.py:143`
  hard-codes `load_archetype_gold("v1")`). This BBF ships the
  expanded v0 corpus **alongside** v1, mirroring BBF-88.x's
  "alongside_v1" strategy. The default-flip to v0 is a separate
  decision (BBF-86.7 territory, see §7 cross-ref).
- **kNN algorithm**. Euclidean + z-scored + k=3 + threshold 2.0 +
  min_confidence 0.3 stay as-is. The expanded corpus *raises*
  the average confidence for users in the previously-missing
  clusters; that is the desired effect, not an algorithm change.
- **BBF-86.5 confidence floor**. Stays at 0.3 unless the leaf
  review of this BBF flags a need to retune.
- **`tests/gold/archetypes_with_analyses_fixtures.py`**. Already
  declares all 7 archetypes in `ARCHETYPE_TRAITS` (lines 72-115).
- **BBF-87.2 narrative corpus regen**. Independent workstream.

---

## 4. Honest disclosures

1. **The 6 new entries are hand-curated, not measured.** The
   metric vectors are derived from `ARCHETYPE_TRAITS[archetype]`
   shape contract, not from a real (player, games, scores)
   measurement pipeline. This is a step back from the v0
   corpus's "metric vectors are real (production SQL pipeline)"
   claim for those 6 entries. The validator logs a WARNING
   so operators see which entries are hand-curated.

2. **The metric vectors for the 8 kNN-bootstrapped entries are
   unchanged.** The 6 hand-curated entries use the v0 corpus's
   existing `provenance: "auto"` outer marker (the validator's
   auto-corpus size and per-archetype floor rules apply) but
   carry an inner `_provenance.strategy: "synthetic_shape_curated"`
   for fine-grained provenance reporting. The two provenance
   schemes are documented in the corpus `_metadata`.

3. **The expanded corpus is a "ship the data we have" BBF, not
   "ship real labelled data."** A future BBF-89 (or similar)
   would either (a) hand-curate a v1 with chess-expert labels
   or (b) commission a labeled dataset from an external service.
   This BBF explicitly defers that. The new validator WARNING
   makes the limitation visible.

4. **The new metric vectors are designed to be distinctive, not
   near-duplicates.** The original brief's §4 disclosure #2
   warned that the 3 new archetypes' trait shapes overlap with
   the 4 covered archetypes (Tactician ~ Tilter, Wildcard ~
   Tilter). The hand-curated metric vectors in this BBF are
   designed to extend the metric-vector space, not duplicate
   it: Tactician sits at `tactical_vs_positional_bias ~0.78`
   (vs. the 0.42-0.50 cluster of existing entries);
   Wildcard at `opening_comfort=4.0` and `blunder_rate ~0.28`
   (the existing entries all sit at `opening_comfort=1.0` and
   `blunder_rate <= 0.18`); Specialist at `opening_comfort=0.0`
   (the existing entries all sit at `opening_comfort=1.0`).
   The kNN should now have a clear nearest reference for each
   of the 3 missing archetype clusters.

---

## 5. Ship gate

1. Add 6 hand-curated entries to `tests/gold/archetypes/v0/corpus.json`.
2. Add `synthetic_shape_curated` branch to `scripts/validate_archetype_gold.py`.
3. Add `test_v0_all_7_archetypes_covered` and
   `test_v0_shape_curated_entries_have_archetype_trait_source` to
   `tests/unit/test_archetype_gold_corpus.py`.
4. Run `scripts/validate_archetype_gold.py --version v0 --json`
   and confirm `complete: true` with all 7 labels present.
5. `git diff --numstat HEAD~1..HEAD` per the BBF-84A reflex.
6. Leaf review mandatory per §13.5 (touches user-facing data).
7. User-named `go BBF-88.2a` → squash-merge per BBF-sprint contract.

---

## 6. Per BBF-sprint contract

This BBF is **data + tests + docs (brief amend)**, no production
code change. The v0 corpus file changes; production still loads
v1. The fix takes effect when BBF-86.7 (corpus versioning) lands
and flips the default to v0.

Leaf review is mandatory per the §13.5 meta-pattern: this BBF
touches user-facing data. The nits to watch for:
(a) the validator's `_MIN_AUTO_ENTRIES`/`_MAX_AUTO_ENTRIES` rules
must still pass (14 entries, well within 1-30);
(b) the production code must still load v1 (no accidental flips);
(c) the 6 new entries' metric vectors must be distinctive enough
that the kNN actually returns the new archetype labels for
Tactician/Wildcard/Specialist-shaped inputs;
(d) the 2-per-archetype floor in the validator is satisfied for
all 7 archetypes.

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

BBF-88.2a scope-error analysis:
`docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-07-30-bbf-88-2-scope.md`
(346 lines) — the category-error report that triggered this
amendment. External reviewer approved Path A on 2026-07-30.

BBF-89 cross-reference: hand-curated seed corpus (per external
reviewer's recommendation). The eventual replacement for the
`AUTO-DERIVED + SHAPE-CURATED` provenance in the v0 corpus's
`_metadata.WARNING`.
