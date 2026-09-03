# `apps/cli/` — CHESS COACH Backend entrypoint

**License**: Apache-2.0.

**Status**: Phase 1 has landed: `__main__.py` dispatches two commands (`gateway`, `migrate`). `backend.json` writer is not yet implemented; Phase 8 PyInstaller packaging is still future-tense.

The binary distributed at Phase 8 packaging (`chess-coach-backend.exe` and equivalents) is produced by PyInstaller from this entrypoint plus all of `services/` and `libs/`.
