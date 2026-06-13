# Module Decomposition

Each module is specified with: **Responsibilities**, **Public API** (HTTP/WS + bus topics), **Dependencies**, **Data flow**, **Debugging strategy**, **Scaling concerns**. Tier numbers refer to the dependency tiers defined in `06_multi_agent/`.

Language: Python 3.11 unless noted. All agents are FastAPI services running as separate processes (compose services) except the **GUI Agent** (TypeScript in the Tauri shell) and the **LLM Router** (in-process library imported by other agents).

---

## 1. GUI Agent  (Tier 4 — Presentation)

**Language**: TypeScript / React 19 + Mantine 8, running inside the Tauri renderer process.

**Responsibilities**
- Render all UI panels (en-croissant base + new coach panels).
- Translate user actions into backend API calls.
- Manage local UI state (selected game, current position, panel layout).
- Subscribe to backend WebSocket streams; render live engine/coach updates.
- Display the Debug Panel and Agent Monitor.
- Handle Tauri command invocations (file open, save, screenshot, system tray).

**Public API**
- Tauri commands: `coach.open_pgn(path)`, `coach.import_book(path)`, `coach.screenshot()`, `coach.export_data()`.
- Talks to backend gateway at `http://127.0.0.1:8765` (HTTP + WS).
- Subscribes to topics: `events.engine.analysis.stream.<correlation_id>`, `events.coach.message`, `events.agent.status`.

**Dependencies**: Tauri runtime, en-croissant components, chessground.

**Data flow**
- User → React component → React Query mutation → backend HTTP → response → UI update.
- Streaming: backend WS event → Zustand store update → component re-render.

**Debugging strategy**
- Browser DevTools attached to Tauri webview.
- Redux/Zustand devtools for state.
- A built-in **`/dev` route** with mock-mode toggles, fake backend response injectors, and a network log.

**Scaling concerns**
- Single-user single-window; not a scaling target. Mosaic layouts may cap at 10–12 open panels for perf.

---

## 2. Chess Analysis Agent  (Tier 2 — Compute)

**Responsibilities**
- Take a game/position and produce structured analysis: blunder list, key-moment list, eval graph, tactical motifs, positional themes, conversion-efficiency metrics.
- Coordinate Engine Orchestrator calls for multi-depth, multi-engine analysis.
- Classify mistakes (blunder/mistake/inaccuracy) with chess.com-compatible thresholds and CHESS COACH-extended categories (missed-tactic, premature-trade, time-pressure-induced, etc.).
- Detect tactical patterns (pins, forks, skewers, deflections, …) via heuristic + engine-PV inspection.
- Stream incremental results so the GUI updates as analysis progresses.

**Public API**
- `POST /analysis/games/{game_id}` → returns job_id, starts P2 async job.
- `POST /analysis/positions/{fen}` → returns analysis (P1 sync, short).
- `GET  /analysis/games/{game_id}` → returns latest analysis snapshot.
- Bus producer: `events.analysis.game.completed`, `events.analysis.position.ready`.
- Bus consumer: `events.games.imported` (auto-analyze on import if user opted in).

**Dependencies**: Engine Orchestrator, Memory Agent, Knowledge Base Agent (concept tags), python-chess.

**Data flow**
- Game → split into positions → batch engine eval (depth profile per game importance) → per-move classification → motif detection → store in `engine_analyses` + summary in `games.analysis_json` → emit event.

**Debugging strategy**
- Every analysis run logs an **analysis trace** (JSON) reproducible from `(game_id, engine_id, settings_hash)`.
- CLI: `chess-coach analyze game <id> --engine sf18 --depth 30 --dry-run` prints the plan without executing.
- Replayable: re-running with the same trace_id produces byte-identical output (deterministic engines + seeded heuristics).

**Scaling concerns**
- Embarrassingly parallel by position. Limit concurrency to (engines_available × CPU_cores ÷ 2).
- Per-game analysis budget (e.g. 30 s default) prevents runaway costs.

---

## 3. Engine Orchestrator  (Tier 2 — Compute)

