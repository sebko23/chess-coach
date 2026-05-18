# `services/` — Backend services (Phase-1 in-process; later extractable)

**License**: Apache-2.0.

Per the monolith-first decision (`docs/10_roadmap/phase-plan-v2.md`), Phase 1–3 ships every "service" listed in `docs/02_modules/module-decomposition.md` as a Python package inside one process. Extraction to separate processes (or containers) happens *empirically* when a real workload demands it — never speculatively.

Phase-1 packages live here:

| Package | Purpose |
|---|---|
| `chess_coach.gateway` | FastAPI app, WS multiplex, auth, error envelope. |
| `chess_coach.engine_orch` | UCI process manager, Stockfish adapter, analysis cache. |
| `chess_coach.analysis` | Move-scoring, blunder classification, motif detection. |
| `chess_coach.narration` | Grounded narration pipeline (mandatory per binding rule). |
| `chess_coach.llm_router` | OpenRouter adapter, budget tracking, fallback. |
| `chess_coach.memory_kb` | SQLite + FTS5 storage; merged module for Phase 1. |
| `chess_coach.debug` | Log multiplexer, health endpoints, debug topics. |
| `chess_coach.jobs` | SQLite-backed job queue (no Redis/Celery in Phase 1). |

Each package has its own README once authored in Phase 1.
