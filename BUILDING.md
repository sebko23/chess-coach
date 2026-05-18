# Building CHESS COACH from Source

**Audience**: anyone who wants to build CHESS COACH from this repository on their own machine, including users exercising their **GPL-3.0 §6 right** to install a modified version of the GUI on the same hardware that received our signed build.

**Guarantee**: a user-built GUI binary, produced by following these instructions on commodity hardware with free tools, will run **identically** to our signed build against any conforming Backend. The auto-updater performs no binary-identity check at launch.

This is binding architectural requirement **P2** (see `docs/08_security/security-strategy.md` post-legal addendum and `LICENSING.md` § "GPL-3.0 §6 (Installation Information) compliance").

---

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

### For bundling engines

- The Phase-1 build needs only **Stockfish 18**. Either:
  - download a prebuilt binary from [stockfishchess.org/download/](https://stockfishchess.org/download/), **or**
  - build from source: `git clone https://github.com/official-stockfish/Stockfish` and follow upstream `Makefile` instructions.
  - Place the binary at `data/engines/stockfish/stockfish.exe` (Windows) or `data/engines/stockfish/stockfish` (Linux/macOS).

---

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

---

## Building the backend

### Development mode (recommended for contributors)

```bash
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"          # installs all backend libs + services in editable mode

# Run the gateway service (Phase 1: monolithic Python process):
python -m chess_coach.gateway       # listens on 127.0.0.1:8765 by default
```

The backend creates `${CHESS_COACH_DATA_DIR}/runtime/backend.json` on startup (default data dir per `specs/v1.0/chess-coach-protocol-v1.md` §1.4) with the connection descriptor the GUI reads to find it.

### Production sidecar (Phase 8 packaging path)

The Phase-8 plan bundles the backend as a single self-contained binary via PyInstaller. Until Phase 8, run the development mode above.

---

## Building everything together (developer workflow)

From the repo root:

```bash
# 1. Backend (in one terminal)
uv pip install -e ".[dev]"
python -m chess_coach.gateway

# 2. GUI (in another terminal)
cd apps/desktop
pnpm tauri dev
```

The GUI auto-discovers the backend via `backend.json`. If you want to point the GUI at a backend running on a different host or port, set `CHESS_COACH_DATA_DIR` in both terminals to a shared directory.

---

## Bundled GPL-3.0 source-availability

When we (the CHESS COACH project) distribute a release, we honor GPL-3.0 §6 source-availability for every GPL component:

| Component | License | How to obtain corresponding source |
|---|---|---|
| CHESS COACH GUI | GPL-3.0-only (fork of en-croissant) | This repository at the tag matching the binary version. See `apps/desktop/README.md` for the upstream commit we forked from. |
| Stockfish | GPL-3.0-only | https://github.com/official-stockfish/Stockfish at the version we bundle (see `data/engines/stockfish/VERSION`). |
| Other bundled engines (if any) | per upstream | listed in `infra/installer/COMPONENTS.md` (to be authored at Phase 8 packaging) |

If you received a binary distribution of CHESS COACH and the corresponding source for any GPL component is not where this document points, please file an issue or email the maintainers; we treat source-availability gaps as bugs.

---

## Verifying a build

A conformance test suite (`specs/v1.0/tests/`) exists to verify that any backend or GUI build complies with the published protocol. Run it after building:

```bash
python -m chess_coach.testkit.run_conformance --target backend --base-url http://127.0.0.1:8765
```

(This command will be available from Phase 1 onward, once the conformance harness is implemented.)
