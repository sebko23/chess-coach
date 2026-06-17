# SESSION HANDOVER — App-Data Dir Mismatch (chess-coach vs org.encroissant.app)

**Date:** 2026-06-17
**Status:** Resolved
**Severity:** High — engines.json lookup silently failed for multiple sessions before diagnosis
**Authoring session:** multi-session investigation culminating in Tauri appDataDir identification

---

## 1. Symptom

The `EnginesPage` "Local" tab in the Tauri webview rendered an empty state with the message **"No engines installed / Add an engine to get started"**, even though a populated `engines.json` was known to exist on disk and was confirmed valid:

- 1044 bytes, last modified Jun 15
- Valid JSON containing both `Stockfish 18` (stockfish, ELO 3500) and `Maia-1500 (lc0)` (lc0, ELO 1500)
- All entries passed the zod schema check
- File permissions were correct (world-readable, `root:root`)
- Path was inside an app-data directory convention used consistently elsewhere in the project

The webview was running cleanly (`React app started successfully` in the log), clicking the `Engines` sidebar icon navigated to the page without errors, but the list never populated.

---

## 2. Wrong Assumption

The investigation assumed (across multiple sessions) that `engines.json` lived under the **backend's** data-directory convention:

```
~/.local/share/chess-coach/engines/engines.json
```

This convention is correct and consistent for everything the **Python gateway backend** owns:

| Resource | Path | Owner |
|---|---|---|
| SQLite database | `~/.local/share/chess-coach/chess_coach.db` (→ `sqlite/chess_coach.db`) | Gateway |
| Runtime descriptor | `~/.local/share/chess-coach/runtime/backend.json` | Gateway |
| Code backups | `~/.local/share/chess-coach/backups/code/` | Gateway |
| Gateway binary | `/opt/venv/bin/chess-coach-gateway` | Gateway |
| Test fixture env var | `CHESS_COACH_DATA_DIR=/root/.local/share/chess-coach` | Tests (mocking gateway) |

Because the file's *name* (`engines.json`) and *nesting* (`engines/engines.json`) matched the backend's pattern, populate scripts confidently wrote it to `chess-coach/engines/`, and the convention was treated as authoritative for the whole project.

---

## 3. Actual Ownership

`engines.json` is **not** a backend file. It is **read and written exclusively by the Tauri frontend webview** through:

```ts
import { resolve, appDataDir } from "@tauri-apps/api/path";
// ...
return ensureDirectory(await resolve(await appDataDir(), "engines"));
```

`appDataDir()` resolves to a path determined by `tauri.conf.json`'s `identifier` field, **not** by the project name or any backend convention. For this project:

```jsonc
// apps/desktop/src-tauri/tauri.conf.json
{ "identifier": "org.encroissant.app" }
```

…so `appDataDir()` returns `~/.local/share/org.encroissant.app/`, and the real `engines.json` lives at:

```
~/.local/share/org.encroissant.app/engines/engines.json
```

The populate scripts never targeted this path. From the Tauri webview's perspective, the file at `chess-coach/engines/engines.json` did not exist; it was always inert.

---

## 4. The Fix

**One-line operational fix:** copy the populated `engines.json` to the correct frontend path. The backend-path copy can stay (or be removed) — it was never read by the running app.

```bash
mkdir -p /root/.local/share/org.encroissant.app/engines
cp /root/.local/share/chess-coach/engines/engines.json \
   /root/.local/share/org.encroissant.app/engines/engines.json
```

After this copy, on the next webview navigation to the `Engines` page, the list populated correctly with both Stockfish 18 and Maia-1500 (lc0), and selecting an engine populated the right-hand config panel (Name/Version/ELO, Search/Advanced settings, Edit JSON / Reset / Duplicate / Delete).