**Responsibilities**
- Manage lifecycle of all installed UCI engines: start, configure (`setoption`), warm up, pool, terminate.
- Expose a uniform `analyze(fen, options) -> AnalysisResult` API across Stockfish, Leela, Maia, Berserk, Komodo, Ethereal.
- Multi-engine analysis: run N engines on the same position and aggregate.
- Engine tournaments / sparring (matches between engines or engine-vs-Maia for human-like play).
- Engine download / install / update (signed binaries).
- Resource governance (CPU, RAM, GPU for Leela).

**Public API**
- `POST /engines/{engine_id}/analyze` (P1 short or P3 streaming via WS).
- `GET  /engines` — list installed + metadata.
- `POST /engines/install` — download a new engine.
- `POST /engines/match` — start an engine vs engine game.
- Bus producer: `events.engine.analysis.stream.<corr_id>`, `events.engine.analysis.ready`, `events.engine.installed`.

**Dependencies**: `python-chess` (UCI protocol via `chess.engine`), filesystem (engine binaries), optional GPU drivers for Leela.

**Data flow**
- Request → pool selects free engine instance → UCI `position fen … go depth N` → parse `info` lines → emit incremental events → `bestmove` → write to `engine_analyses` cache → return.
- **Cache key** (canonical, post-review): `(fen, engine_id, engine_version, depth, multipv, settings_hash, cpu_arch, thread_count)`. `cpu_arch` is needed because NNUE SIMD paths (AVX2 / AVX-512) can produce divergent transposition orderings; `thread_count` because Stockfish parallel search is non-deterministic. Time-limited search MUST NOT be cached — depth-limited only.

**Debugging strategy**
- Raw UCI transcript logged per session (truncated to last 1 MB per engine).
- `/engines/{id}/debug` endpoint returns last transcript + current state.
- Health probe sends `isready` and times the `readyok` response.

**Scaling concerns**
- One process per engine instance (UCI is single-game). Pool size configurable; default = (logical_cores ÷ 2).
- Memory: Stockfish hash 1–4 GB default; configurable per engine.
- GPU contention for Leela: serialize Leela calls.

---

## 4. Psychological Profiling Agent  (Tier 2 — Compute)

