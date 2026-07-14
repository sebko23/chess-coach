# Building CHESS COACH from Source

**Audience**: anyone who wants to build CHESS COACH from this repository on their own machine, including users exercising their **GPL-3.0 §6 right** to install a modified version of the GUI on the same hardware that received our signed build.

**Guarantee**: a user-built GUI binary, produced by following these instructions on commodity hardware with free tools, will run **identically** to our signed build against any conforming Backend. The auto-updater performs no binary-identity check at launch.

This is binding architectural requirement **P2** (see `docs/08_security/security-strategy.md` post-legal addendum and `LICENSING.md` § "GPL-3.0 §6 (Installation Information) compliance").

## Prerequisites

### Common

- **git** ≥ 2.30
- ~10 GB free disk space (build artifacts, dependencies)

### For the desktop GUI (`apps/desktop/`)

- **Node.js** ≥ 20.10 (LTS)
- **pnpm** ≥ 9.0 (`npm install -g pnpm`)
- **Rust** ≥ 1.77 (`rustup` recommended)
- **Tauri 2.x system dependencies** (varies by platform — see [tauri.app/start/prerequisites](https://tauri.app/start/prerequisites/))
  - **Windows**: WebView2 (preinstalled on Windows 10 1803+) and the MSVC toolchain (Visual Studio Build Tools 2022 with the "Desktop development with C++" workload)
  - **Linux**: `webkit2gtk-4.1-dev`, `libssl-dev`, `librsvg2-dev` (Debian/Ubuntu names; adapt for your distro)
  - **macOS**: Xcode Command Line Tools

### For the backend (`services/`, `libs/`, `apps/cli/`)

- **Python** ≥ 3.11
- **uv** or **pip-tools** for dependency management (uv recommended: `pipx install uv`)
- **SQLite** ≥ 3.40 (usually preinstalled or available via OS package manager)
- **Stockfish 18** binary on PATH or at a known location. The gateway defaults to `/usr/local/bin/stockfish`; you can override with the `CHESS_COACH_STOCKFISH_PATH` env var if needed.

## Building the desktop GUI

```bash
cd apps/desktop
pnpm install
pnpm tauri build              # produces a native installer in src-tauri/target/release/bundle/
```

For a development run that hot-reloads:

```bash
pnpm tauri dev
```

### Anti-tivoization guarantees during build

- No code-signing certificate is required to build a working GUI. The build succeeds and the resulting binary runs without signing.
- The auto-updater public key embedded in the build is **only** used to verify update manifests we publish; the running binary is not verified against any key at launch.
- A user-built binary connects to any conforming Backend identically to our signed build.

If you wish to **sign** your build (so other users can install your updates with the same signature-verification trust as our updates), generate your own Tauri updater key pair (`pnpm tauri signer generate`) and configure it per [Tauri docs](https://v2.tauri.app/plugin/updater/). This is optional.

## Building the backend

### Environment variables (read these first)

The backend reads three env vars that the next dev should understand:

| Variable | Default | Purpose |
|---|---|---|
| `CHESS_COACH_DATA_DIR` | `~/.local/share/chess-coach` (Linux/macOS), `%LOCALAPPDATA%\chess-coach` (Windows) | Where the SQLite DB, runtime descriptor, and engine binaries live. The desktop reads `${CHESS_COACH_DATA_DIR}/runtime/backend.json` to find the gateway. Set this to a shared directory if backend and desktop run on different machines. |
| `CHESS_COACH_BACKEND_TOKEN` | random per-startup | Bearer token the gateway requires on every request. Read from `backend.json` after first startup. **For dev, set this to `devtoken123`** so you can curl without re-reading the descriptor. |
| `CHESS_COACH_MAX_WORKERS` | `1` | How many Stockfish subprocesses to spawn. Each process is single-coroutine, so `1` is correct for a single-user setup. Set to your CPU core count (4 on the dev machine) for max parallelism, but be aware: each Stockfish process spawns its own OS thread, and running many processes + the gateway itself can hit the per-process thread limit on the host. See "cgroup / thread limit caveat" below. |

### Dev mode (recommended for contributors)

```bash
# In a venv:
uv venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Set the dev token so you can curl without re-reading backend.json
export CHESS_COACH_BACKEND_TOKEN=devtoken123
export CHESS_COACH_MAX_WORKERS=2

# Run the gateway:
python -m chess_coach.gateway
# Listens on 0.0.0.0:18080. Writes the connection descriptor to
# ${CHESS_COACH_DATA_DIR}/runtime/backend.json on startup.
```

The first run creates `${CHESS_COACH_DATA_DIR}/sqlite/chess_coach.db` and
runs the migrations. Subsequent runs use the existing DB.

### Smoke test

```bash
# Health check (the bearer token must match CHESS_COACH_BACKEND_TOKEN):
curl -sS http://127.0.0.1:18080/v1/system/health \
  -H "Authorization: Bearer devtoken123"
# {"data":{"status":"ok",...}}

# Lazy eval-graph end-to-end (proves the full import + analyses path):
python tests/integration/smoke_test.py
```

### Lazy eval-graph behavior (post-BBF-22)

`POST /v1/import/pgn` is a **pure-insert** operation. It parses the PGN
and inserts `games` and `positions` rows. **No Stockfish analysis
happens at import time.** Analyses are computed lazily by
`GET /v1/games/{id}/eval-graph` on first call and cached in the
`analyses` table. This makes import time independent of corpus size:
a 6000-game PGN imports in ~45 s (BBF-25 stress test result).

If you want explicit pre-compute (for offline use, training data,
etc.), call `POST /v1/import/backfill-analyses` with `game_ids=[id1, id2, ...]`
or `game_ids=[]` for the full corpus. The backfill button on the games
list page in the GUI calls this route.

### cgroup / thread limit caveat

The `engine_orch.pool.EnginePool` opens one `aiosqlite` connection
per `analyze_one_position` call inside a single request. With many
concurrent analyses (a 19-ply PGN = 19 analyses per request), the
total per-process thread count can exceed the host's limit and you'll
see `can't start new thread` errors. The lazy eval-graph mitigates
this by using ONE shared connection across the gather. If you see
partial results (e.g. 7/19 positions with `score_cp`), the most
likely cause is the host killed the gateway for cgroup exhaustion,
not a code bug. Recovery: `docker restart <container>` (if running
in agentZero) or just restart the gateway. The smoke test
`tests/integration/smoke_test.py` does NOT exercise this — for that
see `docs/17_lazy_eval_graph/RESULTS.md`.

### Production sidecar (Phase 8 packaging path)

The Phase-8 plan bundles the backend as a single self-contained binary via PyInstaller. Until Phase 8, run the development mode above.

## Building everything together (developer workflow)

From the repo root, in two terminals:

```bash
# Terminal 1: backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export CHESS_COACH_BACKEND_TOKEN=devtoken123
export CHESS_COACH_MAX_WORKERS=2
python -m chess_coach.gateway

# Terminal 2: desktop
cd apps/desktop
pnpm install
pnpm tauri dev
```

The desktop auto-discovers the backend via `backend.json` if both
processes share `CHESS_COACH_DATA_DIR`. If you want to point the
desktop at a backend on a different host or port, set
`CHESS_COACH_DATA_DIR` in the desktop's shell to a directory the
backend has written `backend.json` to (mounted via NFS or similar).

## Bundled GPL-3.0 source-availability

When we (the CHESS COACH project) distribute a release, we honor GPL-3.0 §6 source-availability for every GPL component:

| Component | License | How to obtain corresponding source |
|---|---|---|
| CHESS COACH GUI | GPL-3.0-only (fork of en-croissant) | This repository at the tag matching the binary version. See `apps/desktop/README.md` for the upstream commit we forked from. |
| Stockfish | GPL-3.0-only | https://github.com/official-stockfish/Stockfish at the version we bundle (see `data/engines/stockfish/VERSION`). |
| Other bundled engines (if any) | per upstream | listed in `infra/installer/COMPONENTS.md` (to be authored at Phase 8 packaging) |

If you received a binary distribution of CHESS COACH and the corresponding source for any GPL component is not where this document points, please file an issue or email the maintainers; we treat source-availability gaps as bugs.

## Verifying a build

A conformance test suite (`specs/v1.0/tests/`) exists to verify that any backend or GUI build complies with the published protocol. Run it after building:

```bash
python -m chess_coach.testkit.run_conformance --target backend --base-url http://127.0.0.1:8765
```

(This command will be available from Phase 1 onward, once the conformance harness is implemented.)

A more practical smoke test that exercises the lazy eval-graph path is at `tests/integration/smoke_test.py` — it imports a 5-ply PGN, fetches the eval-graph, and verifies all positions have `score_cp` populated.
