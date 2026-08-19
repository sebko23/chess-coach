# System Architecture — CHESS COACH

**Status**: Phase-1 master document. Integrates every deep-dive report under `docs/`.
**Reading order if new**: this file → `02_modules/` → `06_multi_agent/` → topic-specific reports.

---

## 1. Vision

CHESS COACH is an autonomous, grandmaster-level chess coaching platform for individual players. It combines:

- a rich desktop GUI inheriting en-croissant's chess interface,
- a Python-based multi-agent backend for analysis, profiling, training, and research,
- a hybrid deployment (host shell + Docker services) that runs locally on Windows today and is positioned for cloud/server expansion later.

It is **not** an LLM-driven monologue agent: LLMs are used surgically for natural-language work (narration, summarization, prose reasoning), while deterministic chess logic — engine analysis, classification, metric computation — is plain Python.

The full vision is described in the master prompt in `.a0proj/` and not duplicated here. This document focuses on **how** we build it.

---

## 2. Architectural style

- **Hybrid desktop + microservices** within a single host. The Tauri shell on the user's Windows desktop talks to a Dockerized Python backend over localhost HTTP/WS.
- **Agent-oriented**: 14 specialized modules with documented boundaries (see `02_modules/`).
- **Event-driven** internally: a Redis Streams message bus carries asynchronous events between agents (see `06_multi_agent/`).
- **Local-first**: all user data lives in `%APPDATA%\ChessCoach\data`. Cloud calls (LLMs, Lichess, Chess.com) are opt-in features layered on top of a fully functional offline core (offline LLM is a v2 candidate).
- **Modularity over convenience**: every agent is independently deployable, debuggable, mockable. The tier rules in `06_multi_agent/` forbid back-references and enforce a clean dependency graph.

---

