# L-2 Gold Set v1 -- Spec

**Status:** v1, initial seed. Created in BBF-49 (2026-07-15).
**Path:** `tests/gold/L2/v1/corpus.json` (a single JSON file with one
array of position objects).
**Loader:** `chess_coach.datasets.l2_gold` (re-exported from
`libs/chess_coach/datasets/l2_gold.py`).

## What "L-2 gold" means for this project

L-2 gold is a small, versioned, **labeled** corpus of chess
positions. The "L-2" name follows the v2 roadmap's nomenclature
("L-2" was originally a level-of-analysis tag, kept here for
continuity with the existing `tests/gold/chess_gold_set_v1.json`
file which uses a similar naming pattern).

**It is NOT a database of master games.** Master games are
useful for stylistic and opening-theoretic analysis, but they
are not the right shape for the project: we are building a
Stockfish-backed analysis tool, so the gold set is engineered
to validate engine output, not to teach human play.

**It is NOT a perft or move-generation test set.** That is what
`tests/gold/chess_gold_set_v1.json` is for. L-2 gold is a
complement: perft validates "does the engine see the right
moves", L-2 gold validates "does the engine see the right
**values**".

## Quality bar

Each position in L-2 gold must satisfy **all four** of:

1. **Reachable from a real game.** No synthetic positions that
   no human player would encounter. The position is from
   either a GM-level tournament game (preferred) or a
   well-known opening theory line. The `source` field on each
   entry records the origin game and the move sequence that
   reached the position.
2. **Engine-evaluated at depth 25 with Stockfish 18.** The
   `best_move_uci` and `score_cp` labels are the result of a
   single Stockfish 18 `go depth 25` call on the position,
   with a fixed MultiPV=1, fixed hash size, and the engine's
   own time/thread defaults. No human override. The labels
   are reproducible: running the same engine call against the
   same FEN should produce the same `best_move_uci` and a
   `score_cp` within +/- 5 centipawns of the recorded value.
3. **Phase-tagged.** Every position has a `phase` field
   ("opening", "middlegame", or "endgame") so consumers
   (Phase 4 metrics, Phase 6 model eval) can slice the
   corpus. Phase boundaries: opening = moves 1-15,
   middlegame = moves 16-40, endgame = move 41+ OR any
   position with both sides having <= 7 non-pawn pieces
   (whichever comes first).
4. **Sanity-checked for engine stability.** A position where
   Stockfish 18 depth 25 returns `score_cp` > 1500 (i.e.
   the position is completely winning for one side) is
   excluded from the gold set unless the position is the
   canonical "mate-in-N" teaching position for that
   pattern. This keeps the gold set focused on the
   "interesting middle" where engine evaluation is
   non-trivial.

**The bar is engine-eval-based, not human-curated, by
deliberate choice.** A human-curated bar would require
a GM annotator whose time we do not have. The
engine-eval bar is reproducible by any future contributor
who can run Stockfish 18 with a fixed config, and it is
exactly the same signal that the production eval-graph
route produces, so the gold set is a true eval-test of
the production engine path.

## Source types

L-2 gold v1 has three source types, in priority order:

- **GM game position** (preferred): a position from a
  well-known GM tournament game. The `source` field records
  the players, event, year, round, and the PGN move list
  that reached the position.
- **Opening theory position**: a position from a standard
  opening line (Italian, Ruy Lopez, Sicilian Najdorf, etc.).
  Used to validate that the engine agrees with the
  theoretically-known best move for the position. The
  `source` field records the opening name and ECO code.
- **Tactical motif position**: a position that demonstrates
  a specific tactical pattern (fork, pin, skewer, discovered
  attack, etc.). Used to validate that the engine finds the
  tactic. The `source` field records the motif name and a
  reference to the position's source game or constructed
  from-scratch status.

All three source types are reachable from a real game by
criterion (1) above. Synthetic-from-scratch positions are
NOT in L-2 gold; they go in a different test set (not yet
created, see Future work below).

## Label schema

Each position in `corpus.json` is a JSON object with the
following required fields:

```json
{
  "id": "L2-v1-0001",
  "fen": "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
  "phase": "opening",
  "best_move_uci": "e1g1",
  "score_cp": 25,
  "source": {
    "type": "opening_theory",
    "name": "Four Knights, Italian Variation",
    "eco": "C50",
    "move_sequence": "1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.O-O"
  },
  "engine": {
    "name": "Stockfish",
    "version": "18",
    "depth": 25,
    "multipv": 1,
    "hash_mb": 64
  },
  "tags": ["opening", "castling", "development"]
}
```

Field-by-field:

- `id` (string, required, unique within the corpus):
  format `L2-v1-NNNN` where NNNN is a zero-padded 4-digit
  sequence number. The `v1` is the corpus version, baked
  into the ID so a v2 corpus can use `L2-v2-NNNN` without
  collision.
- `fen` (string, required): standard FEN. No move counters
  in the FEN; the FEN string is parsed by `chess.Board(fen)`.
- `phase` (string, required, one of `opening`, `middlegame`,
  `endgame`): see Quality bar criterion (3) for the
  boundary rules.
- `best_move_uci` (string, required): the engine's best
  move in UCI notation (e.g. `e2e4`, `e1g1`, `e7e8q`).
  MUST be a legal move from the FEN.
- `score_cp` (integer, required): the engine's evaluation
  in centipawns, from the side-to-move's perspective
  (positive = good for side to move, negative = bad).
  `mate_in_N` is not a valid value for this field; record
  a mate as `score_cp = 30000 - N` (the project's existing
  convention; see `services/chess_coach/engine_orch/pool.py`).
