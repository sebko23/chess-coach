# Implementation Roadmap — v2 (Monolith-First, Scope-Reduced)

**Status**: Active. Supersedes `implementation-roadmap-v1.md` (kept for history).
**Trigger for the rewrite**: Claude.ai external architecture review (`docs/13_review_response/claude-review-received.md`) found the v1 plan over-ambitious for Phase 1. This v2 plan:

1. Adopts **monolith-first** deployment: 14 conceptual modules ship inside one Python service for Phase 1–3, with the option to extract each to its own process later.
2. **Reduces Phase 1 scope** to: en-croissant fork + Stockfish-only + SQLite + grounded LLM commentary + opening explorer.
3. **Blocks all implementation** on user decision U1 (GPL boundary — see `docs/13_review_response/response-to-review.md` § E).
4. Removes Redis as a hard dep for Phase 1 (it returns when a real workload needs it).
5. Defers Qdrant + saga + PDF/Vision + Psych Profiling + Repertoire + Training Planner + Research + Sync to later phases.

---

## Gate 0 (current, pre-implementation)

**Exit criteria**:
- [x] Phase-1 architecture package complete.
- [x] External (Claude) review received and integrated into `13_review_response/`.
- [ ] **User resolves U1** (GPL boundary). Until this resolves, the project does not start coding.
- [ ] User resolves U2 (scope reduction approval — this v2 plan).
- [ ] User resolves U8 (Stockfish-only Phase 1 confirmation).

U3, U5, U6, U7, U9 can be answered later (deferred to their respective phases).

---

## Phase 1 — Foundation skeleton + Stockfish analysis (weeks 1–6 of impl)

**Goal**: a user can open a PGN and see Stockfish-driven analysis with grounded LLM narration, inside a forked en-croissant shell. **One process** for the backend.

**Modules in this phase** (as Python packages, all inside one `chess_coach_backend` service):
- `gateway` (HTTP/WS entrypoint, session-token auth)
- `engine_orch` (Stockfish 18 only)
- `analysis` (game/position analysis using engine_orch)
- `memory` + `kb` (merged for Phase 1: SQLite + FTS5 only, no Qdrant)
- `llm_router` (OpenRouter primary; degraded-mode default since no Redis)
- `narration` (the grounded-narration pipeline producing coaching prose)
- `debug` (health, jobs, logs)
- `jobs` (SQLite-backed job queue; not Celery yet)

**Frontend** (one workspace, `apps/desktop/`):
- Forked from a pinned en-croissant tag.
- New panels under `panels/coach/`: `GameAnalysisView`, `EngineLineStream`, `CommentaryPanel`, `DebugPanel`.
- Zustand stores under `lib/state/coach/`.
- TS client auto-generated from FastAPI OpenAPI.
- WS multiplex at `/ws` with topic subscriptions.

**Infra**:
- SQLite (WAL) only. No Redis. No Qdrant. No Celery.
- Dev: `chess_coach_backend` runs as a single Python process via `uvicorn`. The Tauri shell spawns it via `tauri-plugin-shell` in dev; production sidecar packaging is Phase 8.

**Out of scope this phase**:
- Leela / Maia / other engines.
- Vector DB / semantic search.
- PDF ingest.
- Psychological profiling.
- Repertoire management.
- Training plans.
- Cloud sync.
- Saga coordinator.
- Redis message bus.

**Exit criteria**:
- Round-trip works: import PGN → engine analyzes → blunders classified → user clicks a move → engine PV streams → LLM narrates → narration passes grounding validator → displayed in CommentaryPanel.
- Engine cache populated and persisted.
- Job queue handles concurrent analysis without blocking the HTTP handlers.
- Async/sync boundary rule (50 ms rule) enforced.
- Tier-rule namespace packaging enforced.
- Integration-surface tests against the pinned en-croissant tag are green.
- Performance budgets met (per `09_performance/`).
- Security checklist (loopback-only, token auth, secrets in Credential Manager, redaction filter, PGN comment sanitization) passes.

---

## Phase 2 — Engine expansion + cloud cache (weeks 7–9)

**Goal**: add a second engine (Leela) and cloud-eval caching from Lichess.

**Modules added**:
- `engine_orch`: add Leela adapter; Maia OPTIONAL based on memory-tier mode.
- New: `cloud_eval` (subset of future `sync_agent` — only the cloud-cache-read path).

