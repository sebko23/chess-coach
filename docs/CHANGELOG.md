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

## BBF-35 — fix(engine-pool): engine go timeout + dead-pid reset

`24bbb1c`. Closes ADR-0006 Findings 1 and 2: a hung
Stockfish `go` previously wedged the slot forever, and
a subprocess that exited between requests was silently
reused as a dead Popen and hung the next caller. New
`EngineHungError` exception, `engine_go_timeout_s`
parameter (default 30s) on the engine pool, and a
`slot.engine._proc.poll()` check in `_acquire()` that
catches dead-pid scenarios and starts a fresh subprocess.
Tests: `tests/unit/test_engine_pool_lifecycle.py` (10
tests across 4 classes, run in 1.17s with a FakeUCIEngine
monkeypatched into `pool.UCIEngine` -- no real
subprocesses, so the agentZero cgroup wedge from fake-hang
scripts is sidestepped). Real bug fix, no perf claim (per
BBF-21 discipline).

## BBF-36 — fix(eval-graph): coalesce concurrent first-viewers

`e69fb0c`. Closes ADR-0006 Finding 3: the eval-graph
route could be hit by multiple concurrent first-viewers
on the same `(game_id, ply, engine_id, depth)` cache
key. The analyses table's `INSERT OR IGNORE` prevented
corruption, but did not save redundant Stockfish work.
Added `_inflight` dict + `_get_dedup_lock()` +
`_dedup_get` / `_dedup_put` + `_coalesce_analyze` to
`services/chess_coach/gateway/routes/eval_graph.py`.
The `async with lock` wraps the get-then-put so two
concurrent first-views cannot both register as the
leader. Tests: `tests/unit/test_eval_graph_dedup.py`
(12 tests across 3 classes, run in 9.88s). The 100-call
stress test was the one that needed a test-bug fix
(missing `leader_started` / `release` synchronization
in the stress variant, mirroring the 2-call version);
without that fix the test deadlocked on
`release.wait()` inside the leader. **Efficiency
correctness fix, not a perf win** (per BBF-21
discipline) -- the bottleneck remains Stockfish per
`go()`, and no `MAX_WORKERS` change or gather
restructuring was made.

## BBF-37 — DEFERRED (needs macOS hardware)

The desktop discovery path in
`apps/desktop/src/state/atoms/coach.ts` hardcodes
`$HOME/.local/share/...` on all platforms, but the
backend writes to `%LOCALAPPDATA%\...` on Windows and
`~/Library/Application Support/...` on macOS. The
desktop cannot find the backend by default on
Windows/macOS without an explicit
`CHESS_COACH_DATA_DIR` set in both shells. **Deferred
indefinitely** -- needs macOS hardware to verify the
macOS leg, and the user has no current path to that
hardware. ~20 LOC, not started.

## BBF-38 — ci(smoke): poll /v1/system/health with curl, not docker inspect

`f05203b`. The original smoke workflow polled
`docker inspect --format={{.State.Health.Status}}` to
wait for the gateway. The Dockerfile's `HEALTHCHECK`
hard-codes the bearer token to `"***"` (a TODO marker
that was never replaced with the real value), so the
`HEALTHCHECK` CMD always 401s, the container's health
status never becomes `"healthy"`, and the old poll
timed out at 60s every run -- taking the smoke
workflow red since BBF-32. This BBF replaces the
`docker inspect` poll with a direct `curl` against
`/v1/system/health` using the real token. The poll
runs up to 120s, with periodic log output every 10s
and a final dump of the backend container's logs on
failure. This BBF is the change that surfaced every
subsequent missing-dep error in the BBF-39-44 chain
with a debuggable log instead of a silent timeout.
The commit message in `f05203b` contains a wrong claim
that the Dockerfile had no `HEALTHCHECK` directive; the
directive IS there (with the bad token), but the
fix is correct regardless of whether the directive
exists.

## BBF-39 — fix(routes): SUPERSEDED by BBF-43

`f8db480` (original), reverted in `f113f6c` (BBF-43).
The original BBF-39 added a PEP 562 lazy import for
`pdf_ingest_router` in
`services/chess_coach/gateway/routes/__init__.py` on
the theory that a missing optional dep should fail at
request time, not process startup. The design had a
bug: `from .routes import (..., pdf_ingest_router, ...)`
in `app.py:39` triggers the lazy `__getattr__` lookup
**at import time** (because `from X import Y` resolves
`Y` on `X` during the import), so the gateway
crashed on startup anyway. The unit test I wrote for
BBF-39 only checked `routes.pdf_ingest_router` directly
and "expected" the `ModuleNotFoundError` it observed,
which confirmed the broken behavior rather than
catching the bug. See BBF-43 for the fix.