The diagnostic side-channel (`enginesFileStorage.getItem`'s `_engines-debug.json` write into the engines directory) was also stripped from `apps/desktop/src/state/atoms.ts` once the path was confirmed correct — the debug code is no longer needed.

---

## 5. What NOT to Fix

The following files **correctly** use the `chess-coach` directory name. They were never wrong. Do not "fix" them by replacing `chess-coach` with `org.encroissant.app` — that would break the backend, not help the frontend:

| File | Why it's correct |
|---|---|
| `scripts/start_gateway.sh` (lines 11, 18, 32) | Points at the gateway's SQLite DB, gateway binary, and runtime descriptor — all backend-owned |
| `scripts/backup_session.sh` (line 3) | `BACKUP_DIR` for backend code backups |
| `scripts/qdrant_spike.py` (line 9) | `DB_PATH` for backend's SQLite DB |
| `tests/integration/test_profile_analysis.py` (line 12) | `CHESS_COACH_DATA_DIR` env var for gateway test fixtures |
| `tests/integration/test_training_schedule.py` (line 12) | Same |
| `tests/integration/test_pdf_import.py` (line 15) | Same |
| `tests/integration/test_repertoire_blunders.py` (line 13) | Same |
| `tests/integration/test_gateway_error_handling.py` (line 12) | Same |
| `tests/integration/test_api_routes.py` (line 22) | Same |

**Rule of thumb:** if a file's `chess-coach` reference is in a `*.sh`, `*.py`, or backend-context test, it's almost certainly the gateway's data dir and should be left alone. If it's about the Tauri webview reading a frontend-owned file (engines.json, databases, etc.), it must use the Tauri `appDataDir()` path.

---

## 6. How to Avoid This Again

**Rule for any Tauri-frontend-owned file path:** derive or cross-check the path against `tauri.conf.json`'s `identifier`. Never assume a Tauri webview reads from a directory named after the project.

**Concrete check before writing any new Tauri-webview file:**

```bash
# What the Tauri webview actually sees as appDataDir:
grep -n "identifier" /a0/usr/projects/chess_coach/apps/desktop/src-tauri/tauri.conf.json

# What getEnginesDir/getDatabasesDir/getPuzzlesDir resolve to:
grep -A 2 "getEnginesDir\|getDatabasesDir\|getPuzzlesDir" \
  /a0/usr/projects/chess_coach/apps/desktop/src/utils/directories.ts
```

If a file is read by `atomWithStorage(...)` (or any other `appDataDir()`-derived path) in `apps/desktop/src/state/atoms.ts`, it belongs in the `org.encroissant.app` tree, **not** the `chess-coach` tree.

If a file is read by the Python gateway (`chess-coach-gateway`) or by the integration tests via `CHESS_COACH_DATA_DIR`, it belongs in the `chess-coach` tree.

**A naming-convention update worth considering (followup):** rename the backend data directory to something more obviously "backend-only" (e.g., `chess-coach-backend/`) so that a Tauri-frontend owner can never mistakenly route there. Tracked as future-work.

---

## 7. Investigation Notes (for the next person who hits "file exists but UI says no")

Multiple diagnostic angles were pursued before the path was identified. All of these were correct in isolation — they just verified the *wrong* file. Worth remembering that "everything checks out" applied to a problem is a strong signal that the thing being checked is not the thing that's actually wrong.

Angles exhausted before the breakthrough:

- **JSON / zod schema validity** — `engines.json` is well-formed and parses against the engine schema. Verified with `python3 -m json.tool` and `zod` (via a side-channel test).
- **File permissions** — readable by `root`, world-readable, correct ownership.
- **Tauri fs scope** — the `fs:scope-appdata-recursive` grant with `path: "**"` is correctly bound to `appDataDir()`, and a `/tmp` write from `enginesFileStorage.getItem` failed silently (correctly) because `/tmp` is outside that scope. The redirected in-scope write to `enginesDir/_engines-debug.json` also never appeared, which is what eventually pointed back at "the patched module is loading, but the file is being looked for in a different directory than we think."
- **Missing Rust command / `enginesListAtom` fabrication** — an earlier stretch of investigation constructed an elaborate internally-consistent wrong story (`enginesListAtom`, `read_engines_file`, `EngineListResponse`) that never existed in the current file. The `find / -name "_engines-debug.json"` + `ls ~/.local/share/` + `grep identifier tauri.conf.json` chain broke that illusion cleanly. Lesson: when source code is being "shown" via grep but the corresponding symbols don't exist, stop and re-verify the file rather than continuing to construct the diagnosis on top of unverified output.
- **Stale Vite/webview module cache** — the patched `enginesFileStorage.getItem` (with the in-scope debug write) was confirmed in `atoms.ts` via `grep -A 8 "async getItem(key)"` and the TS check (`pnpm tsc --noEmit` came back clean), yet the debug file never appeared. The webview is loading *some* version of the module but not necessarily the patched one. This is a real but smaller followup — it does not change the path-mismatch diagnosis or the fact that the engines are now correctly rendering.
- **Stale `.a0proj/knowledge/solutions/` memory** — checked, nothing in the `knowledge/` text tree encodes the wrong path as a "saved solution". The actual solution store is the binary `index.faiss` under `.a0proj/memory/`, and that one is accurate. No memory cleanup required.

---

## 8. References

- `apps/desktop/src/state/atoms.ts` — `enginesFileStorage` and `enginesAtom` (now clean, diagnostic stripped)
- `apps/desktop/src/utils/directories.ts` — `getEnginesDir`, `getDatabasesDir`, `getPuzzlesDir`, `getDocumentDir` (all `appDataDir()`-based)
- `apps/desktop/src-tauri/tauri.conf.json` — `identifier: "org.encroissant.app"` (the source of truth for the Tauri `appDataDir()`)
- `scripts/start_gateway.sh`, `scripts/backup_session.sh`, `scripts/qdrant_spike.py` — correctly named backend data-dir references (do not edit)
- `tests/integration/test_*.py` — correctly set `CHESS_COACH_DATA_DIR=/root/.local/share/chess-coach` for backend fixtures (do not edit)
- Sibling handover docs (modeled on these): `SESSION-HANDOVER-PRACTICE-DECK-SOURCE.md`, `SESSION-HANDOVER-MAIA-FIX.md`