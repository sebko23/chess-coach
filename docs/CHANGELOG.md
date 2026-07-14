# CHESS COACH Changelog

Sprint history for the chess-coach repo. BBF = "Bug Fix / Feature" sprint.
Sprints are sequential; later sprints build on earlier ones.

## BBF-30 — feat(ci): GitHub Actions smoke test workflow

`.github/workflows/smoke.yml`. New workflow that runs
`tests/integration/smoke_test.py` against a fresh build of the
backend Docker image on every push to main and every PR. Uses
the `services:` pattern with an explicit healthcheck so the
runner waits for the gateway to be healthy before running the
test. Runs on `ubuntu-latest` only (Docker service pattern
limitation). Single job (`smoke`), 5 steps: checkout, setup
Python 3.11, install httpx, run smoke test, dump backend logs
on failure. Concurrency group cancels in-progress runs for the
same branch on rapid pushes. The Dockerfile build itself is
not separately tested (no `hadolint` available in this
environment); the smoke test catches runtime issues.

Refs: BBF-28 (the Dockerfile the workflow builds), BBF-29
(the smoke test the workflow runs), docs/REPO-READINESS.md
(smoke test instructions)

## BBF-29 — feat(tests): end-to-end smoke test script

`tests/integration/smoke_test.py`. Dual-mode: standalone
(`python tests/integration/smoke_test.py`) and pytest
(`pytest tests/integration/smoke_test.py`). Hits a real running
gateway over HTTP, imports a 7-ply PGN, fetches the eval-graph
twice (cache miss + cache hit), verifies all positions have
`score_cp` populated. Exits 0 on success, 1-4 on specific failure
modes. Reads `CHESS_COACH_BASE_URL` and `CHESS_COACH_BACKEND_TOKEN`
env vars (defaults match the docker-compose dev defaults). Skips
cleanly under pytest if the gateway is unreachable so CI doesn't
fail on a dev machine without the backend.

Verified end-to-end against the live gateway: 0.17s import,
11.95s first eval (7/7 with score_cp), 0.05s cache hit, 0 exit.

## BBF-28 — feat(infra): backend Dockerfile + docker-compose

`f4b1e1f`. The backend now runs without the agentZero container.
A new dev can `git clone` and `docker compose up` to get a working
gateway on http://127.0.0.1:18080 in under a minute, no agentZero
image, no manual token setup. 5 files: Dockerfile (single-stage
`python:3.11-slim-bookworm`, stockfish via apt, uv 0.4.18, non-root
user, tini as PID 1, healthcheck), docker-compose.yml (one
backend service, port 18080 published to 127.0.0.1, ./data
bind-mount, dev-token env var, logging driver), .dockerignore
(keeps the build context small), BUILDING.md (added the
"Running the backend in Docker" section), README.md (added a
"Backend (Docker)" subsection). Build not verified end-to-end in
this environment (host's Docker daemon not accessible from
agentZero); the first dev who runs `docker compose build` should
verify in < 60s.

## BBF-27 — docs(repo): repo-readiness docs refresh

`2b5b6bb`. Five docs files + one new reference file. README.md
rewritten from 132 lines of legal/architectural content to a
1-page dev-focused quick start. CONTRIBUTING.md rewritten from
the upstream en-croissant copy to chess-coach specific;
documents the BBF-N brief workflow, pre-commit UTF-8 hook,
no-secrets-in-commits rule, and the frontend fork subtree
strategy. BUILDING.md kept the existing prereqs and build
commands; added an env vars table, dev-token workflow, lazy
eval-graph behavior note, and cgroup/thread-limit caveat.
docs/REPO-READINESS.md (NEW) is the operational guide for
"I just cloned this repo, what do I do?" with 8 common pitfalls.
docs/CHANGELOG.md (NEW) is the BBF-18..BBF-26 sprint history in
human-readable form. .upstream-ref (NEW) is the en-croissant
fork SHA referenced by CONTRIBUTING.md.

## BBF-26 — fix(gui): use real /v1/import/pgn route (was hitting 404)

`860ad89`. The Import PGN button was calling `/v1/import/pgn-database`,
which is not a real backend route. Changed to `/v1/import/pgn` and
added `max_plies: 200` to the request body. Banner now shows positions
count too. Three-line diff in `apps/desktop/src/components/panels/games/GamesPage.tsx`.

## BBF-25 — docs(strategic): 6000-game stress test passed

`fd9b507`. Verified the BBF-22 lazy architecture on a 6000-game
synthetic PGN. Import: 43.8 s (vs pre-pivot estimate of 33+ h, ~2700× speedup).
First eval-graph for 5 random games: median 1.05 s, 100% score_cp.
Cache hit: median 86 ms. Full results in `docs/17_lazy_eval_graph/RESULTS.md`.

