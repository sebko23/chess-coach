# Performance Strategy

## Performance budgets (targets, not floors)

| Operation | p50 | p95 | Hard ceiling |
|---|---|---|---|
| Open a PGN (single game) | 50 ms | 200 ms | 1 s |
| Position eval at depth 22 (Stockfish, 1 thread) | 300 ms | 800 ms | 3 s |
| Full-game analysis (40 moves, depth 22 multi-PV 3) | 8 s | 20 s | 60 s |
| Semantic KB search (top-10) | 80 ms | 250 ms | 1 s |
| Profile snapshot generation | 200 ms | 600 ms | 2 s |
| Book ingest (100-page PDF, GPU) | 30 s | 90 s | 5 min |
| Book ingest (100-page PDF, CPU) | 3 min | 8 min | 20 min |
| GUI cold start (Tauri shell) | 600 ms | 1.2 s | 2 s |
| Backend cold start (all services) | 5 s | 12 s | 30 s |
| WS message round-trip (engine stream) | 5 ms | 25 ms | 100 ms |

Budgets are codified in a `tests/perf/budgets.yaml` and asserted by perf tests in CI.

## Async + concurrency model

- **FastAPI services**: async I/O end-to-end (asyncpg-style patterns over aiosqlite). CPU-bound work is offloaded to a thread pool or to Celery.
- **Engine Orchestrator**: each engine instance runs in its own subprocess; orchestrator uses an async pool to dispatch.
- **Celery workers**: separate compose services for `worker-heavy` (PDF/OCR/YOLO) and `worker-light` (LLM, KB indexing). Concurrency tuned per worker (`-c 2` for heavy, `-c 8` for light).
- **Frontend**: React Query handles client cache + dedup. Heavy lists (large PGN files) use virtualization (`@tanstack/react-virtual`).

## Caching layers

1. **In-process LRU** (`cachetools.TTLCache`) for hot lookups within a single request (e.g. opening name from FEN).
2. **Redis** keyed by hash for: LLM responses, engine analyses, cloud API responses, embedding vectors.
3. **SQLite materialized views** for: heatmaps, profile-metric daily aggregates, opening tree subtree summaries.
4. **CDN-style on-disk cache** for: downloaded engine binaries, PDF page images, generated diagram crops.

Cache keys always include a **version tag** so that engine upgrades, embedding model swaps, or schema migrations invalidate cleanly without manual flush.

## Incremental indexing

- New games trigger **incremental** updates to Qdrant + profile metrics; full reindex is only on schema bumps.
- Book ingest is per-page checkpoint — interrupting mid-book resumes from the last completed page.
- Engine analysis cache is keyed by (FEN, engine_id, depth, multipv, settings_hash); higher-depth results supersede lower-depth.

## Profiling + benchmarking discipline

- `py-spy` for sampling profiles of any agent (`/debug/agents/{name}/pyspy` endpoint, dev-only).
- `pytest-benchmark` for micro-benchmarks of hot Python paths (move generation, FEN parse, motif detection).
- A `bench/` directory holds reproducible engine benchmarks (fixed FEN list, fixed depth) used to regression-test engine config changes.
- Frontend: React DevTools Profiler + a `--perf` URL flag that turns on console timing for major panels.

## Large dataset handling

- **PGN files**: streamed via python-chess `read_game` generator — never load entire file into memory. Imports are chunked with progress events.
- **PDFs**: PyMuPDF reads pages on demand; image extraction streamed.
- **Qdrant**: HNSW in-memory up to ~100k vectors per collection; switch to mmap segments above that (Qdrant config flag).
- **SQLite**: WAL mode, `mmap_size=1GB`, `cache_size=-100000` (100 MB), `synchronous=NORMAL`. PRAGMAs set on every connection by a connection-factory.

## Backpressure

- Redis Stream consumer groups apply natural backpressure (pending entries).
- Celery queues set a `task_acks_late=True` + `worker_prefetch_multiplier=1` so a worker grabs only what it can run.
- WebSocket producers buffer up to 64 messages per client; on overflow they drop oldest and emit a `events.ws.dropped` event so clients can request a snapshot resync.

## Resource caps (defaults; user-configurable)

| Resource | Default cap |
|---|---|
| Stockfish hash | 1 GB total across pool |
| Engine threads | logical_cores − 2 (min 1) |
| Celery memory per worker | 2 GB (`--max-memory-per-child`) |
| LLM daily token budget | configurable per task profile |
| Qdrant memory | 2 GB soft cap (mmap above) |
| Background analysis concurrency | 2 games in flight |
