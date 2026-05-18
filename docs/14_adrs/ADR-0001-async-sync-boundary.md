# ADR-0001: Async/sync boundary in backend services

- **Status**: accepted
- **Date**: 2026-05-18
- **Deciders**: project owner
- **Consulted**: Claude.ai review (recommendation to clarify before code begins)

## Context

The Phase-1 backend is a single Python process running FastAPI + asyncio for I/O-bound work plus several CPU-bound or blocking-stdio workloads:

- Stockfish UCI process I/O (line-oriented, blocking stdin/stdout)
- SQLite writes (blocking, single-writer due to WAL)
- LLM HTTP calls (I/O-bound, naturally async)
- Vector embedding (Phase 3+, CPU-bound)
- PDF parsing (Phase 6+, CPU-bound and memory-heavy)

If we mix asyncio and threading carelessly we'll get the worst of both: occasional deadlocks, blocked event loops, and confusing stack traces during debugging.

## Decision

The backend uses **a single asyncio event loop** in the main process. Blocking work is moved off the event loop via these explicit boundaries:

1. **Engine UCI I/O** runs in a dedicated `asyncio.subprocess` per engine instance, with `asyncio.StreamReader/StreamWriter` for line I/O. No threads.
2. **SQLite writes** go through a single `aiosqlite` connection per database file, used by a single writer task. Reads use a pool of `aiosqlite` connections (WAL allows concurrent reads).
3. **CPU-bound work** (Phase 3+: embedding; Phase 6+: PDF parsing) runs in `loop.run_in_executor(ProcessPoolExecutor(...))` — a process pool, not a thread pool, to escape the GIL.
4. **Long-blocking C extensions that don't release the GIL** (none in Phase 1) would run via `run_in_executor(ThreadPoolExecutor(...))` only after a documented benchmark showing the thread pool is sufficient.
5. **Third-party sync libraries** (e.g. `python-chess` move generation, which is fast and pure-Python) may be called directly from async code provided the call completes in <1ms; longer calls go through the executor.

The `asyncio.run` entrypoint is `apps/cli/__main__.py` (and the Phase-8 PyInstaller wrapper). FastAPI's own ASGI loop is the same loop; no nested loops, no `asyncio.run_until_complete` from inside running coroutines.

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| Pure threading | simpler mental model | GIL contention; FastAPI/Starlette are async-native | gives up FastAPI's strengths |
| Trio + Hypercorn | structured concurrency | smaller ecosystem; non-standard | mainstream asyncio + FastAPI is the well-trodden path |
| Multiple processes per concern | true parallelism | premature decomposition (review §1.3); IPC overhead | violates monolith-first decision (`phase-plan-v2.md`) |

## Consequences

### Positive

- One loop = one debugging mental model.
- `asyncio.subprocess` for engine I/O is well-supported and battle-tested.
- Process pool for CPU work scales linearly with cores when needed (Phase 3+).

### Negative / accepted tradeoffs

- Bug class: blocking calls slipping into async code stall the entire process. Mitigation: ruff rule for sync I/O in async functions, plus integration test that asserts the event loop never blocks > 50ms during a representative workload (test in `tests/perf/`).
- Process pool startup is slow (~1-2s per worker on Windows). Mitigation: pre-warm pool at gateway startup when CPU-bound features are enabled.

### Follow-up actions

- Add a ruff `flake8-async` configuration to the project's ruff settings (Phase 1).
- Add the "event loop never blocks > 50ms" perf test as part of Phase 1 acceptance criteria.

## References

- `docs/02_modules/module-decomposition.md` § engine_orch (async UCI choice)
- `docs/10_roadmap/phase-plan-v2.md` § Phase 1
- Python docs: https://docs.python.org/3/library/asyncio-subprocess.html