- `source` (object, required): the origin of the position.
  Has `type` (one of `gm_game`, `opening_theory`,
  `tactical_motif`), and a `type`-specific payload. The
  full schema is in `tests/gold/L2/v1/SCHEMA.md`.
- `engine` (object, required): the engine config used to
  produce `best_move_uci` and `score_cp`. Recording the
  config makes the labels reproducible: a future
  contributor can re-run the same engine call and verify
  the labels still match.
- `tags` (list of strings, optional, may be empty): free-form
  tags for slicing (e.g. `["tactics", "fork", "knight"]`).
  Consumers SHOULD NOT rely on a specific tag vocabulary;
  new tags can be added without bumping the corpus version.

## Versioning

Versions are `v1`, `v2`, etc. A new version is required
when ANY of the following changes:

- The label schema (any required field added, removed, or
  renamed).
- The engine config defaults (e.g. Stockfish 18 -> Stockfish
  19, or depth 25 -> depth 30).
- The quality bar (e.g. "reachable from a real game" -> some
  other criterion).

A version bump does NOT require a re-run of the existing
engine calls; existing labels remain valid as long as the
engine config is recorded. The `engine` field on each
position is the source of truth for what produced the
labels.

Additions to an existing version (new positions with the
same schema) are allowed without a bump. The new positions
get the next available `L2-v1-NNNN` ID.

## How to add a new position

1. Choose the source (GM game / opening theory / tactical
   motif). For GM games, the move list that reached the
   position is required in `source.move_sequence`.
2. Run Stockfish 18 depth 25 on the FEN with the engine
   config in `engine` (record the actual config you used
   in the entry's `engine` field). Capture `best_move_uci`
   and `score_cp` from the engine's output.
3. Add the JSON object to `corpus.json`. IDs are dense
   (0001, 0002, 0003, ...) for v1; pick the next available
   integer.
4. Run `pytest tests/unit/test_l2_gold_dataset.py`. The
   test suite validates the new entry's schema and
   engine-call reproducibility (the test re-runs the
   engine call on a small sample of positions and asserts
   `best_move_uci` and `score_cp` match within tolerance).
5. Commit. The CI smoke workflow does not run the gold
   set's engine calls (they take ~10s per position at
   depth 25, so 100 positions = 17 minutes); the unit test
   suite samples 5 random positions from the corpus and
   re-runs the engine to verify reproducibility.

## Future work (not in v1)

These are explicitly deferred to a future L-2 gold version,
not a v1 task:

- **Tactical motif positions constructed from scratch.** v1
  only includes reachable-from-real-game positions. A
  future version may add a constructed-positions corpus
  with a different quality bar.
- **Multi-PV labels.** v1 records the engine's single best
  move at depth 25. A future version may record the top-N
  moves and their scores, for use in training a move
  predictor or in eval-graph "what's the engine's second
  choice" features.
- **Eval-delta labels.** v1 records the static evaluation
  of a position. A future version may record the eval
  delta from the previous move, to support blunder-detection
  training (Phase 4's pattern metrics).
- **PGN game-level labels.** v1 is position-level only. A
  future version may add game-level labels (game result,
  average eval, opening ECO) for Phase 5's repertoire
  analysis.
- **A loader that exposes the corpus as a SQL fixture.**
  The current loader returns a list of Python dataclasses.
  A future version may emit a SQLite fixture file that can
  be loaded into the gateway's database for integration
  testing.

## Out of scope

- **Master game database.** A full Lichess/Chess.com dump
  is not part of L-2 gold; it's a separate concern (Phase
  7's sync work) and would be a multi-GB dataset, not a
  versioned small corpus.
- **Human-annotated commentary.** The "grounded LLM
  commentary" feature in Phase 1 uses LLM-generated prose,
  not a human-curated gold standard. L-2 gold records
  engine labels, not commentary.
- **Game-theory-optimal (GTO) move tables.** Some openings
  have published GTO move tables for specific positions.
  L-2 gold v1 records the engine's best move at depth 25,
  not a GTO table. A future version may add a
  `gto_move_uci` field for cross-reference.

## Why this lives in `tests/gold/L2/`

The existing `tests/gold/chess_gold_set_v1.json` is a
perft-style move-generation test set, added in BBF-15. L-2
gold is a different kind of gold (engine-eval, not
move-generation), so it lives at `tests/gold/L2/` to keep
the two corpora separate. The `L2/` directory will hold
L-2 gold versions (`v1/`, `v2/`, etc.); future L-2
versions stay in their own version subdirectory.

The `tests/gold/` path is intentional: the gold set is
test data, not production data. It is checked into git so
the corpus is versioned alongside the code that uses it.
It is read-only at runtime (the loader reads it but never
writes to it).

## Calibration tooling

The `GET /v1/eval/verify/{version}` route (BBF-64) runs the engine
against each position in this corpus and reports per-position accuracy.
This is the calibration baseline for Phase 6 model work and the
regression test for engine eval drift. See:

- Route module: `services/chess_coach/gateway/routes/eval_verifier.py`
- Unit tests: `tests/unit/test_eval_verifier.py`
- Integration tests: `tests/integration/test_eval_verifier_integration.py`
- Plan: `.hermes/plans/2026-07-16_163115-bbf64-phase5-eval-delta-verifier.md`

**Response shape** (from BBF-64): `VerifyResponse` with `corpus_version`,
`summary` (total / top1_hits / top3_hits / score_within_50cp / mean_delta_cp_abs / max_delta_cp_abs),
and a `positions` list of `PositionReport` (id, fen, gold_move_uci, gold_score_cp,
engine_top_move_uci, engine_top_score_cp, delta_cp, status).
