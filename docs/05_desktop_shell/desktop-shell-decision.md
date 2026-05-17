# Desktop Shell Decision — Tauri 2.x

**Status**: Decided. **Date**: 2026-05-18. **Decision owner**: Lead architect (Agent Zero).

## TL;DR

We will use **Tauri 2.x** as the desktop shell.
This decision is effectively pre-determined by the en-croissant base we are required to preserve (en-croissant is already a Tauri 2.10 + React 19 + Mantine 8 + Vite application — see `docs/research/en-croissant-analysis.md`). Switching shells would mean abandoning en-croissant, which the master prompt forbids.

However the decision was independently re-validated against Electron and alternatives below.

## Candidates evaluated

| Criterion | Tauri 2.x | Electron 33+ | Wails v2 | Flutter Desktop | Native (Qt/C++) |
|---|---|---|---|---|---|
| Binary size (installer) | 5–15 MB | 90–180 MB | 10–25 MB | 30–60 MB | 20–80 MB |
| RAM (idle, 1 window) | 80–150 MB | 250–500 MB | 100–200 MB | 150–300 MB | 50–150 MB |
| Runs on Windows 10/11 | ✅ first-class | ✅ first-class | ✅ | ✅ | ✅ |
| React + en-croissant code reuse | ✅ direct | ✅ direct | ⚠️ (Go backend, would require rewriting) | ❌ (Dart) | ❌ |
| Docker IPC (HTTP/WS to localhost) | ✅ trivial | ✅ trivial | ✅ | ✅ | ✅ |
| Sidecar process management | ✅ first-class (`tauri.conf.json` externalBin) | ⚠️ manual `child_process` | ✅ | ⚠️ manual | ⚠️ manual |
| Security model | ✅ allowlist + CSP, no Node in renderer | ❌ Node exposed in renderer (preload required) | ✅ | ✅ | ✅ |
| Auto-update | ✅ built-in signed updater | ✅ via electron-updater | ⚠️ | ⚠️ | ❌ |
| Long-term maintainability | ✅ active, v2 GA Oct 2024 | ✅ very active | ⚠️ smaller community | ⚠️ desktop is second-class for Flutter | ⚠️ high effort |
| Packaging complexity (Win) | ✅ MSI + NSIS built-in | ✅ NSIS | ✅ NSIS | ⚠️ | ⚠️ |
| **en-croissant compatibility** | ✅ **native — it IS Tauri** | ❌ would require full rewrite | ❌ rewrite | ❌ rewrite | ❌ rewrite |

## Justification (technical)

1. **en-croissant preservation requirement is hard-blocking.** The master prompt mandates we preserve en-croissant's visual style, components, interaction patterns, and utilities. en-croissant is Tauri-native (Rust commands, specta TS bindings, chessground board, Mantine UI). Re-implementing all of that on Electron would take months and lose the upstream benefit.
2. **License posture.** en-croissant is GPL-3.0-only. Tauri keeps our backend AI services in **separate processes** (sidecars + Docker), which is critical to avoid GPL contamination of our proprietary backend. Electron would not have changed this analysis but the sidecar pattern is more idiomatic in Tauri.
3. **Resource budget.** A coaching app is expected to run alongside engines (Stockfish using 4–8 GB RAM at depth 30+) and possibly local LLMs. Tauri's 80–150 MB shell overhead vs Electron's 250–500 MB matters here.
4. **Security.** Tauri 2's allowlist + capability system + no-Node-in-renderer is materially safer than Electron when we will be loading user-supplied PGNs, PDFs, and possibly cloud responses.
5. **Sidecar pattern.** Tauri's `externalBin` mechanism is purpose-built for shipping a Python backend (PyInstaller binary) or proxying to a Docker service. This matches our hybrid architecture exactly.

## Trade-offs accepted

- **Rust learning curve** for any Tauri backend command we add. Mitigation: keep Rust-side commands thin — they should only proxy to the Python FastAPI services. All chess logic stays in Python.
- **Smaller ecosystem than Electron.** Mitigation: we don't need exotic Electron-only libs; chess-specific work is in our backend.
- **GPL-3.0 obligation on the GUI fork.** We accept this. The GUI fork (CHESS COACH GUI) will be public/GPL. The backend AI services run in separate processes over HTTP/WS, communicate only by documented protocol, and remain under a license of our choosing.

## Open questions deferred to implementation

- Whether to ship the Python backend as a PyInstaller sidecar (offline-friendly, large binary) or require Docker Desktop on the host (smaller installer, dependency on Docker). **Tentative answer: Docker-first for dev, PyInstaller sidecar for end-user distribution. Validated in Phase 2.**
- Tauri updater signing key management (covered in `docs/08_security/`).