**Validations**:
- Engine memory tier system (Lite/Standard/Full) operational, enforced.
- Leela GPU path optional; CPU fallback never blocks the orchestrator.

**Exit criteria**:
- Multi-engine comparison view ships.
- Cloud-eval cache reduces local engine load by ≥ 30% on user-tested positions.

---

## Phase 3 — Semantic search + Qdrant introduction (weeks 10–13)

**Goal**: introduce vector retrieval. **First place we leave the monolith comfort zone**.

**Modules added**:
- `kb` separates from `memory` and gains a Qdrant adapter.
- `embedding_worker` (in-process, async): batch-embeds new content; backed by `nomic-embed-text` (Ollama local) by default, or cloud per U3.
- Vector retrieval interface (`VectorStore`) made provider-agnostic from day one.

**Infra**:
- Qdrant runs as a separate sidecar binary (Tauri `externalBin`) but Python still ships as one process.
- **No Redis yet** unless empirical evidence shows the in-process bus shim is constrained.

**Exit criteria**:
- Semantic search returns relevant positions/concepts from a seeded test corpus.
- Re-indexing utility exists (for embedding-model swaps).
- Vector retrieval interface is provider-agnostic (Qdrant + a stub `pgvector` adapter prove this).

---

## Phase 4 — Playing Style Patterns (rebrand of "Psychological Profiling") (weeks 14–16)

**Goal**: behavioral metrics with statistical rigor.

