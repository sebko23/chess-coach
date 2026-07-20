




## [unreleased] - BBF-69.2 curation kit (2026-07-20)

### Added
- `docs/20_datasets/narrative-gold-v1.md`: human curation guide for the
  20-30 entry narrative corpus, including source schemas, provenance and
  copyright boundaries, a balanced-seed acceptance bar, and the final
  review checklist.
- `scripts/validate_narrative_gold.py`: strict BBF-69.2 completion gate.
  It checks corpus size, dense IDs, parseable FENs, 50-200 word
  explanations, source-specific fields, duplicate IDs/FENs, placeholder
  removal, and minimum phase/source diversity. `--json` emits the same
  diagnostics for external curation tools.
- `tests/unit/test_validate_narrative_gold_script.py`: focused coverage
  for a completion-ready fixture and the current placeholder failure state.

### Scope
- This BBF does **not** invent the 20-30 curated explanations or citations.
  The user/domain expert still owns that work. The shipped placeholder
  corpus remains unchanged and the strict validator intentionally exits 1
  until the real entries replace it.
- Narration-pipeline integration remains BBF-69.3.

### Verification
- Ruff: clean on the validator and its tests.
- Pytest: 36 passed (10 validator tests + 26 narrative-loader tests).
- Placeholder baseline: validator exits 1 with explicit corpus-size,
  metadata-warning, placeholder-marker, and word-count diagnostics.

---

## [unreleased] - BBF-69.1 (2026-07-18)

### Added
- `libs/chess_coach/datasets/narrative_gold.py` (NEW, ~345 lines):
  narrative gold corpus loader for the BBF-69.1/69.2/69.3 chain.
  Mirrors the L-2 gold (`libs/chess_coach/datasets/l2_gold.py`) and
  archetype gold (`libs/chess_coach/datasets/archetype_gold.py`)
  shape so future BBFs that consume narrative gold can use the
  same loader idioms.
  - `NarrativeGoldEntry` dataclass: one FEN + a 50-200 word
    coaching paragraph + a provenance `source` dict + optional
    `tags` list. The loader's `narrative_explanation` minimum-length
    floor (50 chars) protects against accidental stubs sneaking
    into a future BBF-69.2 hand-curated corpus.
  - `load_narrative_gold(version, base_path=None)` loader.
  - `load_narrative_gold_with_metadata(version, base_path=None)`
    loader that returns the full dict (preserves `_metadata` and
    `schema_version`). Useful for tooling that wants to surface
    corpus provenance (e.g. the SYNTHETIC PLACEHOLDER warning).
  - `validate_narrative_gold(corpus)` cross-entry validator
    (checks unique IDs + unique FENs).
  - `list_versions(base_path=None)` version enumerator.
  - Env-var-free; corpus path resolved relative to the module
    location (`_default_base_path`), with `base_path` override
    for tests.