## BBF-40 — build(deps): add aiohttp>=3.9 to runtime dependencies

`11fc5e9`. The lichess import endpoint at
`/v1/system/health/lichess/...` (handled by
`services/chess_coach/gateway/routes/lichess_import.py`)
streams NDJSON from `https://lichess.org/api/...` using
`aiohttp.ClientSession`. `aiohttp` was not in
`pyproject.toml`'s `[project.dependencies]`, so the
runtime image had no `aiohttp` and the gateway crashed
on startup. One-line addition: `aiohttp>=3.9`. Real
feature (Lichess game import), so making the dep lazy
(per BBF-39) was the wrong call -- adding the dep
restored the lichess import endpoint.

## BBF-41 — build(deps): add numpy, sentence-transformers, qdrant-client

`e97311e`. Continuing the missing-dep sweep that
BBF-40 started. The next smoke run surfaced
`ModuleNotFoundError: No module named 'numpy'` in
`services/chess_coach/kb/embedder.py`. A static scan
of every top-level import in the runtime tree found
three more eagerly-imported third-party deps the
runtime Docker image was missing:

  - `numpy>=1.26` -- used by `kb/embedder.py`
    (`np.array`, `np.stack`, `np.linalg.norm`) and
    `kb/store.py` (vector ops).
  - `sentence-transformers>=3.0` -- used by
    `kb/embedder.py` to load the embedding model.
  - `qdrant-client>=1.10` -- used by `kb/store.py`
    (`QdrantClient`, models).

Three-line addition. `scikit-learn` is imported lazily
inside `kb/embedder.py:validate_model` with an
`# local import, optional dep` comment, so it is
deliberately NOT in the runtime deps. `starlette` and
`dotenv` are import-name variants of already-declared
deps (`fastapi` pulls in `starlette`; `python-dotenv`
is imported as `dotenv`) -- no change needed.

## BBF-42 — build(deps): add pdf2image>=1.17 and poppler-utils

`a2e71c8`. The PDF ingest feature at
`POST /v1/import/pdf` (handled by
`services/chess_coach/gateway/routes/pdf_ingest.py`)
is a real production feature, not a stub. It extracts
chess diagrams from PDF pages via `chessvision.ai`.
It needs two runtime deps that were never declared:

  - The Python `pdf2image` package (a thin wrapper
    around the poppler CLI).
  - The Debian `poppler-utils` system package, which
    provides the `pdftoppm` and `pdftocairo` binaries
    that `pdf2image` shells out to.

Added `"pdf2image>=1.17"` to
`[project.dependencies]`. Added `poppler-utils` to
the `apt-get install` block in `Dockerfile`. The
BBF-39 lazy import is now dead code but not removed
in this BBF -- the follow-up BBF-43 handles the
revert.

## BBF-43 — refactor(routes): revert BBF-39 lazy import, add boot test

