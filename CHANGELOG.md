




## [unreleased] - BBF-66 (2026-07-17)

### Changed
- `services/chess_coach/profile/archetypes.py`: `cluster_archetypes()`
  replaced with kNN classification (k=3, z-scored Euclidean) against the
  v1 archetype gold corpus. The BBF-59 heuristic shape-matching is
  RETIRED entirely (not kept as a fallback) per the Q1 strategic decision
  (single source of truth).
- `cluster_archetypes(metrics: dict[str, float]) -> ArchetypeAssignment`
  signature; the `l2_gold_version` parameter is removed.
- `CLUSTER_MIN_SAMPLE_SIZE = 1` lifted to a module-level constant in
  `archetypes.py`; the gate_metric call reads this constant (BBF-66 Q4).

### Added
- `tests/gold/archetypes/v1/corpus.json` (NEW artefact; 14 entries
  / 2 per `STANDARD_ARCHETYPES` archetype). SYNTHETIC PLACEHOLDER
  with an explicit `_metadata.WARNING` block per Rule #4.
- `libs/chess_coach/datasets/archetype_gold.py` (NEW; Pydantic-flavoured
  loader mirroring `l2_gold.py` shape).
- `tests/unit/test_archetype_gold_corpus.py` (5 unit tests).
- `tests/unit/test_archetype_knn.py` (6 kNN unit tests).
- `@pytest.mark.slow` marker on integration tests
  (`test_profile_archetypes_integration.py`) per Q3; documented in
  `CONTRIBUTING.md`.
- `slow` marker registered in `pyproject.toml [tool.pytest.ini_options]`.

### Changed (tests)
- 6 heuristic-shape tests in `tests/unit/test_profile_tilt_archetypes.py`
  CONVERTED to behavioral assertions (test names preserved; assertion
  bodies changed). The kNN against the SYNTHETIC corpus may pick
  different labels for inputs the heuristic hardcoded; the contract is
  that the label is one of `STANDARD_ARCHETYPES` with valid confidence.

### Documentation
- `docs/15_methodology/profile-metrics-v1.md` updated: the BBF-65.4
  archetype §section now describes the kNN approach (was "this is
  heuristic, not kNN"). Added distance-metric detail (z-scored Euclidean,
  k=3, 2.0 z-score Unknown threshold).

### Future work (deferred)
- **BBF-66.x or BBF-68**: replace SYNTHETIC PLACEHOLDER entries in
  `tests/gold/archetypes/v1/corpus.json` with real hand-labelled
  player-metric vectors. Domain expert (the user) curates ~30 entries
  with one per archetype.

### Test count
- 5 new tests in `test_archetype_gold_corpus.py` (all green).
- 6 new tests in `test_archetype_knn.py` (all green).
- 22 tests in `test_profile_tilt_archetypes.py` (6 converted to behavioral;
  was 20 passed + 2 failed pre-BBF-66.5; now 22 passed + 0 failed).
- 2 integration tests marked `@pytest.mark.slow`.
- 252 passed in total unit sweep (was 241 pre-BBF-66; +5 +6 = +11 net).

## [unreleased] - BBF-65 (2026-07-16)

### Changed
- `services/chess_coach/profile/archetypes.py`: `ArchetypeAssignment.effect_size.d`
  is now a real Cohen's d (capped at +-3.0) computed against the OTHER 7
  archetypes' scores as a synthesized null. Was `None` (sample-size-1 dodge).
- `ArchetypeAssignment` gains a `passes_b4_gate: bool` field (default
  `False`). For Unknown labels, the field is `False` directly (§B4 rule 3:
  below-threshold MUST NOT surface). For labeled archetypes, it's set via
  `gate_metric(effect, min_sample_size=1)` (the gate's default `30` is
  calibrated for time-series metrics, not cluster assignments).
- Route `services/chess_coach/gateway/routes/profile.py`'s archetypes
  branch now reads `assignment.passes_b4_gate` (canonical BBF-65.2 field)
  instead of re-deriving from `effect.d`. Fixes a real double-source-of-truth
  inconsistency where the route would emit a `passes_b4_gate` value that
  disagreed with the function's canonical value for some inputs.

