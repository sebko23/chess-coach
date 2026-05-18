# Implementation Roadmap

Phases are **gated** — each phase has explicit exit criteria. Nothing proceeds past a gate without those criteria being met (and ideally signed off by the user / external review).

## Phase 0 — Architecture (current)

Deliverables: this `docs/` package (12 reports + research).
Exit criteria:
- All 12 deliverable docs present and internally consistent.
- Claude review package generated.
- User sign-off on desktop shell, DB, license posture, and module roster.

## Phase 1 — Skeleton (weeks 1–2 of implementation, after gate 0)

Goal: A booting end-to-end skeleton that does nothing chess-specific yet but proves the architecture.

Deliverables:
- Monorepo scaffolded per `11_repo_structure/`.
- Tauri shell forked from a pinned en-croissant tag; runs on Windows.
- FastAPI `gateway` service bootable in Docker.
- Redis + Qdrant + SQLite running via `compose.dev.yml`.
- One trivial agent (e.g. `debug_agent`) reachable end-to-end: GUI → gateway → debug_agent → bus → back to GUI WS.
- structlog + redaction filter wired up.
- CI: lint + unit tests pass.
- Tier-rule linter committed and green.
- Token-auth between Tauri and gateway working.

Exit criteria:
- `chess-coach dev up` → app window opens → "System healthy" widget green.
- All Phase-1 ADRs (architecture decision records) committed.

## Phase 2 — Engine + Analysis core (weeks 3–4)

Goal: A user can open a PGN and see Stockfish-driven analysis in the GUI.

Deliverables:
- `engine_orchestrator` with Stockfish 18 integration; UCI pool; streaming WS.
- `analysis_agent` minimal: open game, run depth-22 analysis, classify blunders, store.
- GUI `panels/coach/AnalysisExtensions.tsx` augmenting en-croissant's analysis board with our additional data.
- SQLite schema v1 + Alembic baseline.
- Cache layer (Redis) for engine analyses.
- Engine binary download CLI + signed allowlist.

Exit criteria:
- Round-trip: import a PGN → see eval graph + blunder list → click a blunder → engine PV streams in GUI.
- Perf budget met for "open PGN" and "position eval at depth 22".

## Phase 3 — Memory + Knowledge Base + LLM Router (weeks 5–6)

Goal: Persistent memory and basic semantic search; first LLM-narrated outputs.

Deliverables:
- `memory_agent` with three-tier façade.
- `kb_agent` with Qdrant collections + hybrid search.
- `llm_router` library with OpenRouter primary + caching + budget enforcement.
- First LLM use case: "narrate this analysis" — turns the structured blunder list into a human-readable post-game summary.
- Prompt template library in `libs/chess_coach_llm/prompts/`.

Exit criteria:
- `/kb/search` returns sensible results on a seeded corpus.
- A user can request a narration of a finished game; output saved as a report.
- LLM budget enforcement demonstrably caps cost in a stress test.

## Phase 4 — Profiling (weeks 7–8)

Goal: First version of the psychological profile (data-driven, with confidence bands).

Deliverables:
- `profile_agent` with the first 6 metrics: tactical-vs-positional bias, time-pressure quality, opening comfort, conversion ability, blunder rate vs rating, decision-fatigue (eval-loss as moves elapse).
- ChessStalker-inspired Stalker-equivalent composite score, **with confidence intervals**.
- Profile dashboard panel.
- `/profiles/explain` endpoint and UI "explain this metric" affordance.
- Golden tests for each metric using fixture games with known characteristics.

Exit criteria:
- Profile is reproducible from the same inputs.
- Each metric has a written, reviewed definition + confidence-band methodology.
- UI labels metrics as "experimental" below sample-size threshold.

## Phase 5 — Repertoire + Training (weeks 9–10)

Goal: Opening repertoire management + first adaptive training plans.

Deliverables:
- `repertoire_agent` with tree management, gap detection, novelty detection.
- `training_planner` v1: weak-line drills, missed-tactic SRS (FSRS), basic plan view.
- Opening tree visualization in GUI.
- Training dashboard with calendar.

Exit criteria:
- Adding a few games surfaces real gaps in a sample repertoire.
- Daily SRS queue is populated and progresses on completion.

## Phase 6 — PDF / Vision (weeks 11–13)

Goal: Ingest chess books.

Deliverables:
- `pdf_vision_agent` saga: parse → detect → reconstruct → validate → ingest.
- YOLOv8 diagram detector + piece-classifier CNN (trained on a small but diverse dataset).
- PaddleOCR integration; figurine-notation recognition.
- Manual-review queue in GUI.
- User-correction feedback loop captures training data.

Exit criteria:
- A representative test book (one classic + one modern) ingests with ≥ X% diagram FEN accuracy (target set during Phase 0 sign-off — TBD with user).
- Failures route to review queue cleanly.

## Phase 7 — Sync + Research + Reporting polish (weeks 14–15)

Goal: Cloud integration and autonomous research.

Deliverables:
- `sync_agent` with Lichess + Chess.com, OAuth/PAT, incremental sync.
- `research_agent` v1 with source allowlist + daily digest.
- `reporting_agent` polish: PDF export, weekly progress reports, opponent prep reports.

Exit criteria:
- Daily sync runs without rate-limit breaches.
- Weekly digest produced and surfaced in GUI.

## Phase 8 — Hardening + Packaging (weeks 16–17)

Goal: Shippable end-user build.

Deliverables:
- PyInstaller sidecar binary for backend.
- Tauri MSI/NSIS installer.
- Auto-updater configured with signed manifests.
- Memurai bundled for end-user Redis.
- End-to-end perf tests against budgets.yaml.
- Security checklist signed off.
- User documentation + onboarding flow.

Exit criteria:
- Clean Windows 10/11 VM installs and runs without manual setup.
- All `tests/perf/budgets.yaml` budgets met at p95.
- All items in `docs/08_security/` checklist demonstrably implemented.

## Phase 9 — v2 directions (not committed, candidates only)

- Local LLM mode (Ollama / llama.cpp).
- macOS + Linux builds.
- Voice coaching layer.
- Multi-user club server mode (Postgres upgrade path activated).
- Mobile companion (read-only).
- Tournament-prep workflows.

## Validation strategy across all phases

- **Unit**: every library/service has unit tests; coverage target 80% on libs, 60% on services.
- **Golden tests**: deterministic-output features (analysis, profile metrics, repertoire-gap detection) compared to reviewed expected outputs.
- **Integration**: docker-compose.test brings up the stack; pytest hits HTTP/WS endpoints; runs in CI.
- **E2E**: Playwright drives the Tauri shell; runs on a Windows runner.
- **Performance**: pytest-benchmark + custom WS latency tests; budgets enforced.
- **Security**: pip-audit, pnpm audit, `bandit` (Python static), `cargo audit` (Rust), secret-scanning pre-commit.
- **Architectural**: tier-rule linter; OpenAPI compatibility check between gateway and TS client.

## Rollback strategy across phases

At any phase, a regression that fails exit criteria reverts the phase's PRs and re-attempts. Phase exit criteria are immutable once a phase closes (changes require a new ADR).