## BBF-24 — feat(gui): Compute full analysis button on game detail

`ecd24e2`. Added a button + depth selector on the game detail page
that pre-warms the lazy cache at a chosen depth. Reuses the existing
GET `/v1/games/{id}/eval-graph` route (no new backend endpoint —
the spec's planned `POST /v1/games/{id}/eval` would have been
duplicate code after BBF-22 made the GET route lazy). 93 lines added
in `GameDetailPage.tsx`.

## BBF-23 — feat(gui): drop unused depth from import request body

`7e862e1`. After BBF-22 made import a pure-insert operation, the
GUI's hard-coded `depth: 8` was inert (the eval-graph route uses
`?depth=6` by default, so the import's depth never reached the cache).
Removed it. One-line diff in `GamesPage.tsx`.

## BBF-22 — feat(import): lazy eval-graph for 6000-game scaling

`411f7a1`. The strategic pivot. PGN import is now a pure-insert
operation; analyses are computed lazily on first eval-graph request
and cached. Import time is independent of corpus size. 6000-game
PGN imports in seconds instead of 33+ hours. Spec at
`docs/17_lazy_eval_graph/SPEC.md`. Implementation pitfalls
(aiosqlite per-connection background thread, missing commit) in
`references/bbf-22-implementation-pitfalls.md` of the
chess-coach-stockfish-perf-debug skill.

## BBF-21 — refactor(backfill): BBF-21 two-phase pipeline (no perf speedup over BBF-20)

`fb06288`. Refactored the backfill route into a three-phase pipeline
(load+walk+check → one big stockfish gather → per-game INSERTs).
**Code quality only.** The bottleneck is `pool.analyze()`, not the
orchestration; no perf speedup over the per-game gather loop.
The honest framing lesson is now in the
chess-coach-stockfish-perf-debug skill.

## BBF-20 — feat(import): GUI backfill button + fix backfill route decorator

`c6cb707`. Added the Backfill analyses button + depth selector to
the games list. Found that the `@router.post` decorator on
`backfill_analyses` had been left on the extracted `_analyze_and_insert`
helper, not the real handler — every request was returning 422.
Moved the decorator. Two-file change, ~120 lines.

## BBF-19 — feat(engine-pool): N-slot parallelism for true Stockfish concurrency

`71eb1c5`. Replaced single-slot-per-engine with N-slot-per-engine.
Each slot owns its own UCIEngine subprocess and per-slot asyncio.Lock.
Round-robin slot selection. `CHESS_COACH_MAX_WORKERS=N` env var.
Verified 1.3× speedup over single-slot (DB writes cap the
parallelism, not stockfish itself).

## BBF-18 — fix(stockfish): remove non-reentrant lock re-acquisition in _acquire (BBF-18 deadlock)

`8654bb5`. The original BBF-18 commit (`c7220a5`) widened the
per-engine asyncio.Lock scope in `analyze()` to cover the entire
body, but `_acquire()` still did `async with self._locks[spec.engine_id]`
inside that scope — `asyncio.Lock` is not reentrant, so the second
acquisition blocked forever. Removed the inner lock. Symptom: curl
times out at 30 s with HTTP 000, gateway.log is empty.

## BBF-17 (and prior) — mojibake fix, PGN import route, etc.

The pre-BBF-18 history. The handoff at `docs/17_lazy_eval_graph/`
references the original `c7220a5` commit as the BBF-18 wire-up; the
handoff's BBF-1..BBF-15 work is in `f9574f1` and earlier commits.
The UTF-8 mojibake pre-commit hook (BBF-17) is still in place and
runs on every commit.

## Strategic pivot context

Before BBF-22, the architecture was "eager pre-compute at import time":
importing 6000 games would have taken ~33 hours because every ply of
every game was analyzed by Stockfish before the route returned.
The user raised this as a real problem ("what if the database will be
6000?"). BBF-22 is the answer: lazy evaluation. Most users view a
tiny fraction of their corpus, so the lazy mode does 1%+ of the
eager work for typical usage. Verified at 6000-game scale in
BBF-25: 43.8 s import, ~1 s first-eval per game, instant cache hits.

## Status legend

- **Closed** — shipped to main, verified end-to-end
- **In progress** — being worked on
- **Open** — on the roadmap, not yet started

## Roadmap

The next planned work after BBF-26 is the repo-readiness push
(BBF-27 onwards). The goal: a new developer can clone the repo and
have a working backend + desktop end-to-end with documented setup.
After that, the strategic pivot to PDF/Vision (Phase 6) is the
biggest single piece of work, but the lazy architecture makes its
compute footprint smaller, so the ordering is right.