`f113f6c`. BBF-39's PEP 562 lazy import for
`pdf_ingest_router` was broken (see BBF-39). With the
BBF-42 dep addition, the lazy import is dead code.
This BBF:

  1. Restores `services/chess_coach/gateway/routes/__init__.py`
     to the pre-BBF-39 eager-import shape (45 lines vs
     BBF-39's 101). All 18 routers are imported at
     module load again.
  2. Deletes `tests/unit/test_routes_lazy_pdf_ingest.py`
     (the test that "expected" the broken
     `ModuleNotFoundError` and gave a false green).
  3. Adds `tests/unit/test_gateway_boots.py` (59 lines):
     a regression test for the entire BBF-38-42
     missing-dep cascade. Calls
     `chess_coach.gateway.app.create_app()` -- which
     imports every router module and registers the
     FastAPI app. This would have failed during BBF-39
     and caught the bug locally instead of waiting for
     a CI smoke run. Runs in 0.08s with no Docker, no
     real Stockfish, no network.

## BBF-44 — build(deps): add python-multipart>=0.0.9

`d198450`. The PDF ingest route at
`POST /v1/import/pdf` takes a file upload:

```
@router.post(...)
async def import_pdf(
    file: UploadFile = File(...),
    ...
)
```

FastAPI needs the `python-multipart` package to parse
`multipart/form-data` requests. When a route signature
includes `File` or `UploadFile`, FastAPI calls
`ensure_multipart_is_installed()` at module-load time.
This dep is **not picked up by static import scanners**
because `python-multipart` is never imported directly
-- FastAPI detects the `File` / `UploadFile` /
`Form` annotations in route signatures and requires it
implicitly. Added `"python-multipart>=0.0.9"` to
`[project.dependencies]`. Honest framing: the BBF-43
boot test catches the failure at runtime, but only when
run in a clean install. A CI step that does a clean
`pip install -e .` before running the boot test would
close this loop (BBF-46).

## BBF-45 — ci(smoke): install pytest for the smoke test runner

`a06905e`. The smoke test file
`tests/integration/smoke_test.py` is dual-mode: it can
be invoked as `python tests/integration/smoke_test.py`
(standalone, what the CI workflow uses) or as
`pytest tests/integration/smoke_test.py` (the
pytest-mode entry point with skip-on-no-gateway
fixtures, used by devs locally). The file does
`import pytest` near the bottom (around line 194) for
the pytest-mode fixtures. That import runs even in
standalone mode because Python parses the whole file
before executing the top-level `main()` block. The CI
workflow's step 4 "Install smoke test deps" only
installed `httpx`, so the import failed with
`ModuleNotFoundError: No module named 'pytest'` on
every run since the smoke workflow was introduced
(BBF-29). This BBF installs `pytest` and
`pytest-asyncio` alongside `httpx` in the workflow
step.

## BBF-46 — ci(smoke): SUPERSEDED by BBF-47 (workflow file was committed at pre-BBF-38 content)

`8dd117b` (broken), fixed in `5ae4ca7` (BBF-47). The
original commit was meant to add a new `gateway-boot`
job to the smoke workflow that runs the boot
regression test in a clean venv. Instead, the commit
regressed the workflow to the pre-BBF-38 / pre-BBF-45
state: removed the curl-poll loop, removed the
`pytest` install, and removed the gateway-boot job
itself. The host file I patched was correct (181 lines,
with both the new gateway-boot job AND the existing
BBF-38/45 content preserved), but the next step in my
workflow overwrote the clean-clone file with the
agentZero-working-tree copy, which was the stale
pre-BBF-38 / pre-BBF-45 version (the bind-mount working
tree had not been kept in sync with the recent
workflow edits because the bind-mount is one-way
host-to-container, not the other direction). See BBF-47
for the proper end state.

## BBF-47 — ci(smoke): fix BBF-46 (file was committed at pre-BBF-38 content)

`5ae4ca7`. Restores the intended BBF-46 content: the
gateway-boot job from BBF-46 is now present, and the
smoke job retains the BBF-38 curl-poll loop AND the
BBF-45 pytest install. 181 lines total, +109/-7
relative to the BBF-46 (broken) state. The regression
caught itself cleanly: the smoke workflow went red on
the BBF-46 push with a clear
`ModuleNotFoundError: No module named 'pytest'`, the
same class of error the BBF-38 / BBF-45 changes were
supposed to eliminate. Total commits in the BBF-38 to
BBF-47 chain: 10 (38, 39, 40, 41, 42, 43, 44, 45, 46,
47). All required. Honest framing per BBF-21: I lost
track of the file's content during the cp chain and
should have re-read the file in the clean clone BEFORE
committing, not just after.

## BBF-48 — docs(repo): catchup CHANGELOG + update REPO-READINESS audit section

`5ae4ca7`+docs. Docs-only catchup. The previous CHANGELOG
entry (BBF-34) jumped straight to the pre-BBF-35
audit state. This entry adds the BBF-35 to BBF-47
sprint history so a new dev reading the changelog has
an accurate picture of the cascade fix. The
REPO-READINESS doc's "Known issues (BBF-34 audit)"
section previously listed BBF-35 / BBF-36 / BBF-37 as
"fix planned" -- that section is updated to
"Fixed in `24bbb1c`" / "Fixed in `e69fb0c`" /
"Deferred indefinitely". The "Sprint history" footer
is updated to "BBF-1..BBF-47" instead of "BBF-1..BBF-26".
No code touched.



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
