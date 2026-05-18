# `infra/` — Infrastructure

**License**: Apache-2.0.

| Subdirectory | Purpose |
|---|---|
| `docker/` | Compose files and Dockerfiles for the **developer environment**. End users do not need Docker (see `docs/05_desktop_shell/desktop-shell-decision.md`). |
| `installer/windows/` | WiX or equivalent installer recipe that bundles `chess-coach-gui.exe` + `chess-coach-backend.exe` + Stockfish + assets into a single MSI. Authored at Phase 8. |
| `memurai/` | Memurai (Windows Redis-compatible) packaging — kept as a planning artifact only; Phase 1 does NOT use Redis. |