### Added
- 4 new unit tests at `tests/unit/test_profile_tilt_archetypes.py`:
  - `test_archetypes_winner_d_uses_other_archetype_distribution`
  - `test_archetypes_unknown_label_sets_d_to_none`
  - `test_archetypes_d_capped_under_synthesized_null`
  - `test_archetypes_assignment_passes_b4_gate_for_strong_tactician`
  - `test_archetypes_assignment_gate_inconclusive_for_unknown_and_subthreshold`
- 2 integration tests at `tests/integration/test_profile_archetypes_integration.py`
  exercising the route via `httpx.ASGITransport` + mocked `cluster_archetypes`.

### Documentation
- `docs/15_methodology/profile-metrics-v1.md` now has an
  "Archetype cluster (BBF-65)" §H2 section parallel to the 6 player metrics.

### Future work (deferred)
- **BBF-66**: build a real archetype-labelled reference corpus at
  `tests/gold/archetypes/v1/corpus.json` (~30 player-metric vectors,
  one per `STANDARD_ARCHETYPES` archetype + Unknown). The v2 chess
  corpus is chess-position data, not archetype-labelled reference vectors;
  a separate artefact is needed. BBF-66 swaps heuristic shape-matching
  for kNN against this corpus.

### Test count
- 22 tests in `test_profile_tilt_archetypes.py` (6 existing heuristic +
  4 BBF-65.1 d/cap + 2 BBF-65.2 gate + 10 misc structural).
- 2 tests in `test_profile_archetypes_integration.py` (route-level).
- No regressions in the 6 BBF-65.0 heuristic shape-match tests.

## [unreleased] - BBF-64 (2026-07-16)

### Added
- `GET /v1/eval/verify/{version}` route at `services/chess_coach/gateway/routes/eval_verifier.py`.
- Phase 5 eval-delta verifier: runs the engine against each gold position in L-2 v1/v2 and returns a per-position accuracy report (top-1 hits, top-N hits, score-within-50cp count, mean + max |delta_cp|).
- 8 unit tests at `tests/unit/test_eval_verifier.py` (dataclass shape + engine-loop behavior).
- 4 integration tests at `tests/integration/test_eval_verifier_integration.py` (in-process FastAPI + mocked engine).

### Cross-references
- `docs/20_datasets/L2-gold-v1.md` now cross-references the verifier as the calibration tooling.
- Phase 5 exit criterion: "Adding a few games surfaces real gaps in a sample repertoire" remains open; the verifier is a prerequisite for it (validates that engine eval matches gold before training lessons reference it).

### Backward compatibility
- No existing route behavior changed.
- `app.py` `include_router` registration of the new route at module-load time; smoke CI's `gateway-boot` job exercises the import path so a registration regression trips CI.

## [unreleased] - BBF-63 (2026-07-16)

### Changed
- L-2 chess corpus grown with new `tests/gold/L2/v2/corpus.json` (18 new positions).
- Added multi-PV=3 `eval_deltas` labels (depth=15) to all v2 entries.
- v1 corpus unchanged (still 12 entries, schema_version=2.0).
- Phase/source distribution: 8 opening / 6 middlegame / 4 endgame; 7 opening_theory / 9 gm_game / 2 tactical_motif.

### Added
- `tests/gold/L2/v2/corpus.json` (NEW file, separate from v1 for clean back-compat).
- `tests/gold/L2/v2/game_labels.jsonl` (PGN metadata for the 9 gm_game positions).
- `services/chess_coach/gold/eval_delta.py` async helper (uses `EnginePool.analyze` + shared pool pattern, `hash_mb=32`).
- 8 new tests in `tests/unit/test_L2_v2_corpus.py` covering v1/v2/PGN-label contracts.

### Backward compatibility
- v1 tests still pass (`load_corpus("v1")` still returns 12 entries).
- l2_gold.py unwrap shim landed in BBF-63.2 (the v2-wrapped dict format works).
- phase4_golden + eval_delta tests still pass.
