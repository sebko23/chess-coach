# BBF-89 — Deferred (hand-curated seed corpus, requires human curator)

**Status (2026-08-02):** DEFERRED-item CLOSED. The minimal hand-curated
seed (5 narratives + 2 archetype profiles) was supplied by the human
curator (the maintainer) on 2026-08-02 and shipped as the
`hand-curated-v0` corpus (see status history below). The ORIGINAL
deferral reasoning still stands for the FULL corpus: a complete
20-30/20-40 hand-curated corpus remains human-curator work that an LLM
must not fabricate. The full-curation gap documented here is partially
closed; the remaining work is growing the seed to full completion.

Original deferral rationale (preserved for the audit trail):

The proposed commit-mc
strategy (use a LLM to fabricate 5 narratives with provenance
citations to chess books and GM games, plus 2 archetype
profiles) is structurally unsound:

## Why this BBF is deferred

Per `docs/20_datasets/narrative-gold-v1.md` Acceptance Bar §4:

> "Precise provenance. Cite the source precisely enough that
> another curator can locate it. **Never guess a title, author,
> chapter, page, game, event, year, or URL.**"

This is human-curatorial work. The LLM cannot produce real
chess-book page citations, attest to a specific GM game's year
without verification, or confirm a chapter ordering without
looking at the book. Producing fabricated provenance to satisfy
the brief would:

- Violate the brief's own acceptance bar.
- Ship a PR with made-up page numbers that future curators
  would have to rewrite.
- Pollute the `narrative_gold` corpus with invented content
  that the system would then cite as ground truth (a particularly
  bad failure mode for a "narrative grounding" dataset).

This BBF is held back at Tier 4 in v2 handoff §13.3 for exactly
this reason: the queue was authored by an external reviewer
who understood that hand-curatorial work cannot be done by a
machine.

## What already exists (production state)

- **`tests/gold/narrative/v1/corpus.json`** (synthetic placeholder,
  5 entries, auto-generated stubs) — shipped in BBF-69.1 as the
  initial corpus to test the loader. NOT for production use; clearly
  marked `WARNING: SYNTHETIC PLACEHOLDER`.