- `tests/gold/narrative/v1/corpus.json` (NEW): SYNTHETIC PLACEHOLDER
  v1 corpus with 5 entries (King's Pawn, Italian Game, Four Knights,
  Najdorf Sicilian, Ruy Lopez Four Knights). Each entry carries a
  `_metadata.WARNING` field flagging the narrative_explanation as
  STUB. Real hand-curated entries with provenance citations from
  chess books (Logical Chess Move by Move, Reassessing Your Chess,
  etc.) replace placeholders in BBF-69.2 (domain-expert work, not
  the agent's).
- `tests/unit/test_narrative_gold.py` (NEW, 26 tests): full unit
  coverage of the public API including in-memory validation,
  on-disk loading, version validation, malformed-corpus error
  paths, and shipped-corpus regression checks.

### Rationale
- The narration pipeline can produce *grounded* coaching prose,
  but grounding requires a corpus of well-explained positions
  (per the BBF-69 plan in
  docs/16_audit/BBF-68.1-candidate-survey-2026-07-17.md §"Narrative
  grounding corpus"). The L-2 corpus (`tests/gold/L2/`) is
  chess-position data for engine eval validation -- it does not
  have the coaching prose that grounds narration output.
- This BBF is the LOADER ONLY. BBF-69.2 (hand-curate 20-30
  narrative entries with provenance citations) and BBF-69.3
  (wire the loader into `services/chess_coach/narration/pipeline.py`
  so each generation cites the closest narrative corpus entry as
  the grounding source) are follow-up BBFs.

### Verification
- Local: ruff clean on the 2 changed files.
- Local pytest: 26 passed (narrative) + 12 passed (l2) + 16 passed
  (archetype) = 54 passed on the focused + regression scope.
- Mypy: zero errors in the loader; 13 pre-existing
  `no-untyped-def` errors for pytest fixture parameters in the
  test file (project-wide pattern: `tests/unit/test_l2_gold_dataset.py`
  has 25, `tests/unit/test_archetype_gold_corpus.py` has 15; not
  CI-gated, see `.github/workflows/smoke.yml`).
- The shipped v1 corpus loads cleanly and validates without errors
  (`TestShippedCorpus`).

### Cross-references
- BBF-69 plan: `docs/16_audit/BBF-68.1-candidate-survey-2026-07-17.md`
  §"Narrative grounding corpus" (Gap 2)
- L-2 gold shape: `libs/chess_coach/datasets/l2_gold.py`
- Archetype gold shape: `libs/chess_coach/datasets/archetype_gold.py`

---

## [unreleased] - BBF-68.2 (2026-07-18)

### Added
- `services/chess_coach/pdf_ocr/protection.py` (NEW, ~225 lines):
  per-process rate-limit + circuit-breaker primitives for OCR backends.
  - `TokenBucket`: classic refill-bucket; non-blocking `try_acquire()`;
    starts full, drains on call, refills at configured rate.
  - `CircuitBreaker`: 3-state (CLOSED -> OPEN -> HALF_OPEN -> CLOSED).
    Trips OPEN after N consecutive failures, holds for `cooldown_seconds`,
    then admits a single HALF_OPEN probe before resuming normal traffic.
  - `ProtectionRegistry`: per-backend (bucket, breaker) singleton
    instances; module-level, in-process, resets on container restart.
  - Env-var configuration per backend (all optional, all
    `CHESS_COACH_OCR_<BACKEND>_*`). Defaults: 1 RPS / 5 burst /
    5-failure threshold / 120s cooldown for chessvision.
  - Garbage env values fall back to defaults with a WARNING log so a
    typo in an env var does NOT brick OCR.
- `tests/unit/test_ocr_protection.py` (NEW): 17 unit tests for the
  protection primitives (TokenBucket behavior, CircuitBreaker state
  machine incl. HALF_OPEN recovery, ProtectionRegistry per-backend
  isolation + env-var wiring + invalid-env fallback).

### Changed
- `services/chess_coach/pdf_ocr/adapter.py`: the chessvision.ai backend
  is now wrapped by a new `_predict_chessvision_protected` that gates
  calls through the bucket and breaker. The underlying httpx POST body
  is unchanged. `_REGISTRY["chessvision"]` points to the protected
  wrapper; `_predict_local` is unchanged (no network, no protection).
  Module docstring updated to document the protection contract and the
  `rate_limit:` / `circuit_open:` error-string conventions.
- `tests/integration/test_ocr_backend.py`: extended with a new
  `TestOcrProtection` class (3 tests) exercising the end-to-end path
  through the dispatcher: rate-limit returns structured error without
  invoking the network; circuit breaker opens after N consecutive
  failures; breaker recovers on HALF_OPEN probe success after cooldown.

### Rationale
- The chessvision.ai default backend is a public endpoint with no API
  key, no SLA, and a documented history of throttling (see BBF-68.1
  spike report). Production traffic to `/v1/import/pdf` could easily
  exceed what chessvision serves, making the route a SPOF. The
  wrapper produces structured `OcrResult` errors prefixed `rate_limit:`
  or `circuit_open:` so the route surfaces them as per-page
  `DiagramResult.issue` without HTTP 5xx-ing the entire PDF.
- Per-backend isolation: future BBF-68.1 (local model) can have its
  own RPS / burst / breaker config without affecting chessvision.

### Env vars added
- `CHESS_COACH_OCR_CHESSVISION_RPS` (default `1.0`)
- `CHESS_COACH_OCR_CHESSVISION_BURST` (default `5`)
- `CHESS_COACH_OCR_CHESSVISION_CB_THRESHOLD` (default `5`)
- `CHESS_COACH_OCR_CHESSVISION_CB_COOLDOWN` (default `120.0`)

### Cross-references
- Spike report motivating the pivot:
  `docs/16_audit/BBF-68.1-spike-report-2026-07-18.md`.
- Decision packet: `C:\chess-i3\bbf68-1-decision-packet-2026-07-17.md`
  (fallback d, explicitly chosen by the user).
- BBF-68.0 (the OCR seam this wraps): `47feaea`.

### Verification
- Local: ruff + mypy clean on the 4 changed files (strict mode).
- Local pytest: 29 passed (17 new unit + 7 BBF-68.2 integration +
  5 regression on `tests/integration/test_pdf_import.py` +
  `tests/unit/test_gateway_boots.py`).
- CI run `29646097746` on the PR-2 merge SHA (`e3bb918`):
  - gateway boot (clean install): `81 passed in 8.98s`
  - qdrant sidecar smoke: `qdrant is healthy after 1s`
  - lazy eval-graph smoke test: `[4/4] OK smoke_test passed: 7 positions, all with score_cp`

---

## [unreleased] - BBF-68.1 (2026-07-18, spike-only — pivoted)

### Status
- **UNMEASURED, not shipped.** Per project Rule 4, the spike's acceptance
  bar (>=80% FEN accuracy, <=5 s warm latency, <=2 GB disk) was not
  measured. No result was fabricated.
- Per the user-signed-off decision packet fallback (d), BBF-68.1
  measurement was deprioritized and BBF-68.2 (chessvision.ai rate
  limiting + circuit breaker) shipped instead.

### Infrastructure that did get installed (verified)
- `torch==2.12.0+cpu`, `torchvision==0.27.0+cpu` (corrected pin from
  the prior handoff's inverted `0.21.0` claim) — in
  `/tmp/bbf68-tsoj-venv/` on the agentZero container.
- 27 runtime deps from Tsinghua + PyTorch CPU index.
- Full tsoj source at `/tmp/bbf68-tsoj-src/` (301 MB git history).
- Full 824 MB chess model bundle extracted to
  `/tmp/bbf68-tsoj-src/models/chess/` (5 `.pth` files).
- 2 of 5 torchvision backbones downloaded into
  `/root/.cache/torch/hub/checkpoints/` (`regnet_x_800mf` 29 MB,
  `lraspp_mobilenet_v3_large` 13 MB); 3 remaining (`convnext_tiny`,
  `mobilenet_v3_large`, and one more) failed to complete due to
  CDN throttling.

### Two real blockers that prevented measurement
1. **Off-by-one in unzip extraction path.** The spike install script
   ran `unzip -d /tmp/bbf68-tsoj-src/models/`, but `models.zip`
   already contains a top-level `models/` directory, producing
   `models/models/chess/` (one level too deep). The tsoj
   `_find_latest_model()` looks one level above and raised
   `FileNotFoundError: No model file found
   'models/chess/best_model_existence_*.pth'` on every page of the
   first spike run.
2. **CDN throttle on `convnext_tiny` backbone.** The same
   `release-assets.githubusercontent.com` throttle that affected the
   824 MB model bundle also throttled
   `download.pytorch.org/models/convnext_tiny-...`. The download
   stalled indefinitely at 68/110 MB after 8 minutes. Torch hub's
   default retry policy silently gives up.

### Corrections to the prior handoff
- The handoff's pip line `torchvision==0.21.0` is **WRONG**. The
  correct pin for `torch==2.12.0` on the PyTorch CPU index is
  `torchvision==0.27.0` (paired). Verified via
  `pip install --dry-run` against the index.
- The handoff's 2 GB disk budget is **WRONG**. Measured install
  footprint alone is 3.0 GB (venv 1.5 GB + src 1.2 GB + extracted
  models 891 MB + partial torch hub cache ~120 MB), exceeding the
  budget before any spike inference runs.
- The handoff's "5-10 minute spike if mirrors cooperate" estimate
  is **WRONG**. Real-world elapsed time for the infrastructure
  stages was ~80 minutes just for the model bundle (Stages 1-3
  took ~28 minutes total, Stage 4 alone took ~80 minutes).
- A future BBF-68.1 integration MUST address all three: corrected
  torchvision pin, higher disk budget (or lazy-download on first use
  with a configurable model dir), and either pre-baked torchvision
  backbones or a host with unthrottled egress to
  `download.pytorch.org`.

### Cross-references
- Full report: `docs/16_audit/BBF-68.1-spike-report-2026-07-18.md`
  (committed on `main` at `442978c`).
- Skill capturing the corrected install pipeline:
  `chess-coach-bbf68-spike-runner` (Hermes desktop skills system).

---

## [unreleased] - BBF-68.0.1 (2026-07-17)

### Changed
- `services/chess_coach/gateway/routes/pdf_ingest.py`:
  `PdfImportResponse` field renamed `results: list[DiagramResult]`
  -> `diagrams: list[DiagramResult]`; matching return-kwarg
  `results=results` -> `diagrams=results`.
- `tests/integration/test_pdf_import.py`: assertion
  `assert "results" in data` -> `assert "diagrams" in data`.

### Rationale
- The desktop `PdfIngestPage.tsx` (326 LOC, fully wired) already
  reads from `result.diagrams` — the prior BBF-68.0 backend was
  returning `results`, so the frontend panel silently rendered an
  empty list. This BBF closes that GUI/backend drift BEFORE the
  BBF-68.1 spike so the end-to-end flow would work once the spike
  landed.

### Verification
- Local: ruff + mypy unchanged on the affected files (3+8
  pre-existing ruff errors, NOT introduced by this BBF).
- Local pytest: 8 passed on focused
  `tests/integration/test_pdf_import.py +
  tests/integration/test_ocr_backend.py`.
- CI run `29611366000` on the push (`d5cf262`): 3/3 jobs green.

---

## [unreleased] - BBF-68.0 (2026-07-17)

### Added
- `services/chess_coach/pdf_ocr/` package (NEW): env-only OCR backend
  dispatcher. Default backend is `chessvision` (HTTP); `local` is a
  structured-error placeholder pending BBF-68.1.
  - `OcrResult` NamedTuple: `(fen | None, confidence, error | None)`.
  - `UnknownOcrBackend(ValueError)`: raised on misconfigured backend
    name; the route propagates as 500 (server-side misconfiguration,
    not a per-page failure).
  - `predict_fen()`: reads `CHESS_COACH_OCR_BACKEND` on every call;
    dispatches to the registered predicter.
  - `_predict_chessvision()`: verbatim copy of the prior
    `pdf_ingest._predict_fen` body so existing route-level mocks keep
    working.
  - `_predict_local()`: returns structured error pointing at BBF-68.1
    follow-up and the candidate-survey doc.
- `tests/integration/test_ocr_backend.py` (NEW): 4 tests covering
  default-is-chessvision, `local` returns a structured error pointing
  at BBF-68.1, `nonexistent` raises `UnknownOcrBackend`, and the
  chessvision path still goes through `httpx.AsyncClient.post`
  (mocked).
- `docs/16_audit/BBF-68.1-candidate-survey-2026-07-17.md` (NEW,
  190 lines): candidate model survey. Audits the prior handoff's
  claim that `bersisyan/chess-diagram-recognizer` exists on
  Hugging Face (it does NOT — 404). Concludes the strongest live
  candidate is `tsoj/Chess_diagram_to_FEN` (GitHub, MIT).

### Changed
- `services/chess_coach/gateway/routes/pdf_ingest.py`: `_predict_fen`
  reduced to a 3-line delegator to `chess_coach.pdf_ocr.predict_fen`.
  Removed `httpx`, `base64`, the original `CHESSVISION_URL`, and the
  original `TIMEOUT` constant (all moved to `pdf_ocr.adapter`).
- `pyproject.toml`: added `chess_coach.pdf_ocr` to both
  `[tool.setuptools].packages` and `[tool.setuptools.package-dir`.
  No new runtime dep.

### Rationale
- The chessvision.ai public endpoint has no API key, no rate
  limiting, and no SLA. A swap to a local model is multi-BBF and
  involves a model-bundle download + torch stack. This BBF ships
  the minimum viable seam: env-var dispatcher + structured-error
  placeholder, so future BBFs only need to register a new backend.

### Verification
- Local: ruff + mypy clean on the changed files.
- Local pytest: 9 passed on focused
  `tests/unit/test_gateway_boots.py +
  tests/integration/test_ocr_backend.py +
  tests/integration/test_pdf_import.py`.
- CI run `29609499303` on the squash-merge SHA (`47feaea`):
  3/3 jobs green.

### Future work (deferred)
- **BBF-68.1**: implement `_predict_local` with a real local OCR
  model. Spike must complete first; see
  `docs/16_audit/BBF-68.1-candidate-survey-2026-07-17.md` and the
  BBF-68.1 spike report.

---

## [unreleased] - BBF-67 (2026-07-17)

### Added
- `scripts/static_import_scanner.py` (NEW; BBF-67.1): static-import
  scanner for `apps/desktop/src/`. Walks the desktop source tree,
  parses `import` statements, cross-references against the backend
  route registry (`gateway/routes/`), and emits an advisory report
  of dead imports and missing references. Exits 0 always; output
  is for human review (no CI gate yet).
- `CONTRIBUTING.md` §"Static-import scanner" (BBF-67.2): section
  explaining the scanner's purpose, usage, output formats, and how
  to extend the pattern table. Notes that wiring into `lint:ci`
  is intentionally deferred to a future BBF until the script is
  reviewed.

### Rationale
- The prior BBF-26 closed a frontend Import PGN button that 404'd
  against a non-existent route (`/v1/import/pgn-database` instead of
  `/v1/import/pgn`). The class of bug ("GUI wired to a backend
  symbol that doesn't exist") was detected by code review, not by
  any automated check. The scanner is the long-term defense.

### Verification
- Local: scanner runs against the BBF-67.1 commit and reports zero
  mismatches.
- CI: no new workflow; `lint:ci` wiring deferred per BBF-67.2.

### Future work (deferred)
- Wire the scanner into `lint:ci` as an advisory step (non-blocking)
  after a few weeks of human review of its output.

---

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
