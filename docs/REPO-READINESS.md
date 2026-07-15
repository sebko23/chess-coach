# REPO-READINESS — what to do after a fresh clone of this repo

**Audience**: a developer who just cloned
`github.com/sebko23/chess-coach` and wants to know what works,
what's broken, and where the sharp edges are.

Last updated: 2026-07-15 (BBF-52).

---

## TL;DR

```bash
git clone https://github.com/sebko23/chess-coach.git
cd chess-coach
docker compose up --build          # backend on http://127.0.0.1:18080
curl -sS http://127.0.0.1:18080/v1/system/health \
  -H 'Authorization: Bearer devtoken123'
```

If you don't have Docker, the fallback path is the agentZero
container (the original dev workflow); see "Alternatives"
below.

---

## What's in this repo

- **Backend** (`services/chess_coach/`): a FastAPI monolith
  gateway with Stockfish analysis, Lichess import, opening
  repertoire, training planner, profile analysis, narration,
  and a KB vector store backed by Qdrant.
- **Libraries** (`libs/chess_coach/`): shared code used by the
  backend services (storage, protocol types, UCI adapter,
  datasets, errors, testkit).
- **CLI** (`apps/cli/chess_coach/`): the `chess-coach` and
  `chess-coach-gateway` entry points.
- **Desktop** (`apps/desktop/`): Tauri/React GUI. NOT included
  in `docker compose up` -- run it locally with `pnpm tauri dev`.
- **Docs** (`docs/`): everything from architecture decisions to
  per-feature results. Index in `docs/README.md`.
- **Tests** (`tests/`): unit, integration, e2e, perf, and the
  L-2 gold corpus (`tests/gold/L2/v1/corpus.json`).
- **Roadmap** (`docs/10_roadmap/phase-plan-v2.md`): the v2 plan
  with phase-percentages table and current progress.

---

## Supported platforms

Per BBF-50 (2026-07-15):

| Platform  | Status                       | Notes                                                |
|-----------|------------------------------|------------------------------------------------------|
| Linux     | Primary + CI-tested          | The GitHub Actions smoke workflow runs on ubuntu-latest. |
| Windows   | Experimental                 | Some dev work happens on Windows. See "Pitfall: agentZero is Linux-only" below. |
| macOS     | Experimental                 | Not currently in CI. Hardware not available to maintainers. |

Windows/macOS support is expected to move from "experimental" to
"supported" at Phase 8 (packaging + installer work).

---

## First-run recipe (Linux, with Docker)

```bash
git clone https://github.com/sebko23/chess-coach.git
cd chess-coach
docker compose up --build
```

This brings up two containers:

- `chess-coach-backend` -- the FastAPI gateway on port 18080.
- `chess-coach-qdrant` -- the Qdrant vector store sidecar on
  port 6333 (loopback only).

The `./data` directory is bind-mounted; the SQLite DB, runtime
descriptor, engine binaries, and Qdrant storage all live there
and survive `docker compose down` (without `-v`).

### Verify

```bash
TOKEN=devtoken123

# 1. Backend health
curl -sS http://127.0.0.1:18080/v1/system/health \
  -H "Authorization: Bearer $TOKEN" | jq .

# 2. Backend identity + capabilities
curl -sS http://127.0.0.1:18080/v1/system/info \
  -H "Authorization: Bearer $TOKEN" | jq .

# 3. Trigger an index of positions from your local SQLite
curl -sS -X POST http://127.0.0.1:18080/v1/kb/index \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit": 5000}' | jq .

# 4. Query for positions similar to a FEN
curl -sS -X POST http://127.0.0.1:18080/v1/kb/similar \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1","top_k":5}' | jq .
```

### Inspect the Qdrant sidecar directly

```bash
# List collections
curl -sS http://127.0.0.1:6333/collections | jq .

# Inspect the 'positions' collection
curl -sS http://127.0.0.1:6333/collections/positions | jq .
```

---

## Alternatives

### agentZero container (legacy / non-Docker dev)

The original dev workflow used a Linux container named
`agentZero` with Stockfish, Qdrant, and the gateway running
in-process. The container is bind-mounted to
`C:/chess-coach/desktop/` on the host (one-way: writes from
the host do not reflect back into the container). Use this
when:

- You're on Windows but the dev environment is Linux
  (bind-mount + docker exec).
- You want to iterate on Python without rebuilding the Docker
  image on every change.

Quick reference (from the BBF-sprint skill):

```bash
docker exec -i agentZero bash -lc '
  cd /a0/usr/projects/chess_coach
  rm -f /tmp/chess_coach_gateway.lock /tmp/gateway.log
  export CHESS_COACH_BACKEND_TOKEN=devtoken123
  export CHESS_COACH_MAX_WORKERS=1
  nohup scripts/start_gateway.sh > /tmp/gateway.log 2>&1 & disown
'
sleep 35   # cold start: pip install --force-reinstall + UCI handshake
curl -sS --max-time 8 http://127.0.0.1:18080/v1/system/health \
  -H 'Authorization: Bearer devtoken123'
```

### Bare-metal (no Docker, no agentZero)