- **`tests/gold/narrative/v2/corpus.json`** (auto-derived from real
  Lichess PGNs, BBF-87, prose is template-generated, positions
  are real) — shipped in BBF-87 as an interim corpus that uses real
  positions with template prose. The template prose is clearly
  flagged as auto-generated; the `narrative-gold-v1.md` doc
  explains the auto-derivation pipeline (Lichess PGN exports of
  `ebassti` self-play and Fischer's *My 60 Memorable Games*).
  NOT for production narrative-grounding use; clearly marked
  `WARNING: AUTO-DERIVED PLACEHOLDER`.
- **`tests/gold/archetypes/v1/corpus.json`** (synthetic placeholder,
  14 entries, 2 per `STANDARD_ARCHETYPES` archetype) — shipped in
  BBF-66 as the initial corpus to test the kNN classifier. The
  kNN implementation is real (`services/chess_coach/profile/archetypes.py`
  `_knn_classify` function); the corpus it scores against is the
  synthetic placeholder, clearly marked `WARNING: SYNTHETIC
  PLACEHOLDER`.

## What BBF-89 will produce (when a human curator picks it up)

Per the brief: **minimal hand-curated seed (5 narratives, 2 archetype profiles)**.

This is the minimal viable hand-curated seed that the auto-derived
or synthetic placeholders are intended to be replaced with over
time. The full release-ready corpus would be 20-30 entries per
the v1 doc's Acceptance Bar §7, but the brief asks for the minimal
5-entry version to start.

## Hand-curator handoff (production workflow)

The minimal workflow for a human curator:

### Phase 1: Read the curated guide

1. `docs/20_datasets/narrative-gold-v1.md` (§Goal, §Acceptance
   Bar, §Entry Schema, §Source Types).
2. Existing `narrative_gold` corpus structure
   (`tests/gold/narrative/v1/corpus.json`) — for reference, not
   as content to copy.

### Phase 2: Pick positions (5 narratives)

For each of the 5 entries:

1. Pick a well-known position (FEN) that illustrates a concrete
   lesson — opening, middlegame, tactical, or endgame.
2. Write a 50-200 word ORIGINAL coaching explanation.
   - Paraphrase, in your own words.
   - Do not paste long passages.
   - Focus on what matters, why it matters, what plan/decision
     the student should understand.

### Phase 3: Cite provenance PRECISELY

For each entry:

- If the source is a book: title, author, chapter, **exact page**
  in the cited edition, edition (publisher + year). Page numbers
  are edition-specific; the curator must look at the actual page
  to cite accurately.
- If the source is a GM game: title (White - Black), author
  (annotator name), event, year, round (when known), URL
  (when online).
- **Never guess** any of these. If unsure, leave the field
  blank and mark the entry `NEEDS-SOURCE`; a second-pass
  curator can fill it in.

### Phase 4: Validate and place

1. Run `scripts/validate_narrative_gold.py` to check schema,
   FEN validity, duplicate IDs, duplicates-by-FEN.
2. Add the 5 entries to
   `tests/gold/narrative/hand-curated-v0/corpus.json` (a new
   versioned directory; do NOT modify v1 or v2).
3. Run `tests/unit/test_narrative_gold.py` to confirm the new
   corpus loads cleanly.

### Phase 5: 2 archetype profiles

1. Pick 2 real Lichess-game metric vectors (or hand-construct
   2 plausible metric vectors from strong-player knowns).
2. Label each with a confident archetype from `STANDARD_ARCHETYPES`
   (`Tactician`, `Positional Player`, `Grinder`, `Wildcard`,
   `Specialist`, `Tilter`, `Endgame Specialist`).
3. Add to `tests/gold/archetypes/hand-curated-v0/corpus.json`.
4. Validate via `scripts/validate_archetype_gold.py`.

### Phase 6: Wire up the loader (if needed)

The current loader (`libs/chess_coach/datasets/narrative_gold.py`)
defaults to v2 (auto-derived). For the hand-curated corpus, the
loader needs to support a version parameter (or a separate
loader function) that points to the hand-curated directory. This
is a small refactor — separate BBF.

## Why this doc exists

This doc is the BBF-89 work product. The absent artifacts (5
narratives, 2 archetype profiles) are honest-deferred. The
hand-curator handoff above is what someone needs to know to pick
this up when they have time + chess domain expertise + access to
the relevant books/GMs.

## Status history

- **2026-07-XX:** Tier 4 in v2 handoff §13.3 (held back).
- **2026-08-02:** This BBF (bbf-89) shipped as the honest-deferral
  record + hand-curator handoff.
- **2026-08-02 (later session):** The human curator supplied the minimal
  hand-curated seed (5 narratives + 2 archetype profiles). It shipped as
  the `hand-curated-v0` corpora with a new `provenance ==
  "hand_curated_seed"` validator/loader mode:
  - `tests/gold/narrative/hand-curated-v0/corpus.json`
  - `tests/gold/archetypes/hand-curated-v0/corpus.json`
  - Loader + validator relaxed mode in
    `libs/chess_coach/datasets/narrative_gold.py`,
    `libs/chess_coach/datasets/archetype_gold.py`,
    `scripts/validate_narrative_gold.py`,
    `scripts/validate_archetype_gold.py`.
  Record: `docs/16_audit/bbf-89-hand-curated-seed-record.md` (untracked).
  Documented NEEDS-SOURCE gaps (curator did not supply): L3/L4/L5
  `source.chapter`. Remaining work to reach full completion (20-30
  narratives, 20-40 archetypes with >=2 per label) is human-curated
  growth, not LLM work.

## Cross-references

- `docs/20_datasets/narrative-gold-v1.md` — the curated guide.
- `tests/gold/narrative/v1/corpus.json` — synthetic placeholder.
- `tests/gold/narrative/v2/corpus.json` — auto-derived corpus.
- `tests/gold/archetypes/v1/corpus.json` — archetype synthetic.
- `libs/chess_coach/datasets/narrative_gold.py` — corpus loader.
- `libs/chess_coach/datasets/archetype_gold.py` — archetype loader.
- `scripts/curate_narrative_gold_auto.py` — auto-derivation pipeline.
- `scripts/curate_archetype_gold_auto.py` — auto-derivation pipeline.
- `scripts/validate_narrative_gold.py` — validator.
- `scripts/validate_archetype_gold.py` — validator.
- v2 handoff §13.3 (Tier 4 list).