**Modules added**:
- `profile` (internal name; UI label "Playing Style Patterns" pending U7).
- `metrics`: each metric is a Python module with explicit hypothesis, null hypothesis, sample-size requirement, effect-size threshold (Cohen's d ≥ 0.5 to surface), confidence band.

**Rules** (per `13_review_response/` § B4):
- No metric is shown to the user with statistical significance alone — must also pass effect-size threshold.
- All metrics carry a permanent "experimental" badge.
- Each profile dashboard view ships with a non-clinical disclaimer.
- An `/profile/explain/{metric}` endpoint shows methodology + raw inputs + intermediate values.

**Exit criteria**:
- 6 metrics shipped (tactical-vs-positional bias, time-pressure quality, opening comfort, conversion ability, blunder rate vs rating, decision-fatigue).
- Each metric has reviewed methodology doc + golden test fixtures.
- UI clearly communicates uncertainty.

---

## Phase 5 — Repertoire + Adaptive Training (weeks 17–20)

**Goal**: opening repertoire intelligence + FSRS-based training.

**Modules added**:
- `repertoire` (tree, gap detection, novelty detection).
- `training_scheduling` (FSRS algorithm — deterministic).
- `training_lessons` (LLM-mediated lesson generation, grounded).

**Note**: scheduling vs lesson generation kept as **separate libraries inside one service**, per review §2.1 (different change rates).

**Exit criteria**:
- Adding sample games surfaces real repertoire gaps.
- SRS queue advances daily.
- Lesson generation is grounded (no LLM commentary contradicting engine truth or known theory).

---

## Phase 6 — PDF/Vision (weeks 21–32, *not* 11–13 per v1)

**Critical change from v1**: this phase is **8–12 weeks**, not 3. The dataset and model work alone takes months per the review (§ 8.1).

**Workstreams** (largely parallel):
- W1: Dataset assembly (existing ChessPiece + synthetic augmentation + a curated set of book pages).
- W2: YOLOv8 fine-tune for diagram detection.
- W3: Piece classifier CNN training.
- W4: PaddleOCR + chess-syntax post-processing.
- W5: Validation pipeline (legal-position checks, low-confidence routing).
- W6: Pipeline integration as a **linear Celery chain** (no saga framework; review § B1).
- W7: PDF parser isolation (subprocess sandbox; review § A-F11).
- W8: Manual-review queue UI + user-correction feedback loop for re-training.

**Infra**:
- Celery introduced here (real long-running parallel work).
- Redis (Valkey on Windows) reintroduced here as Celery broker AND agent bus.
- Saga coordinator: NOT built. The ingest pipeline is a linear chain with per-step DLQ.

**Gate threshold** (U6, default per review § 11.1): ≥ 97% piece placement accuracy, ≥ 90% full-board FEN accuracy on a held-out test set of 500+ diverse book pages.

---

## Phase 7 — Cloud sync + autonomous research (weeks 33–36)

**Modules added**:
- `sync` (Lichess + Chess.com; OAuth/PAT; incremental cursor).
- `research` (curated-source monitor; LLM relevance judge under tight token budget).

**Exit criteria**:
- Daily sync runs without 429s.
- Weekly research digest produced.

---

## Phase 8 — Packaging + hardening (weeks 37–40)

**Workstreams**:
- PyInstaller sidecar binary (real cost: significant; AV false positives expected — budget time for it).
- Alternative considered (per review § 2.5): Docker-launcher shim. Final choice = U9.
- Tauri MSI/NSIS installer; auto-update signed (Ed25519).
- End-to-end perf budgets met.
- Security checklist signed off (incl. PDF sandbox, PGN sanitization, telemetry posture U5).
- User onboarding flow including separate-API-key recommendation.

---

## Phase 9 — v2 candidates (uncommitted)

- Local LLM mode (Ollama-served narration).
- Voice coaching (latency budget incompatible with multi-hop bus — measure first).
- macOS / Linux builds.
- Multi-user club server (Postgres upgrade path activates).
- Mobile companion (read-only).

---

## Validation strategy (unchanged from v1)

Unit + golden + integration + E2E + perf + security + tier-rule packaging enforcement. See v1 doc for the matrix; methodology is unchanged.

---

## Roadmap diff vs v1 (summary)

| Aspect | v1 | v2 |
|---|---|---|
| Phase 1 process count | ~5+ services + Redis + Qdrant | **1 Python service** + SQLite |
| Phase 1 engine roster | 6 engines pluggable | **Stockfish only** |
| Saga framework | Built in Phase 1 | **Never built** (linear chains only) |
| Vector DB | Phase 3 | Phase 3 (unchanged) — but separated from `memory` only here |
| PDF/Vision | 3 weeks, Phase 6 | **8–12 weeks**, Phase 6 |
| Redis | Hard dep from Phase 1 | Introduced when a workload needs it (Phase 6) |
| Psych profiling | Confidence bands only | + effect-size threshold + permanent "experimental" + UI rebrand |
| LLM narration | implicit | **Mandatory** grounded-narration pipeline |
| GPL boundary | Asserted (sep process = clean) | **Blocked on user U1** |


---

## Post-Legal-Opinion Amendments (2026-05-18)

External OSS counsel returned a plausibly-NO verdict on the combined-work question (U1) contingent on three pre-coding actions (P1/P2/P3). See `docs/13_review_response/legal-opinion-integration.md`. The plan is amended accordingly.

### Gate 0 (now)

Added exit criteria:
- [ ] User confirms acceptance of P1 (CLA with broad sublicensing grant), P2 (non-blocking auto-updater per GPL-3.0 §6), and P3 (public protocol spec) as binding architectural requirements.
- [ ] Protocol contract draft (`docs/16_protocol/chess-coach-protocol-v1.md`) sent back to counsel; precise §6 assessment received and any recommended revisions integrated.

U1 remains conditionally open until the protocol-review round returns. Once it returns clean, Gate 0 closes and Phase 1 may begin.

### Phase 1 — additional exit criteria

- [ ] `CONTRIBUTING.md`, `CLA-ICLA.md`, `CLA-CCLA.md` published in repo root.
- [ ] CLA-bot or `cla-assistant.io` wired into CI as a hard merge gate for the Backend codebase.
- [ ] `BUILDING.md` published with reproducible GUI build instructions.
- [ ] `chess-coach-protocol-v1.md` published as protocol v1.0.0 (final, post-counsel-review).
- [ ] JSON Schema documents for every payload (§15 of the protocol) committed under `specs/v1.0/schemas/`.
- [ ] Reference test vectors (§14 of the protocol) committed under `specs/v1.0/tests/`.

### Phase 8 — additional exit criteria

- [ ] P2 verification: GUI built from source on a clean Windows VM using only `BUILDING.md`, installed, and run against the Backend without any difference from our signed build.
- [ ] User-visible documentation of update opt-out and self-hosting paths.
- [ ] Source-availability obligations for bundled engine binaries (Stockfish) documented and linked in installer notes.