Only recommended if you're hacking on the embedder or want
to run the unit tests. The full backend needs Stockfish +
python-multipart + sentence-transformers + qdrant-client, all
of which are pip-installable but not trivially cross-platform.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest tests/unit/ -v
```

The unit tests use the `:memory:` Qdrant default and don't
need a sidecar.

---

## Common pitfalls

### 1. `git push` "succeeded" but main hasn't moved

`main -> main` in the git client output only means the local
daemon accepted the write. Always confirm with the GitHub API:

```bash
curl -sS 'https://api.github.com/repos/sebko23/chess-coach/branches/main' \
  | jq -r '.commit.sha'
```

If the SHA hasn't moved, the push hit push-protection or a
network error. The CI run will not exist for a commit that
isn't on `main`.

### 2. Smoke CI red with no obvious cause

Per BBF-38 (2026-07-14), the smoke workflow polls the backend's
health endpoint directly with `curl` rather than via Docker's
`inspect` healthcheck. The Dockerfile's HEALTHCHECK used to
hard-code `Bearer ***` (a TODO marker), which always 401'd; this
was fixed in BBF-52.

If the smoke CI is red, read the step 9 (`docker logs`) output
first. The relevant signatures:

- `docker logs chess-coach-backend-ci` shows
  `ModuleNotFoundError: No module named 'X'` -- missing runtime
  dep (BBF-40/41/42/44 family).
- `kb: index_positions failed (...)` -- Qdrant unreachable
  (BBF-52).
- `gateway.startup: applied N migration(s)` then hangs -- the
  SQLite migrations are blocked; check the data dir perms.

### 3. Container cgroup wedge after heavy pytest

The agentZero container's cgroup is memory-starved after long
pytest runs. Symptoms: `OCI runtime exec failed: procReady not
received`. Recovery:

```bash
docker restart agentZero
sleep 90
curl -sS --max-time 8 http://127.0.0.1:18080/v1/system/health \
  -H 'Authorization: Bearer devtoken123'
```

The host-port 18080 path bypasses the cgroup, so a successful
curl here proves the gateway is up even if the container
behaves weirdly.

### 4. `write_file` "files modified" success is unreliable on Windows

If a `write_file` call returns success but `ls -la` shows the
file is missing or empty, the tool silently dropped the write.
Common triggers: same-path `write_file` after a `patch` in the
same turn, unicode escapes the parser mis-reads, sibling
sub-agent races. Always follow `write_file` with an
`os.path.getsize(path) > 0` check.

### 5. `python` not found in /bin/sh on git-bash

The bash on Windows (`/bin/sh`) does NOT have `python` on PATH.
Use the Python Launcher: `py -3` (resolves to
`C:\Users\i3\AppData\Local\Programs\Python\Launcher\`). Don't
use bare `python -c "..."` in bash examples.

### 6. Unicode in commits gets rejected

The pre-commit UTF-8 lint (`lint-utf8.mjs`, BBF-17) blocks any
non-ASCII character in `apps/desktop/src/`, `scripts/`, and a
few top-level config files. Use `->` not `->`, `--` not `--`,
`'single quotes'` not `'smart quotes'`. It does NOT scan
`docs/`, `libs/`, or `tests/`.

### 7. Adding a new `chess_coach.*` package requires both pyproject entries

The project uses an explicit multi-source layout, not
`packages.find`. For each new `chess_coach.X` package you need
both an entry in `[tool.setuptools].packages` AND an entry in
`[tool.setuptools].package-dir`. Missing either: `pip install`
succeeds, `import` fails. Verified recipe in the BBF-sprint
skill.

### 8. PEP 562 lazy-imports don't actually defer on `from X import Y`

A `from X import Y` line in `app.py` calls `X.__getattr__` at
import time, which defeats the lazy-import. The defensive
pattern is fine for missing-dep deferral, but the real fix is
to add the dep to `pyproject.toml`. See the BBF-39 / BBF-43
history.

---

## Where to look next

- **Roadmap**: `docs/10_roadmap/phase-plan-v2.md` -- what
  ships in each phase, current progress, and the L-2 gold
  section.
- **Architecture decisions**: `docs/14_adrs/` -- ADR-0001
  (async/sync boundary), ADR-0004 (monolith-first), ADR-0006
  (engine pool audit, BBF-34).
- **Codebase audit**: `docs/14_adrs/ADR-0006-engine-pool-failure-modes.md`
  -- 5 findings from BBF-34, 3 closed, 1 benign, 1 deferred.
- **Lazy eval-graph results**: `docs/17_lazy_eval_graph/RESULTS.md`
  -- BBF-25's strategic-pivot success story (43.8s for a 6000-game
  PGN import).
- **L-2 gold corpus**: `docs/20_datasets/L2-gold-v1.md` --
  the project's first versioned labeled corpus (BBF-51), the
  spec for what "gold" means, and the procedure for extension.
- **Qdrant deployment**: `docs/20_datasets/qdrant-deployment.md`
  -- the BBF-52 deployment recipe, including the sidecar
  docker-compose shape and the three CI jobs that cover it.
- **CHANGELOG**: `docs/CHANGELOG.md` -- sprint history with
  honest framing for broken-and-reverted BBFs (BBF-39,
  BBF-46).
- **Smoke CI workflow**: `.github/workflows/smoke.yml` -- the
  three-job workflow (gateway-boot, qdrant-smoke, smoke)
  since BBF-52.