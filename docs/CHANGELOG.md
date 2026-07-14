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

## BBF-34 — docs(repo): code audit + reviewer response

`TBD`. Five-file docs push + one new ADR in response to an
external developer review (2026-07-14). Files changed:

- `docs/14_adrs/ADR-0006-engine-pool-failure-modes.md` (NEW,
  252 lines): the audit findings from reading the actual code
  for engine_orch/pool.py and gateway/routes/eval_graph.py.
  Five findings; three are real bugs (BBF-35, BBF-36, BBF-37
  fixes pending); one is benign; one is deferred indefinitely.
  Each finding has explicit "Current behavior" sentences so
  the user-visible impact is documented.
- `docs/README.md` (NEW, 76 lines): index of the docs directory
  with two reading orders ("just cloning" vs "new to the
  codebase") and a doc-layout table.
- `tests/README.md` (NEW, 138 lines): index of the test
  directory with the smoke-test, pytest, and perf-test
  workflows. Documents the BBF-29 smoke test and the BBF-25
  perf-test history.
- `LICENSING.md` (replaced, 75 lines): was 1-paragraph legal
  guidance. Now a quick-license-matrix table + contributor
  licensing + downstream-use notes. NOTE: the existing
  LICENSING.md already had a license matrix inside it; the
  BBF-34 LICENSING.md is a refactor that pulls the table
  above the fold and adds contributor / downstream guidance.
- `README.md` (+~80 lines): added "Who is this for?" and
  "Architecture in 60 seconds" with an ASCII data-flow diagram.

Total: 6 files, ~600 insertions.

Refs: External developer review (2026-07-14); BBF-22 (the lazy
eval-graph architecture the audit examined); ADR-0001
(async/sync boundary, which the engine pool follows).

## BBF-33 — fix(ci): rebuild image in a step, not as a service

`a6032c4`. The original smoke.yml (BBF-30, commit be24395) used
the `services:` keyword with a `build:` directive. That pattern
FAILS on the GitHub Actions ubuntu-latest runner -- the workflow
parses to 0 jobs and fails before any job runs. Verified
empirically with 4 diagnostic workflows:

  smoke-simple (no services)               success
  smoke-services-only (just image:)        success
  smoke-no-concurrency (build:+image:)     failure (0 jobs)
  smoke-prebuilt (just image: in           failure (1 job,
    services, image not in registry)         image pull failed)

The bisect isolated `services: <name>: build:` as the cause.
This is a known limitation; the runner cites this as a "services
don't support build" error but the message isn't surfaced through
the public Actions API.

The fix: build the image in a regular `docker build` step and
run the gateway as a background `docker run`, then poll the
healthcheck. The 4 diagnostic workflows are deleted; the rewrite
of smoke.yml is captured in this commit.

BBF-33 was committed in this session but the push to GitHub
happened in this BBF-34 commit because BBF-33's push was
deferred.

Refs: BBF-30 (the original broken smoke.yml), BBF-29 (the smoke
test), BBF-28 (the Dockerfile the workflow builds).

## BBF-32 — docs(repo): verification guide + catchup CHANGELOG

`519857f`. `docs/VERIFICATION.md` (NEW, 186 lines) is the
next-dev-facing guide for closing the BBF-28 (Dockerfile) and
BBF-30 (CI workflow) verification gaps. Documents which
gaps remain, how to verify each one (step-by-step), what to do
if a verification fails, and explicitly calls out the
"Reporting back" loop so the next dev knows to update the
CHANGELOG and the commit messages when they close the loop.
CHANGELOG: added the deferred BBF-30 and BBF-31 entries.

## BBF-31 — chore(setup): .env.example + .dockerignore fix

`a0fa235`. Two small follow-on fixes to the BBF-27..30 repo-readiness
push. `.env.example` (NEW, 61 lines) is a template for the local-venv
workflow: lists the 3 env vars a dev needs (CHESS_COACH_BACKEND_TOKEN,
CHESS_COACH_MAX_WORKERS, CHESS_COACH_DATA_DIR) plus optional network
overrides. The actual `.env` is gitignored (secrets stay out of
git). `.dockerignore` (MODIFIED, +3 lines) had a bug: the
`**/.env` glob also matched `.env.example`, so the Docker build
context excluded the template. Added `!**/.env.example` and similar
negation patterns to explicitly re-include templates. The first
dev who runs `docker compose build` will now find the template in
the container.

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