## 3. Component model (high-level)

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                                  Tauri Shell                                  │
 │  ┌──────────────────────────────────────────────────────────────────────┐   │
 │  │  React (en-croissant base + panels/coach/*)                          │   │
 │  │   • Analysis board (upstream)         • Profile dashboard            │   │
 │  │   • Repertoire explorer               • Training dashboard           │   │
 │  │   • Heatmaps                          • Agent monitor                │   │
 │  │   • Logs / Debug panel                • Coach terminal/chat          │   │
 │  └──────────────────────────────────────────────────────────────────────┘   │
 │                       ▲                          │                          │
 │             Tauri commands (Rust)                ▼                          │
 └──────────────────────────────┬──────────────────────────────────────────────┘
                                │ HTTP + WS  (127.0.0.1:8765, token-auth)
 ┌──────────────────────────────▼──────────────────────────────────────────────┐
 │                          FastAPI Gateway                                     │
 │            auth · routing · WS fan-out · OpenAPI · health                   │
 └──┬────────┬────────┬────────┬────────┬────────┬────────┬────────┬───────────┘
    │        │        │        │        │        │        │        │
    ▼        ▼        ▼        ▼        ▼        ▼        ▼        ▼
  Engine  Analysis  Profile  Memory   KB     Training Repertoire Reporting
  Orch.   Agent     Agent    Agent   Agent   Planner  Agent      Agent
    │        │        │        │       │        │        │        │
    ▼        ▼        ▼        ▼       ▼        ▼        ▼        ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                       Redis Streams (bus)                              │
  │                       Redis (cache + queues)                            │
  └────────────────────────────────────────────────────────────────────────┘
    │        │        │        │        │        │
    ▼        ▼        ▼        ▼        ▼        ▼
  PDF /  Research  Sync     Debug    LLM Router    Celery workers
  Vision Agent     Agent    Agent    (library)     (heavy + light)
  Agent
    │        │        │
    ▼        ▼        ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                Persistence: SQLite (WAL) · Qdrant · Filesystem          │
  └────────────────────────────────────────────────────────────────────────┘
```

References:
- Per-module specs: `docs/02_modules/module-decomposition.md`
- Bus topology + tier rules: `docs/06_multi_agent/multi-agent-workflow.md`
- Persistence design: `docs/04_database/database-decision.md`
- Repo layout: `docs/11_repo_structure/repository-structure.md`

---

## 4. Frontend architecture

Driven by the constraint to **preserve en-croissant**:

- Stack: Tauri 2.x + Rust + React 19 + Mantine 8 + Vite 8 + chessground (inherited).
- Code we author lives **only** in `apps/desktop/src/panels/coach/*` and a few well-known integration points (Tauri commands, lib/api, lib/ws, lib/state). Upstream files are touched sparingly so that periodic rebases against en-croissant remain low-cost.
- State: existing en-croissant Zustand stores are preserved; we add new stores under `lib/state/coach/*` for new panels. **Decision (post-review)**: Zustand is the chosen state library for all new `panels/coach/*` work, matching upstream and avoiding a second state-management paradigm in the same renderer. Prop drilling beyond two component levels is forbidden by lint rule.
- Client API: a TypeScript client is **generated** from the FastAPI OpenAPI schema (`tools/gen_ts_client.py`) so contracts stay in lockstep with the backend.
- WebSocket: a single multiplexed WS connection at `/ws` with topic subscriptions per panel — engine streams, agent status, log tails.
- All cross-process traffic terminates at the gateway. Tauri commands themselves do nothing chess-specific; they only handle OS-level concerns (file dialogs, screenshots, system tray).
- Desktop shell decision and justification: `docs/05_desktop_shell/desktop-shell-decision.md`.

---

## 5. Backend architecture

### Service inventory (Docker compose, dev)

| Service | Purpose | Type |
|---|---|---|
| `gateway` | FastAPI entrypoint, auth, WS fanout, OpenAPI | HTTP/WS |
| `engine_orchestrator` | UCI engine pool | HTTP/WS |
| `analysis_agent` | Game/position analysis | HTTP + bus |
| `profile_agent` | Psychological metrics | HTTP + bus |
| `kb_agent` | Knowledge base, semantic + structured search | HTTP |
| `memory_agent` | Unified memory façade | HTTP |
| `training_planner` | Plans + SRS | HTTP + bus |
| `repertoire_agent` | Opening repertoire | HTTP + bus |
| `research_agent` | Source monitoring + digest | scheduled |
| `reporting_agent` | Reports + Saga coordinator | HTTP + bus |
| `debug_agent` | Health, DLQ, support bundles | HTTP |
| `sync_agent` | Lichess / Chess.com | scheduled |
| `worker-heavy` (Celery) | PDF, OCR, YOLO, classifier | bus consumer |
| `worker-light` (Celery) | LLM, KB indexing, lighter async | bus consumer |
| `redis` | Bus + cache + queues | infra |
| `qdrant` | Vector DB | infra |

SQLite is in-process per service (read pool) but writes are funneled through `memory_agent`'s `db_writer` actor (see `04_database/`).

### Why a gateway and not direct service exposure

- Single point of authentication (session token).
- One TLS/CSP/CORS surface.
- WS fan-out: one socket to the frontend, many internal subscriptions.
- Simpler firewall posture: only port 8765 is bound, only on loopback.

---

## 6. Deployment topology

### Developer mode

```
Windows host:
   Tauri shell (npm run dev → Vite + tauri dev) ──┐
                                                  │ HTTP/WS
   Docker Desktop:                                ▼
     compose.dev.yml ▶ gateway + agents + redis + qdrant
     Bind mounts:
       ./services    → /app                 (live code reload)
       ./data        → /data                (single source of truth)
       ./libs        → /app/libs
```

### End-user mode (Phase 8 packaging)

```
Windows host:
   Installer (MSI / NSIS) deploys:
     • CHESS COACH.exe (Tauri shell)
     • chess-coach-backend.exe  (PyInstaller sidecar bundling all services)
     • memurai.exe              (Redis-compatible Windows service)
     • qdrant.exe               (Qdrant binary, embedded mode)
     • Default %APPDATA%\ChessCoach\data tree
   Tauri shell launches the sidecar via Tauri's `externalBin`.
   No Docker required by the end user.
```

Why two modes:
- Dev uses Docker for environmental fidelity, language-agnostic services, and easy infra reset.
- End-user uses a sidecar to avoid imposing Docker Desktop on every user.
The service code itself does not change between modes; only the **process supervisor** differs.

---

## 7. IPC, message passing, and contracts

Three levels of contracts:

1. **HTTP/REST (sync)**: OpenAPI schema generated by FastAPI is the source of truth; TS client and Python clients are generated from it. Breaking changes require a route version bump (`/v2/…`).
2. **WebSocket (streaming)**: Each topic has a typed schema (Pydantic on backend, mirrored TS interface on frontend). Subscriptions are by topic name; messages are envelopes (see `06_multi_agent/`).
3. **Bus events (async)**: Redis Streams, canonical envelope, `schema_version` per topic. Breaking schema = new stream name.

All cross-service calls go through one of these three. **No** direct database calls across service boundaries; agents read/write their own tables and obtain other agents' data via API or events. This is enforced by the tier-rule linter.

### Conversation patterns

Five named patterns (full definitions in `06_multi_agent/`): P1 request/reply, P2 async job, P3 streaming, P4 pub/sub, P5 saga. Every agent endpoint declares which pattern it uses.

---

## 8. Engine orchestration pipeline

```
  Request (FEN, settings)
          │
          ▼
  ┌─────────────────────┐
  │ Engine Orchestrator │  ──► pool of UCI subprocesses (Stockfish, Leela, Maia, Berserk, Komodo, Ethereal)
  └─────────────────────┘                  │
          │                                ▼
          │            UCI: position fen ... ; go depth N multipv K
          │            info depth ... score cp ... pv ...
          │            bestmove ...
          ▼
  Aggregator: parse info lines → AnalysisResult (PV list, score, depth, time)
          │
          ├─► WebSocket stream (live progressive UI)
          ├─► Redis Streams: events.engine.analysis.ready
          └─► Cache: SQLite engine_analyses keyed by (fen, engine_id, engine_version, depth, multipv, settings_hash)
```

Key properties:
- Pool size = (logical_cores ÷ 2), configurable.
- Engine instances are reused across requests (UCI `ucinewgame` + `position` reset state).
- Multi-engine comparison: same FEN dispatched to N engines in parallel; results aggregated for the Analysis Agent.
- Engine downloads via signed allowlist (see `08_security/`).
- Detailed engine architecture in `02_modules/` § 3.

---

## 9. PDF / OCR / vision pipeline

Implemented as a P5 Saga (see `06_multi_agent/`):

```
  PDF upload
     │
     ▼
  parse_pages (PyMuPDF)         → events.book.page.parsed
     │                            • text per page
     │                            • images per page
     ▼
  detect_diagrams (YOLOv8)      → events.book.diagram.detected
     │                            • bounding boxes + confidence
     ▼
  detect_orientation            • white-to-move? upside-down?
     │
     ▼
  classify_pieces (CNN)         • per-square piece label + confidence
     │
     ▼
  reconstruct_fen               • assemble + side-to-move + castling rights
     │
     ▼
  validate_fen (legal pos check)
     │
     ├── confident ──► events.book.fen.reconstructed → KB ingest
     └── low conf  ──► manual_review_queue (surfaced in GUI)
     │
     ▼
  ocr_nearby_text (PaddleOCR)   → move sequences, annotations
     │
     ▼
  ingest into KB                → Qdrant + SQLite
  events.book.ingested (saga done)
```

**Production path note (since 2026-06-14):** the diagram-extraction stage uses the chessvision.ai API as the production path (150 diagrams extracted at audit time per `docs/16_audit/project-audit-2026-06-14.md`). **Correction (2026-08-13, doc-drift fix-up):** the previous text said "YOLOv8 + PaddleOCR retained as offline fallback" but verified against current main (per FU-19 / PR #95 investigation): neither binary exists in services/, libs/, or apps/. Current production path is the external chessvision.ai API only; there is no local PDF parser to deploy. The 2026-06-14 point-in-time reference SHA `6635ffa` is no longer reachable in the current history because subsequent squash-merges have invalidated it; the substance of the change (chessvision as production path) is documented per the audit.

Feedback loop: user corrections in the manual-review queue are stored as labeled training data under `data/models/piece_classifier/training/`, enabling periodic re-training. Detailed in `02_modules/` § 6.

---

## 10. OpenRouter / LLM orchestration

LLM access is mediated by the **LLM Router** library (Tier 2, in-process, see `02_modules/` § 14):

```
  caller (any agent)
     │
     ▼  await llm.run(task="narration", prompt=…, schema=Pydantic)
  ┌──────────────────────────────────────────────────────────────────┐
  │ LLM Router                                                       │
  │ 1. cache lookup (Redis, key = hash(prompt, model, temperature))  │
  │ 2. budget check (per task profile, per day)                      │
  │ 3. provider route (OpenRouter primary; OpenAI/Anthropic/Ollama) │
  │ 4. circuit breaker per provider                                  │
  │ 5. structured output: JSON-mode + Pydantic validate + retry      │
  │ 6. cache write + budget decrement                                │
  └──────────────────────────────────────────────────────────────────┘
```

Task profiles route to different cost tiers:
- `narration` → mid-cost model with prose strength
- `reasoning` → top-tier (selectively)
- `summarization` → cheap model, long context
- `relevance_judge` → cheapest tier
- `embedding` → embedding model (separate path)
- `vision` → vision-capable model (optional)

Claude-review packages (see deliverable #12) are produced separately and shipped to the user / external Claude.ai outside this router.

---

## 11. Persistent memory tier

Three tiers (see `04_database/` for storage details):

| Tier | Backing store | What lives there |
|---|---|---|
| Episodic | SQLite | games, analyses, lessons, attempts, messages, audit |
| Semantic | Qdrant | book chunks, position concepts, annotations, user lessons |
| Procedural | Filesystem markdown (`data/skills/`) + Qdrant index | coaching skills, playbooks |

Access is unified via the **Memory Agent** which:
- Routes writes to the appropriate tier(s).
- Fan-out reads with rank-merge (recency × relevance).
- Maintains an append-only audit log.
- Runs periodic consolidation: old episodic rows → condensed semantic memories.

---

## 12. Observability and debuggability

- **Logs**: every service emits structured JSON via structlog; redaction filter scrubs secrets. Aggregation optional via Loki sidecar.
- **Metrics**: each service exposes Prometheus `/metrics`. Scraping optional.
- **Tracing**: OpenTelemetry spans propagated via the `trace_id` field of the bus envelope. Optional Jaeger.
- **Debug Panel** (GUI): live agent status, per-topic event tail, DLQ inspector + retry, log tail, support-bundle generator.
- **Reproducibility**: analyses, profile metrics, reports, and LLM calls are reproducible from a recorded trace_id + inputs. This is essential for both debugging and external review.

---

## 13. Performance posture

Budgets are codified in `tests/perf/budgets.yaml` and enforced in CI. Highlights (full table in `09_performance/`):

- Position eval at depth 22: p95 ≤ 800 ms.
- Full-game analysis at depth 22 / multi-PV 3: p95 ≤ 20 s.
- Semantic KB search top-10: p95 ≤ 250 ms.
- GUI cold start: ≤ 1.2 s p95.
- Backend cold start (all services): ≤ 12 s p95.

We meet these via:
- async I/O, sized engine pools, sized Celery worker pools,
- multi-layer caching (in-process LRU → Redis → SQLite materialized views → on-disk artifacts),
- WAL-mode SQLite tuned with mmap + cache pragmas,
- Qdrant HNSW with mmap segments above ~100k vectors per collection.

---

## 14. Security posture

Full details in `08_security/`. Key points:

- Loopback-only gateway with session-token auth between Tauri and backend.
- Tauri allowlist minimized; CSP locked down; no Node in renderer.
- Secrets in OS keychain (Windows Credential Manager).
- All outbound HTTP through one wrapper enforcing TLS, timeouts, rate limits, redacted logging, circuit breaker.
- Untrusted user content (PDFs, PGNs, cloud responses) sandboxed and explicitly delimited in LLM prompts.
- Signed auto-update (Tauri Ed25519).
- Append-only audit log with hash-chained export.

---

## 15. License posture

- The Tauri shell (forked from en-croissant) is **GPL-3.0-only**.
- Backend services run as **separate processes**, communicate only via documented HTTP/WS protocol, and have no GPL linkage. They are released under a license of the user's choosing (default suggestion: Apache-2.0).
- Authoritative source for license terms: `LICENSING.md` (published 2026-05-18, ADR-0004). The boundary is validated periodically.
- See `docs/research/en-croissant-analysis.md` for the upstream license analysis.

---

## 16. Risk-aware architectural choices

(Full risk register in `07_risk/`.) Architectural decisions that exist specifically because of identified risks:

- **Process-separated backend** → avoids GPL contamination from en-croissant.
- **`panels/coach/*` discipline** → minimizes upstream rebase pain.
- **Tier rules + linter** → prevents architectural drift across 14 agents.
- **Confidence intervals on every profile metric** → prevents overclaim of precision.
- **PyInstaller sidecar option** → prevents Docker Desktop becoming a user-facing dependency.
- **Engine cache versioning** → prevents silent cache poisoning across engine upgrades.
- **LLM Router as sole LLM ingress** → enables budget, caching, fallback, and prompt-injection containment in one place.

---

## 17. What is explicitly out of scope for Phase 1 (architecture)

- Cloud-hosted multi-user deployment.
- Voice coaching pipeline.
- Mobile companion.
- Live tournament-pairing integration.
- Real-time multiplayer.

These are listed as Phase 9 candidates in `10_roadmap/`. The architecture does **not preclude** any of them; the persistence tier, the multi-agent bus, and the gateway pattern are deliberately chosen to scale into those directions if pursued.

---

## 18. Open decisions (carried to next gate review)

0. **(RESOLVED 2026-05-18)** License posture per ADR-0004 — see `LICENSING.md` (counsel verdict in `docs/13_review_response/legal-protocol-assessment-received.md`; protocol v1.0.0 stable, R1+R2 applied, P1+P2+P3 committed).
1. **Default sidecar vs Docker** for end-user installs — currently "Docker-first for dev, PyInstaller sidecar for users". Confirm with user before Phase 8.
2. **Embedding model default** — `bge-small` (offline, 384-dim) vs OpenAI `text-embedding-3-small` (cloud, 1536-dim). Both supported; default needs choosing. **Note (2026-06-20):** **Correction (2026-08-13, doc-drift fix-up):** the previous text said `services/chess_coach/memory_kb/` ships a TF-IDF facade (289 lines); verified against current code: that path does NOT exist (the actual KB module is at `services/chess_coach/kb/`, 457 total lines across 3 files), and `services/chess_coach/kb/embedder.py` line 5 explicitly states "Replaced TF-IDF (256-dim) on 2026-06-22" — the KB module now uses `sentence-transformers all-MiniLM-L6-v2` (384-dim), not TF-IDF. This entry remains a point-in-time reference (SHA `789b0cd` no longer reachable) but the substance of "TF-IDF was the path" is no longer accurate. The embedder is real and wired into the gateway via `routes/kb.py`; this open decision item has effectively been resolved by the embedder replacement.
3. **(RESOLVED)** Backend service license → **Apache-2.0** per `LICENSING.md` table (also covers `libs/`, `apps/cli/`, `tests/`, `tools/`, `scripts/`, `infra/`).
4. **Telemetry posture** — opt-in usage telemetry: yes/no/never. Default: no.
5. **OCR primary** — chessvision.ai API is the production path since 2026-06-14 (point-in-time reference; original SHA `6635ffa` is no longer reachable in the current history due to subsequent squash-merges); PaddleOCR vs Tesseract comparison **deferred** but moot in practice (neither binary is implemented; the local OCR path is PaddleOCR-shaped in concept only + the actual implementation does not exist; production path is the external chessvision.ai API).
6. **Repertoire UI density** — tree vs grid as primary; subjective. Defer to Phase 5 prototype.
7. **Phase-6 FEN-accuracy target** — currently unset; user input needed before Phase 6 gate.

---

## 19. Cross-references

| Topic | Location |
|---|---|
| Module specs (all 14) | `docs/02_modules/module-decomposition.md` |
| Multi-agent topology + bus | `docs/06_multi_agent/multi-agent-workflow.md` |
| Tech stack and rejected alternatives | `docs/03_technology/technology-comparison.md` |
| DB choice + schema sketch | `docs/04_database/database-decision.md` |
| Desktop shell justification | `docs/05_desktop_shell/desktop-shell-decision.md` |
| Risk register | `docs/07_risk/risk-analysis.md` |
| Security strategy | `docs/08_security/security-strategy.md` |
| Performance budgets and strategy | `docs/09_performance/performance-strategy.md` |
| Implementation roadmap (9 phases) | `docs/10_roadmap/implementation-roadmap.md` |
| Repo structure + license posture | `docs/11_repo_structure/repository-structure.md` |
| External (Claude) review package | `docs/12_claude_review/claude-review-package.md` |
| en-croissant analysis (raw) | `docs/research/en-croissant-analysis.md` |
| ChessStalker concepts (raw) | `docs/research/chessstalker-concepts.md` |

---

## Implementation Reality (as of `main@0cf39b6`, 2026-08-04)

The architecture above describes the **target vision**. Current reality differs in the following ways:

| Vision | Reality |
|--------|---------|
| Redis Streams message bus | Not implemented. Async work uses `asyncio.gather()` within the monolith. |
| 14 specialized agents as separate services | 1 FastAPI monolith (`gateway/`) with 20 route modules under `services/chess_coach/gateway/routes/` (29 `@router.<method>` decorators as of `main@0cf39b6`, 2026-08-04; verified unchanged at `main@6cd8302d` 2026-08-13). Module boundaries exist as Python packages but are not network-isolated. `route_guard` cross-cutting decorator (ADR-0002): as of `main@0cf39b6`, 25 of 29 handlers were guarded (6 via PR #72 squash `b320d3b`) with 5 routes still pending. **Correction (2026-08-13, doc-drift fix-up):** as of current `main@6cd8302d`, all 20 route files have `@route_guard` applied (verified line-by-line: `analysis.py:37`, `backfill_analyses.py:228`, `eval_verifier.py:161`, `pgn_import.py:135`, `system.py:58`/`system.py:77`); the apparent `route_guard` coverage gap from the 2026-08-04 snapshot was closed during work subsequent to the snapshot date (post-FU-9 / pre-PR-#94). The "follow-up BBF" referenced in the snapshot text is no longer needed. (Earlier `f24bd8b` SHA cited in prior doc versions is no longer reachable; the `route_guard`-applied-to-7-routes claim it supported is superseded by the PR #72 squash count.) |
| WebSocket streaming for real-time analysis | Not implemented. All communication is REST. |
| Backend port `127.0.0.1:8765` | Runs on `0.0.0.0:18080`. Frontend discovers via `backend.json` descriptor file. |
| Qdrant vector database | In-memory KB vector layer landed (point-in-time reference SHA `789b0cd` — no longer reachable in current history due to subsequent squash-merges — see `services/chess_coach/kb/` for the current code location). **Correction (2026-08-13, doc-drift fix-up):** the original text named `services/chess_coach/memory_kb/` which does NOT exist; the actual KB module is `services/chess_coach/kb/` (3 files, 457 lines total). Also the previous text said "TF-IDF position-similarity pipeline" but per `services/chess_coach/kb/embedder.py` line 5 TF-IDF was replaced by sentence-transformers all-MiniLM-L6-v2 (384-dim) on 2026-06-22. Standalone Qdrant server still not deployed; in-memory Qdrant-shaped facade still in place. Embedding-model default (item 2 of §18) has effectively been answered by the all-MiniLM choice — whether to graduate to a real embedding model is the remaining open question. |

**What is built and working (as of `main@0cf39b6`, 2026-08-04):** 20 route modules under `services/chess_coach/gateway/routes/` (29 `@router.<method>` decorators), Stockfish 18 engine pool + Maia-1500 via lc0, Tauri runtime `engines.json` pre-populated with both (point-in-time historical fact per `docs/16_audit/project-audit-2026-06-14.md`; current repo no longer contains `engines.json` as a checked-in file — it is a runtime-install artifact populated by the Tauri app, sourced from the appDataDir; root cause of the appDataDir copy pattern documented per project-audit-2026-06-14.md in the historical audit), Sqlite WAL (the 88,452-row figure was a 2026-06-20 snapshot; live row count varies), FSRS spaced repetition, psychological profiling (7 metrics: tactical_vs_positional_bias, time_pressure_quality, opening_comfort, conversion_ability, blunder_rate_vs_rating, decision_fatigue, sequence_based_tilt; corrected from the 2026-08-04 snapshot which listed 5 metrics — BBF-58 added decision_fatigue and sequence-based tilt subsequently), repertoire gap analysis, **engine-wired narration** (BBF-87.2 squash `e4a4c66` + BBF-87.2.1 squash `0cf39b6` — the narration route now invokes `engine_pool.analyze()` and feeds a real `AnalysisResult` into the LLM prompt; response carries `pv_moves`, `score_display`, `depth_reached`, `best_move` from the engine; real engine failures now propagate to `@route_guard` for a 5xx ADR-0002 envelope, was the silent-fabrication regression BBF-87.2.1 closed), typed OpenAPI TypeScript client, `route_guard` cross-cutting decorator (ADR-0002 — applied to 25 of 29 handlers; 6 routes via PR #72 squash `b320d3b`, plus the rest predating PR #72), chessvision.ai integration for PDF diagram extraction as the production path (Phase 6 partial — chessvision shipped; **Correction (2026-08-13, doc-drift fix-up):** the prior text "YOLOv8 + PaddleOCR retained as offline fallback only" is a stale reference per the FU-19 / PR #95 investigation; verified against current repo: neither binary exists in services/, libs/, or apps/. The `implementation-roadmap-v1.md` § Phase 6 deliverable list (YOLOv8 + PaddleOCR + manual-review queue + feedback loop) remains correctly deferred; no current implementation. Other Phase 6 deliverables per `implementation-roadmap-v1.md` § Phase 6), local pytest on the previously-blocked narration integration suites now passes 9/9 (verified post-FU-1 — the broken `importlib.metadata` for `huggingface-hub` was caused by a ghost `huggingface_hub-1.24.0.dist-info/` orphan that was quarantined during the FU-1 BBF), `activePlayerAtom` shared across Repertoire + TrainingQueue pages, 7 missing storage migrations restored at the 2026-08-04 snapshot (current state at `main@6cd8302d`: 9 migrations total, at `libs/chess_coach/storage/migrations/` — the storage module moved out of `services/` at some point subsequent to the snapshot, corrected here per the doc-drift fix-up convention; check `git log --oneline -- libs/chess_coach/storage/migrations/` for the current migration list), project audit at `docs/16_audit/project-audit-2026-06-14.md`, memory-disable durability across 2 session boundaries, and the **57 of 57 integration tests passing** baseline at the `main` HEAD bisect from `75d3af0` through `4feef86` (point-in-time reference — those SHAs are no longer reachable in the current history because subsequent squash-merges have invalidated them; the test count was correct at the time and has since evolved). Per `docs/01_architecture/doc-conventions.md`: SHA citations in current-state claims are intentionally avoided or qualified as point-in-time references; SHAs that are still reachable in `git log --all --reflog` are kept (e.g. `e4a4c66`, `0cf39b6`, `b320d3b`). See also the duplicate copy at `docs/12_claude_review/fable5-prompt1-ready-to-paste.md:1183` — marked there as a historical snapshot; this file is canonical.

Redis Streams and microservice extraction are deferred to Phase 6+ when workload demands it.
