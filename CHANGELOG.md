


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