**Responsibilities**
- Compute behavioral / psychological metrics from user games (and tracked opponents).
- Maintain time-series of metrics per player in `profile_metrics`.
- Detect patterns: tilt streaks, time-pressure quality degradation, opening comfort/discomfort, tactical-vs-positional bias, risk appetite, conversion ability, fear-of-complications, decision fatigue, endgame resilience.
- Generate **explainable** outputs: every metric has a definition, computation method, sample size, confidence interval, and supporting game/position evidence list.
- Build the **CHESS COACH Profile Score** (a thoughtfully composed multi-axis score; inspired by ChessStalker's Stalker Score but with confidence bands and explainability — see `docs/research/chessstalker-concepts.md`).

**Public API**
- `GET  /profiles/{player_id}` — current profile snapshot.
- `GET  /profiles/{player_id}/metric/{name}/history` — time-series.
- `GET  /profiles/{player_id}/explain/{metric}` — methodology + evidence.
- `POST /profiles/{player_id}/recompute` (P2 async).
- Bus consumer: `events.analysis.game.completed` → updates metrics incrementally.
- Bus producer: `events.profile.metric.updated`, `events.profile.alert` (e.g. "tilt pattern detected").

**Dependencies**: Chess Analysis Agent outputs, Memory Agent, `pandas`/`numpy`/`statsmodels`.

**Data flow**
- Incremental: on `events.analysis.game.completed` → update relevant rolling-window metrics + write to `profile_metrics`.
- Full recompute: scheduled weekly or on demand → rebuild all metrics from scratch.

**Debugging strategy**
- Every metric module exposes a `--explain` CLI flag printing the formula, inputs, intermediate values.
- Synthetic-data tests: known input games → expected metric outputs (`tests/profile/golden/`).
- Profile diffs over time stored to enable "why did this metric jump?" investigations.

**Scaling concerns**
- Metrics are per-player; trivially partitionable.
- Use materialized aggregates (`profile_metric_daily`) to avoid recomputing long histories.

---

## 5. Knowledge Base Agent  (Tier 1 — Data)

**Responsibilities**
- Maintain the chess knowledge corpus: PDFs ingested by PDF/Vision Agent, PGN annotations, engine-derived concepts, curated opening theory.
- Provide **semantic search** (vector) and **structured lookup** (SQL) and **hybrid** (BM25 + vector fusion).
- Maintain a chess **ontology** (openings, motifs, concepts, principles) and link content to ontology nodes.
- Build the **opening tree** keyed by ECO + transposition table.

**Public API**
- `GET  /kb/search?q=…&filters=…` (hybrid search).
- `GET  /kb/positions/{fen}/concepts` — concept tags for a FEN.
- `GET  /kb/openings/{eco}` — opening node.
- `POST /kb/index` — re-index a document.
- Bus consumer: `events.book.ingested`, `events.games.imported`.
- Bus producer: `events.kb.indexed`.

**Dependencies**: Qdrant (vector), SQLite (relational), Memory Agent.

**Data flow**
- Read: query → embed → Qdrant ANN → fetch payloads + SQL joins → rank → return.
- Write: document chunk → embed → upsert to Qdrant + SQL row.

**Debugging strategy**
- `/kb/debug/query` returns the full execution plan: query embedding norm, candidates per stage, scores.
- A **reindex consistency check** verifies SQL row count == Qdrant point count per collection.

**Scaling concerns**
- Embedding throughput is the bottleneck. Batch size 32, async pipeline.
- Qdrant HNSW params tuned for ≤100k vectors per collection initially; switch to disk-backed segments above that.

---

## 6. PDF/Vision Agent  (Tier 2 — Compute, on-demand via Celery)

**Responsibilities**
- Parse PDF books: extract text per page (PyMuPDF), extract images.
- Detect chess diagrams in images (YOLOv8 fine-tuned; heuristic OpenCV fallback).
- Reconstruct FEN from each diagram (board-detection + piece-classifier CNN).
- OCR text near diagrams to capture move sequences / annotations (PaddleOCR primary).
- Validate reconstructed FENs (legal position check; orientation re-check).
- Emit structured book records to the Knowledge Base.

**Public API**
- `POST /books/upload` (multipart) → returns job_id, starts P2 saga (see `06_multi_agent/`).
- `GET  /books/{id}/diagrams` — list reconstructed diagrams + confidence.
- `POST /diagrams/{id}/correct` — user-provided FEN correction (feedback loop).
- Bus producer: `events.book.page.parsed`, `events.book.diagram.detected`, `events.book.fen.reconstructed`, `events.book.ingested` (final).

**Dependencies**: PyMuPDF, OpenCV, PaddleOCR, PyTorch (YOLO + classifier), Memory Agent (store corrections as training data).

**Data flow**
- PDF → pages → (text, images) → diagram-detect → board-crop → orientation-detect → piece-classify → FEN → validate → store. Each step emits an event for the saga.

**Debugging strategy**
- Per-page **artifact dump**: original image, detection bounding boxes, piece-class confidences, final FEN, all saved to `data/debug/books/<book_id>/p<page>/`.
- A `/books/{id}/diagrams/{page}.png?overlay=detections` endpoint renders the visualization for UI inspection.
- Confidence threshold below X routes the diagram to a manual-review queue surfaced in the GUI.

**Scaling concerns**
- GPU-accelerated when available (YOLO + piece-classifier); CPU fallback is 5–10x slower but works.
- Books are split into 10-page Celery sub-tasks → near-linear parallelism.

---

## 7. Training Planner  (Tier 3 — Planning)

**Responsibilities**
- Generate personalized training plans based on Profile, Repertoire gaps, and stated goals.
- Manage spaced repetition over weak positions, missed tactics, repertoire lines.
- Compose lessons combining: explanatory text (LLM-generated), example positions, exercises, and recommended book chapters (from KB).
- Schedule training sessions on a calendar; track completion + outcomes.
- Adapt difficulty (SM-2 / FSRS algorithm) based on user performance.

**Public API**
- `GET  /training/plan` — current plan.
- `POST /training/plan/regenerate` (P2).
- `GET  /training/session/next` — next due training item.
- `POST /training/session/{id}/complete` — record outcome.
- Bus consumer: `events.profile.metric.updated` (regenerate-on-drift).
- Bus producer: `events.training.lesson.created`, `events.training.session.due`.

**Dependencies**: Profiling Agent, Repertoire Agent, KB Agent, LLM Router.

**Data flow**
- Profile snapshot + repertoire gaps + goals → planner heuristic + LLM synthesis → lesson units → store in `lessons` + `lesson_attempts` (FSRS state) → schedule.

**Debugging strategy**
- Plan generation logs include the input profile snapshot hash → reproducible plans.
- A `/training/plan/why` endpoint explains, per lesson unit, the profile/repertoire signal that triggered it.

**Scaling concerns**
- Single user, low frequency (weekly plan + daily session pick) → not a scale target.

---

## 8. Repertoire Agent  (Tier 3 — Planning)

**Responsibilities**
- Maintain user's opening repertoire as a tree (color × variation × position).
- Detect gaps (positions reached in user games that are not in repertoire).
- Suggest moves via Engine Orchestrator + cloud DB stats + GM databases.
- Detect novelties (positions reached vs known theory).
- Generate preparation reports against a specific opponent (pull opponent games → cluster openings → highlight weaknesses).
- Compare user repertoire vs GM repertoires.

**Public API**
- `GET  /repertoire/tree?color=white` — tree view.
- `POST /repertoire/lines` — add/update a line.
- `GET  /repertoire/gaps` — gap detection.
- `POST /repertoire/prepare/{opponent_id}` (P2) → preparation report.
- Bus consumer: `events.games.imported` (auto-gap-scan).
- Bus producer: `events.repertoire.gap.detected`, `events.repertoire.novelty.found`.

**Dependencies**: Engine Orchestrator, KB Agent (openings), Synchronization Agent (opponent games), python-chess.

**Data flow**
- Game move list walked against repertoire tree → unmatched node = gap → record.
- Opponent prep: opponent_id → fetch games → group by ECO → engine-evaluate critical positions → cross with user repertoire → produce report.

**Debugging strategy**
- Repertoire tree exportable as PGN / .ctg-like JSON.
- Gap-detection diff against last run logged.

**Scaling concerns**
- Tree can grow large (~100k nodes for serious players). Use SQLite recursive CTE for queries; cache hot subtrees in Redis.

---

## 9. Research Agent  (Tier 3 — Planning, scheduled)

**Responsibilities**
- Monitor curated sources (TWIC, ChessBase News, lichess blogs, top-player social, arxiv chess-AI tags) on a cron schedule.
- Identify newsworthy events: new top-level games in user's repertoire openings, engine releases, theoretical novelties.
- Pull and stage PGNs/PDFs for ingest.
- Produce a daily/weekly **research digest** delivered to the GUI as a notification.

**Public API**
- `GET  /research/digest/latest`.
- `POST /research/sources` — manage subscribed sources.
- `POST /research/run` (P2 manual trigger).
- Bus producer: `events.research.digest.ready`, `events.research.pgn.staged`.

**Dependencies**: LLM Router (for summarization + relevance judging), search engine API or scraping (with rate limits + caching).

**Data flow**
- Cron → fetch sources → dedupe via URL hash → LLM relevance judge → summarize → store digest → notify.

**Debugging strategy**
- Every research run is a tagged trace; raw fetched content cached for replay.
- `/research/runs/{id}` returns full trace.

**Scaling concerns**
- Polite rate-limiting per domain; ETag/If-Modified-Since respected.
- LLM cost bounded by daily budget (LLM Router enforces).

---

## 10. Memory Agent  (Tier 1 — Data)

**Responsibilities**
- Unified façade over the three memory tiers: episodic (SQL), semantic (Qdrant), procedural (markdown skills).
- API for any agent to `remember(fact)`, `recall(query)`, `forget(criteria)`.
- Maintain audit log of memory writes for explainability.
- Periodic memory consolidation: summarize old episodic entries into condensed semantic memories.

**Public API**
- `POST /memory/remember`.
- `GET  /memory/recall?query=…&tier=semantic|episodic|procedural|all`.
- `POST /memory/forget` (with confirmation token).
- `GET  /memory/audit?since=…`.

**Dependencies**: SQLite, Qdrant, KB Agent (for embeddings shared infra).

**Data flow**
- Write → optional embed → write to appropriate tier(s) → audit row.
- Read → fan-out to enabled tiers → merge + rank by recency × relevance.

**Debugging strategy**
- Full audit log of writes and forgets, immutable (append-only table).
- `/memory/explain?id=…` returns provenance chain.

**Scaling concerns**
- Episodic table grows linearly; consolidate-and-prune monthly job keeps it bounded.

---

## 11. Reporting Agent  (Tier 4 — Presentation)

**Responsibilities**
- Generate human-readable reports: post-game analysis report, weekly progress report, opening preparation report, psychological profile report, system audit report.
- Render to: HTML (in-app), PDF (export), markdown (Claude-review package), JSON (machine-readable).
- Compose LLM prose with deterministic data tables.
- Drive the **Saga Coordinator** for multi-agent sagas (book ingest, full-recompute, etc.) and report progress/failure.

**Public API**
- `POST /reports/generate` (P2) → returns report_id.
- `GET  /reports/{id}` → status + URLs.
- `GET  /reports/{id}/export?format=pdf|md|json`.
- Bus consumer: many, for saga monitoring.
- Bus producer: `events.report.ready`.

**Dependencies**: All Tier 1–3 agents (read-only), LLM Router, WeasyPrint or `pdfkit` for PDF.

**Data flow**
- Report template → fetch data from agents → compose → render → store under `data/reports/<id>/`.

**Debugging strategy**
- Report manifest JSON records every data source + version; reports are reproducible.
- LLM prompts and responses are saved per report for audit.

**Scaling concerns**
- PDF render is CPU-bound; offload to Celery.

---

## 12. Debug Agent  (Tier 4 — Admin)

**Responsibilities**
- Aggregate `/health` + `/ready` from all agents.
- Tail logs (Loki query or direct stdout subscription).
- Surface DLQ contents and let user retry/discard.
- Run diagnostic playbooks: "engine X not responding", "vector search returns nothing", etc.
- Generate **support bundles** (sanitized) — a tarball of recent logs, configs, schema versions, env metadata for external review.

**Public API**
- `GET  /debug/status` — system health overview.
- `GET  /debug/dlq`.
- `POST /debug/dlq/{event_id}/retry`.
- `POST /debug/bundle` → returns path to support tarball.
- `GET  /debug/agents/{name}/logs?tail=N`.

**Dependencies**: every other agent's `/health`, log store, DLQ stream.

**Data flow**
- Periodic pulls → cache in Redis → expose via API to GUI Debug Panel.

**Debugging strategy**
- Itself has a `--self-test` CLI that exercises every diagnostic path.

**Scaling concerns**
- Read-heavy, low concurrency. Trivial.

---

## 13. Synchronization Agent  (Tier 4 — Admin, scheduled)

**Responsibilities**
- Pull user's recent games from Lichess and Chess.com APIs.
- Pull cloud-eval and opening-stat data when needed (cached).
- Pull selected opponent games for preparation requests.
- Manage rate limits, auth tokens, and incremental sync cursors.

**Public API**
- `POST /sync/lichess/connect` (OAuth or PAT).
- `POST /sync/chesscom/connect`.
- `POST /sync/run` (P2) — manual full pull.
- `GET  /sync/state` — last cursor, last error per provider.
- Bus producer: `events.games.imported`, `events.cloud.eval.cached`.

**Dependencies**: HTTP client, OAuth lib, KB/Memory for caching cloud data.

**Data flow**
- Cron → read cursor from `cloud_sync_state` → fetch delta → parse PGN → write `games` rows → emit `events.games.imported` per game.

**Debugging strategy**
- Per-provider request log (sanitized — tokens redacted).
- `/sync/state/replay/{provider}` re-runs the last fetch in dry mode.

**Scaling concerns**
- Rate limits dominate. Single concurrent fetch per provider; backoff on 429.

---

## 14. LLM Router  (Tier 2 — Compute, in-process library)

**Not a service — a library.** Every agent that needs an LLM imports `chess_coach.llm` which is the Router.

**Responsibilities**
- Abstract over OpenRouter, direct OpenAI/Anthropic, and local Ollama/llama.cpp.
- Route each call to a provider based on **task profile** ("narration", "reasoning", "summarization", "embedding", "vision") + cost tier + latency budget + offline-mode flag.
- Token accounting per task profile per day → enforce daily budget.
- Caching by `(prompt_hash, model, temperature)` in Redis.
- Fallback chain: provider A → B → C → fail.
- Streaming support.
- Structured output: built-in JSON-mode + Pydantic validation + retry-on-parse-failure.
- Prompt template loader (markdown files under `chess_coach/llm/prompts/`).

**Public API (Python)**
- `await llm.run(task="narration", prompt=…, schema=PydanticModel)` → typed result.
- `await llm.stream(task="reasoning", prompt=…)` → async iterator.
- `llm.embed(texts: list[str], task="book_chunk")` → vectors.
- `llm.budget.remaining(task)` → tokens remaining today.

**Dependencies**: openrouter SDK / OpenAI SDK / Anthropic SDK / Ollama HTTP, Redis (cache + budget counter).

**Data flow**
- Call → cache check → provider route → request → response → cache write → budget decrement → return.

**Debugging strategy**
- Every call optionally logged to a `llm_calls` SQLite table (off by default for privacy; on in dev).
- `chess-coach llm replay <call_id>` re-runs a logged call with optional model swap.

**Scaling concerns**
- Per-provider concurrency caps (configurable). Default: OpenRouter 8 concurrent, local Ollama 1.
- Backpressure: if budget low, downgrade to cheaper model; if circuit open, fail fast.

---

# Post-Review Addenda (2026-05-18)

These sections were added in response to the Claude.ai architecture review (see `docs/13_review_response/`). They strengthen or clarify specific module specs without rewriting them.

## A-F2. Engine memory tiers (Module 3 — Engine Orchestrator)

The installer detects available RAM and recommends one of three modes; user can override.

| Mode | Detected RAM | Engines runnable concurrently | Stockfish hash cap | Local LLM |
|---|---|---|---|---|
| **Lite** | 8–12 GB | Stockfish only | 512 MB | not supported |
| **Standard** | 12–24 GB | Stockfish + (Maia OR Leela small net) | 1 GB | quantized 3B–7B optional |
| **Full** | 24 GB+ | Stockfish + Leela + Maia + LLM | 2 GB | up to 13B quantized |

The orchestrator enforces the mode at runtime: requests that would exceed the active mode's budget are rejected with a typed error (`EngineBudgetExceeded`) and the GUI surfaces a clear "upgrade mode" suggestion. This is the explicit response to the memory-OOM risk identified in the review (§7.2 + §11.2).

Mode is **per-installation, not per-session**. Switching requires a backend restart.

## A-F5. LLM Router degradation mode (Module 14)

When Redis is unreachable, the Router enters **degraded mode** rather than failing:

- Rate limiting becomes per-process in-memory (no cross-process coordination).
- Cache becomes per-process LRU (still useful within one run).
- Budget tracking falls back to a local file write with atomic rename; loses some accuracy at process boundaries.
- A one-time WARNING log line is emitted on entering degraded mode; the Debug Panel shows it.
- Recovery is automatic on next successful Redis ping.

For the Phase 1 monolith-first deployment (no Redis), the Router runs **permanently in degraded mode** until Redis is introduced. This is acceptable for single-user scale and removes Redis as a hard dependency.

## A-F6. Grounded LLM narration pipeline (Module 14 — **MANDATORY**)

This is the architectural mitigation for LLM hallucinations contradicting engine ground truth.

**Rule**: every LLM call that produces user-facing coaching narration MUST flow through the grounded-narration pipeline. Free-form LLM coaching output that bypasses this pipeline is forbidden by lint rule.

```
  Engine analysis available (best_move, eval_cp, top_pvs, classification, motifs[])
     │
     ▼
  GroundingPayload builder (Pydantic-typed, immutable)
     │
     ▼
  LLM Router: prompt = system_template + <ground_truth>…</ground_truth> + <user_content>…</user_content>
     │  Instruction: "Do not contradict <ground_truth>. If you cannot narrate without
     │   contradicting it, return the special token __NEED_FALLBACK__."
     ▼
  LLM response
     │
     ▼
  Narration validator (parses claims out of prose; cross-checks against GroundingPayload)
     │
     ├── consistent + no fallback token → deliver to user (also store call+response for audit)
     └── inconsistent OR fallback token → emit a deterministic template-rendered narration
                                          based purely on GroundingPayload; log discrepancy
                                          to `data/debug/llm_grounding_violations/`
```

The validator does not need to fully understand the prose — it checks for concrete falsifiable claims (a stated best move != ground-truth best move; a stated eval direction opposite to ground truth; a named motif not in `motifs[]`). When unsure, it errs on "consistent" so we don't over-reject; the audit log captures everything for offline review.

## A-F7. PDF parsing isolation (Module 6 — PDF/Vision Agent)

PDF parsing runs in an **isolated subprocess** with:
- **No network access** (use a subprocess wrapper that disables sockets via seccomp on Linux containers; on Windows, run as a separate Celery worker with no outbound DNS).
- **Read-only filesystem** except for the per-book artifact dir under `data/debug/books/<book_id>/`.
- **Memory limit** (cgroup on Linux; Windows job object) of 2 GB per parser process.
- **Timeout** of 5 minutes per page; exceeding triggers a clean kill + re-route to manual review.

This isolates the attack surface from PDF parser CVEs (PyMuPDF and PaddleOCR are large native-code stacks).

---

## Implementation Reality (as of 2026-06-13, commit `7c41b02`)

Modules below are **co-located in the gateway monolith**, not independently deployed services. Each has an isolated Python package (`__init__.py`) enabling future extraction without interface changes.

| Module (Vision) | Actual State |
|-----------------|-------------|
| GUI Agent | ✅ React 19 + Mantine 8 + Tauri. Talks to `127.0.0.1:18080` (not `:8765`). Typed OpenAPI client (`src/services/coach/`). |
| Engine Orchestrator | ✅ `services/chess_coach/engine_orch/pool.py` — Stockfish 18 subprocess pool, depth-configurable, parallel dispatch via `asyncio.gather`. |
| Analysis Cache | ✅ `analysis_cache` SQLite table — deterministic keying on fen+engine+depth+settings. |
| Narration Pipeline | ✅ `services/chess_coach/narration/` — grounded LLM output with validator and deterministic fallback. |
| LLM Router | ✅ `services/chess_coach/llm_router/` — OpenRouter primary, degraded mode when key absent. |
| Profile / Psychology | ✅ 5 metrics computed via SQL from game history. `/v1/profile/{player}/analysis`. |
| Training / FSRS | ✅ Full FSRS implementation — queue, review, seed, 7-day planner with priority scoring. |
| Repertoire | ✅ Tree, gaps, novelties, recommendations (parallel Stockfish dispatch). |
| Memory KB | ❌ Stubbed — `memory_kb/` package exists but contains no implementation. Qdrant spike validated pipeline architecture. Awaiting embedding format decision before pipeline code written. |
| Redis Streams bus | ❌ Not implemented. Deferred to Phase 6+. |
| Celery workers | ❌ Not implemented. Heavy async handled in-process with `asyncio`. |
| Remaining 6 modules | ❌ Empty `__init__.py` packages only. |

**Inter-module communication:** Direct Python function calls within the monolith, not Redis events. Tier rules from the multi-agent workflow doc are enforced by code review convention, not by network isolation.
