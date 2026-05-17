# En-Croissant Repository Analysis

**Target**: https://github.com/franciscoBSalgueiro/en-croissant
**License**: GPL-3.0-only
**Author**: Francisco Salgueiro (fgcdbs@gmail.com)
**Current version**: 0.15.0
**Last commit observed**: 2026-04-20 ("improve nodes decimals", #810)
**Tagline**: "The Ultimate Chess Toolkit"
**Website**: https://www.encroissant.org
**Built for**: Windows, macOS, Linux (cross-platform desktop)

---

## 1. Tech Stack

### Desktop Shell
- **Tauri 2.10.2** (Rust + WebView) — chosen over Electron
- Custom protocol enabled (`tauri/custom-protocol`)
- Windows: hides console subsystem in release

### Frontend
- **React 19.2** + TypeScript (TS native preview)
- **Vite 8** build tool with Babel + React Compiler plugin
- **TanStack Router** (`@tanstack/react-router` 1.161) — file-based routing
- **Mantine 8.3** UI framework (core, charts, dates, form, hooks, notifications, tiptap)
- **Mantine extensions**: `mantine-datatable`, `mantine-contextmenu`, `mantine-flagpack`
- **State management**:
  - `jotai` (atomic) — primary
  - `zustand` 5.0 (stores)
  - `immer` 11 (immutable updates)
  - `proxy-memoize` (selectors)
- **Routing UI**: `react-mosaic-component` (tiled panels), `react-dnd` (drag-and-drop)
- **Charts**: `recharts` 3.7, `@mantine/charts`
- **Validation**: `zod` 3
- **i18n**: `i18next` 25 + `react-i18next` 16 + `i18next-cli`
- **Spaced repetition**: `ts-fsrs` 3.5 (Free Spaced Repetition Scheduler)
- **Pattern matching**: `ts-pattern`
- **Fuzzy search**: `fuse.js`
- **Editor**: `@tiptap/*` 3.20 (rich text annotations)
- **HTTP**: `swr` for data fetching
- **Analytics**: `posthog-js`

### Chess-Specific Frontend
- **`@lichess-org/chessground`** 10.1.1 — board rendering (Lichess's official board)
- **`chessops`** 0.14.0 — chess logic (FEN, moves, validation)

### Backend (Rust, src-tauri)
- **`shakmaty`** 0.27.1 — chess move generation/validation
- **`pgn-reader`** 0.26.0 — PGN parsing
- **`vampirc-uci`** (custom fork: `franciscoBSalgueiro/vampirc-uci`) — UCI protocol with `specta` + `serde` features
- **`polyglot-book-rs`** 0.1.0 — Polyglot opening book reader
- **`rusqlite`** 0.28.0 (bundled SQLite)
- **`diesel`** 2.0.2 (ORM, SQLite, r2d2 pool)
- **`tokio`** 1.33 (async)
- **`reqwest`** 0.12.5 (HTTP)
- **`rayon`** 1.6 (parallel iteration)
- **`memmap2`** 0.9 + **`rkyv`** 0.8 — memory-mapped zero-copy search indexes
- **`zstd`** + **`bzip2`** + **`zip`** + **`tar`** (compression/archives)
- **`specta`** + **`tauri-specta`** — automatic TypeScript binding generation from Rust types
- **`dashmap`** 6 — concurrent maps (engine processes, caches)
- **`oauth2`** 4.4 + **`axum`** 0.6 — OAuth flow (Lichess login)
- **`sysinfo`** 0.29, **`governor`** (rate limiting), **`strsim`** (fuzzy player name match)

### Tauri Plugins Used
`fs`, `dialog`, `http`, `cli`, `log`, `opener`, `os`, `process`, `updater`, `window-state`

---

## 2. Repository Structure

~~~
en-croissant/
├── src/                       # React frontend (TypeScript)
│   ├── App.tsx, index.tsx     # Entry
│   ├── routes/                # TanStack file-based routes
│   │   ├── __root.tsx, index.tsx, accounts.tsx,
│   │   │   engines.tsx, files.tsx, settings.tsx,
│   │   │   databases/         # nested
│   ├── components/
│   │   ├── boards/            # BoardAnalysis, BoardGame, EvalBar, MoveInput,
│   │   │                       PromotionModal, EnginesSelect, Clock, PiecesGrid…
│   │   ├── panels/
│   │   │   ├── analysis/      # engine analysis panel
│   │   │   ├── annotation/    # PGN annotations editor
│   │   │   ├── database/      # opening explorer / DB panel
│   │   │   ├── info/          # game info
│   │   │   └── practice/      # repertoire training
│   │   ├── databases/         # AddDatabase, DatabaseView, PlayerCard, FideInfo,
│   │   │                       GameTable, TournamentTable, PlayerSearchInput…
│   │   ├── engines/           # AddEngine, EngineForm, EnginesPage
│   │   ├── files/             # PGN file management
│   │   ├── home/              # AccountCard, Lichess account integration
│   │   ├── puzzles/           # puzzle solver UI
│   │   ├── tabs/              # BoardTab, NewTabHome, ImportModal, CreateRepertoireModal
│   │   ├── settings/, common/, icons/
│   ├── bindings/              # generated.ts (auto-generated from Rust via specta)
│   ├── chessground/           # chessground integration helpers
│   ├── hooks/, state/, styles/, translation/
│   └── utils/
│       ├── chess.ts, chessops.ts        # logic helpers
│       ├── annotation.ts, treeReducer.ts
│       ├── db.ts, engines.ts, repertoire.ts, puzzles.ts
│       ├── lichess/, chess.com/, chessdb/  # cloud integrations
│       └── tests/
├── src-tauri/                 # Rust backend
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs            # Tauri entry, AppState, command registry
│   │   ├── chess.rs           # engine analysis commands (analyze_game, get_best_moves…)
│   │   ├── engine/            # engine subsystem
│   │   │   ├── mod.rs, process.rs (BaseEngine spawn/stdin/stdout/stderr),
│   │   │   │   uci.rs (FEN+UCI move normalization), types.rs
│   │   ├── db/                # database subsystem
│   │   │   ├── mod.rs (19 tauri commands), create.sql, indexes.sql,
│   │   │   │   schema.rs (diesel), models.rs, ops.rs, search.rs,
│   │   │   │   search_index.rs (memory-mapped), encoding.rs
│   │   ├── pgn.rs             # PGN read/write/count
│   │   ├── lexer.rs           # PGN lexer
│   │   ├── game.rs            # GameManager (live local games vs engine)
│   │   ├── puzzle.rs          # puzzle DB
│   │   ├── opening.rs         # opening detection (by FEN, name search)
│   │   ├── oauth.rs           # Lichess OAuth flow
│   │   ├── sound.rs, fs.rs, progress.rs, error.rs
│   │   └── data/              # bundled data
│   ├── capabilities/          # Tauri 2 capabilities (permissions)
│   └── icons/                 # app icons
├── public/                    # pieces (multiple sets), board themes
├── sound/                     # 8 sound themes (standard, lisp, nes, robot, woodland, piano, futuristic, sfx)
├── package.json, pnpm-lock.yaml, pnpm-workspace.yaml
├── vite.config.ts, tsconfig.json, i18next.config.ts
├── .oxlintrc.json, .oxfmtrc.json   # oxc-based linter/formatter (Rust-powered)
├── index.html, README.md, CONTRIBUTING.md, LICENSE (GPL-3.0)
~~~

---

## 3. Key Components / UI Features

### Analysis Board
- `BoardAnalysis.tsx` — main analysis view
- `EvalBar.tsx`, `EvalListener.tsx` — evaluation visualization
- `MoveInput.tsx` — keyboard/text move input
- `BoardControls.tsx` — navigation (prev/next/start/end)
- `AnnotationHint.tsx` — annotation hints
- `PromotionModal.tsx`
- Multi-panel mosaic layout (drag/resize) via `react-mosaic-component`

### Engine Integration
- `EnginesPage.tsx`, `AddEngine.tsx`, `EditEngine.tsx`, `EngineForm.tsx`
- `EnginesSelect.tsx` (in boards) — pick engine to run
- Multi-engine simultaneous analysis (engine_processes keyed by `(engine_id, tab_id)`)
- Engine config introspection (UCI options)

### Database / PGN
- `DatabasesPage.tsx`, `DatabaseView.tsx`, `AddDatabase.tsx`
- `GameTable.tsx`, `GamePreview.tsx`, `TournamentTable.tsx`
- `PlayerTable.tsx`, `PlayerCard.tsx`, `PlayerSearchInput.tsx`, `FideInfo.tsx`
- Opening explorer (via `panels/database/`)
- Position search (absolute & partial) in DB — uses memory-mapped index
- Player merging (`merge_players`), tournament browsing

### Repertoire & Training
- `CreateRepertoireModal.tsx`
- `panels/practice/` — spaced-repetition repertoire training (FSRS algorithm)
- `puzzles/` — puzzle solving page

### Cloud / Online
- Lichess OAuth login (`oauth.rs` + `axum` callback server)
- Lichess account / games import (`home/AccountCard.tsx`, `utils/lichess/`)
- Chess.com import (`utils/chess.com/`)
- `chessdb` integration (`utils/chessdb/`) — community opening DB

### Annotations
- TipTap-based rich text annotations on moves
- Move-tree reducer (`treeReducer.ts`) with NAG support

### Other
- Multi-language (i18next, 11+ locales)
- Window state persistence (Tauri plugin)
- Auto-updater (Tauri plugin)
- 8 piece sets + multiple board themes + 8 sound themes

---

## 4. Chess Engine Integration

### Mechanism
Engines are external **UCI binaries** (Stockfish, Lc0, etc.) spawned as child processes by the Rust backend.

### Engine Process Lifecycle (`src-tauri/src/engine/process.rs`)
~~~rust
// BaseEngine::spawn(path: PathBuf)
// - spawn Command with stdin/stdout/stderr piped
// - Windows: CREATE_NO_WINDOW (0x08000000) — no console flash
// - cwd = engine binary's parent dir
// - tokio::process::Command for async I/O
// - stderr logged via tokio::spawn background task
// - lines reader via BufReader::new(stdout).lines()
// - logs: Vec<EngineLog::Gui|Engine>
~~~

### UCI Layer (`src-tauri/src/engine/uci.rs`)
- `parse_fen_to_position(fen)` → `shakmaty::Chess`
- `apply_uci_moves(pos, &[String])` → mutates position
- `normalize_uci_moves_for_fen` — normalizes castling/promotion notation per FEN
- Uses **vampirc-uci** fork for typed UCI message parsing

### Tauri Commands Exposed (in `chess.rs`)
- `get_engine_config(path)` — discover UCI options of a binary
- `get_best_moves(...)` — start analysis, stream `BestMovesPayload` events
- `analyze_game(...)` — full game analysis
- `cancel_analysis(id)`, `stop_engine(...)`, `kill_engine(...)`, `kill_engines(tab)`
- `get_engine_logs(...)`

### Concurrency Model (in `AppState`)
~~~
engine_processes: DashMap<(engine_id, tab_id), Arc<Mutex<EngineProcess>>>
analysis_cancel_flags: DashMap<analysis_id, Arc<AtomicBool>>
new_request: Arc<Semaphore::new(2)>   // limit concurrent search ops
~~~

### Engine Discovery
- User adds engine via `AddEngine.tsx` (manual file picker) or downloads via UI (engine catalog hosted on encroissant.org)
- No bundled engine — clean separation

---

## 5. Database / PGN Handling

### Storage
- **SQLite** via `diesel` ORM + `rusqlite` (bundled)
- Schema defined in `src-tauri/src/db/create.sql` + `db/schema.rs`
- Indexes in `db/indexes.sql` (created/dropped on demand for batch import speed)
- Connection pool per DB file (`r2d2`)

### PGN Pipeline
- `pgn.rs`: `count_pgn_games`, `read_games`, `write_game`, `delete_game`
- `lexer.rs`: `lex_pgn` (own lexer, exposed as Tauri command)
- `pgn-reader` crate for streaming parse
- `convert_pgn` command — import PGN into SQLite DB
- Per-PGN-file byte offsets cached: `pgn_offsets: DashMap<String, Vec<u64>>` for O(1) game seek

### Search
- `db/search.rs` — game query by player/event/result/ECO/date
- `db/search_index.rs` + `MmapSearchIndex` — **memory-mapped + rkyv zero-copy** position index for fast absolute/partial position search across millions of games
- Line cache: `DashMap<(GameQuery, PathBuf), (Vec<PositionStats>, Vec<NormalizedGame>)>` — avoid recompute
- Collision lock per query to avoid duplicate work

### Database Commands (`db/mod.rs`, 19 commands)
`get_db_info`, `edit_db_info`, `delete_database`, `clear_games`, `delete_db_game`, `delete_empty_games`, `delete_duplicated_games`, `merge_players`, `get_players`, `get_player`, `get_players_game_info`, `get_tournaments`, `get_games`, `write_db_game`, `create_indexes`, `delete_indexes`, `search_position`, `export_to_pgn`, `preload_reference_db`, `convert_pgn`

### Reference DB
A dedicated reference DB (community master games) can be preloaded for opening explorer functionality.

---

## 6. Build / Packaging (Windows)

### Toolchain
- **pnpm** for JS deps (`pnpm install`)
- **Tauri CLI** (`@tauri-apps/cli` 2.10) drives Rust + Vite build
- Rust toolchain (stable) + Windows SDK / MSVC

### Build Command
~~~bash
pnpm install
pnpm build      # = tauri build --no-bundle (CI handles bundling)
pnpm dev        # = tauri dev (Vite dev server + cargo run)
~~~

### Output
`src-tauri/target/release/en-croissant.exe` (and per-platform bundles via CI)

### CI
`.github/workflows/` — GitHub Actions for multi-platform release builds. Auto-updater plugin enabled (signed releases from encroissant.org).

### Linting / Formatting
- **oxlint** + **oxfmt** (Rust-powered, fast) instead of ESLint/Prettier
- TypeScript checking via `@typescript/native-preview` (tsgo)

### Testing
- `vitest` 4 + `jsdom` for unit tests (`src/utils/tests/`)

---

## 7. License & Project Activity

| Metric | Value |
|---|---|
| License | GPL-3.0-only (**copyleft — affects fork/redistribution**) |
| Stars (snapshot) | not captured (GitHub JS-rendered) |
| Forks | **254** |
| Open issues | **121** |
| Open PRs | **16** |
| Discussions | enabled |
| Last commit | 2026-04-20 (`improve nodes decimals` #810) — **actively maintained** |
| Primary maintainer | Francisco Salgueiro (`@franciscoBSalgueiro`) |
| Active collaborator | `Disservin` (Sebastian, also Stockfish dev / chess-cli author) |
| Project age | ~2+ years (v0.15.0) |
| Donations | accepted via encroissant.org/support |
| Discord | active community server |

*Note: shallow `--depth 1` clone limited git log inspection; contributor count via GitHub UI was not captured but page header shows Disservin as visible contributor and #810 PR number implies hundreds of merged PRs.*

---

## 8. Notable Dependencies

### Frontend chess libs
- `@lichess-org/chessground` ^10.1.1 — **Lichess's official board renderer**, MIT/GPL-friendly
- `chessops` ^0.14.0 — TS chess logic from Lichess team
- **Not used**: `chess.js` (replaced by `chessops`, which is more rigorous)

### Backend chess libs
- `shakmaty` 0.27 — high-perf Rust chess (Lichess team), used by Lichess server
- `pgn-reader` 0.26 — streaming PGN parser (same author as shakmaty)
- `vampirc-uci` (custom fork) — typed UCI message parsing
- `polyglot-book-rs` 0.1 — Polyglot binary opening book reader

### Storage / indexing
- `rusqlite` 0.28 bundled SQLite, `diesel` 2 ORM, `memmap2`, `rkyv` (zero-copy serialization)

### Tauri ecosystem
- 11+ official Tauri plugins (fs, dialog, http, log, etc.)
- `specta` + `tauri-specta` — **Rust ↔ TS type bridge** (generates `src/bindings/generated.ts` automatically)

### React ecosystem
- React 19, Mantine 8, TanStack Router 1.161, Jotai, Zustand, Immer
- `ts-fsrs` — spaced repetition (same algo Anki+ uses)

### Analytics / payments
- `posthog-js` (product analytics)
- No payment integration in OSS repo (PRO/paid tier likely on encroissant.org separately)

---

## 9. Integration Points / Extension Surfaces for CHESS COACH Backend

En-Croissant is **NOT designed as a plugin host**. There is no public extension API. To integrate a CHESS COACH Python/FastAPI backend, the following hooks are viable:

### A. Replace / Augment the Engine Layer
- `engine_processes` in `AppState` could be extended so a "coach engine" is a spawned process speaking UCI-extended protocol (or a thin UCI shim wrapping a remote HTTP/WebSocket endpoint).
- **Best fit**: register CHESS COACH backend as a virtual UCI engine that proxies to FastAPI. This requires zero changes to the React frontend — it just appears as "another engine".
- Risk: UCI is move-oriented; richer outputs (lessons, psychological insights, prose) require either a sidecar channel or a parallel new Tauri command.

### B. Add New Tauri Commands (Fork)
Add commands in `src-tauri/src/coach.rs`:
- `coach_analyze_position(fen, history) -> CoachReport`
- `coach_train_session(user_id, weakness_area) -> Lesson`
- `coach_psychological_profile(games_pgn) -> Profile`

These call out to CHESS COACH backend via `reqwest` (or WebSocket).
Frontend gets these via specta auto-generated bindings — zero TS-side boilerplate.

### C. Sidecar / Companion Process
Tauri 2 supports **sidecar binaries** (declared in `tauri.conf.json`). Bundle the CHESS COACH backend as a sidecar (PyInstaller-packaged FastAPI server) launched at app start. Frontend talks to it on `localhost:PORT` via existing `@tauri-apps/plugin-http`.

### D. Custom Panel via `react-mosaic-component`
The analysis page is a mosaic of panels (`panels/analysis`, `panels/database`, `panels/practice`). Adding a `panels/coach/` directory is a clean, localized change.

### E. Database Integration
- The SQLite schema is owned by en-croissant. Adding new tables requires migration logic.
- Cleaner: keep CHESS COACH data in a **separate SQLite (or DuckDB / vector store) owned by the backend**, joined logically by `pgn_id` / `position_fen`.

### F. Events / Telemetry
Tauri's event system (`window.emit`/`listen`) is used for engine streaming. Coach can use same pattern for streaming lesson narration, analysis progress, etc.

### G. OAuth Reuse
Lichess OAuth is already implemented in `oauth.rs`. The coach can reuse the token for game history download.

---

## 10. Compatibility Risks if We Fork / Extend

### Licensing Risk: GPL-3.0 (HIGH)
- En-Croissant is **GPL-3.0-only** (strong copyleft).
- **Any fork or derivative we distribute must also be GPL-3.0.**
- The CHESS COACH AI backend (Python/FastAPI) is a **separate program** if it communicates via process/HTTP boundaries — that classically avoids GPL contamination of the backend itself, but the **GUI fork remains GPL-3**.
- Linking GPL-3 code statically into a non-GPL binary is forbidden; our shell/fork must stay GPL-3.
- Distributing modified binaries requires source release of the GUI changes.
- **Decision implication**: this is fine for an open-source CHESS COACH GUI, but blocks any future closed-source commercial GUI without re-implementation.

### Maintenance / Upstream Drift Risk (MEDIUM-HIGH)
- The project ships fast (v0.15, 800+ PRs, active in 2026). Forking now means **continuous rebase pain** to absorb upstream fixes.
- Mitigation: keep changes minimal in shell, push heavy logic into separate Tauri commands and sidecar.

### Schema Coupling Risk (MEDIUM)
- The SQLite schema (`db/create.sql`, `db/schema.rs` diesel macros) is opinionated and frequently extended. If we touch it, migrations diverge.
- Mitigation: do **not** modify their schema; use a parallel CHESS COACH database.

### Bindings Generation Risk (LOW-MEDIUM)
- `specta` regenerates `src/bindings/generated.ts` from Rust types at build time. Custom additions to Rust types need to be added to the specta export list in `main.rs`.
- Documented pattern, low risk if followed.

### React 19 + Mantine 8 + TS native preview (LOW-MEDIUM)
- Bleeding-edge frontend stack (React 19, TS native, oxc lint, Vite 8). May lag on Linux/macOS compat fixes; Windows is primary target which matches our needs.

### Tauri 2 Capabilities Model (LOW)
- Tauri 2 uses an explicit per-command capability/permission system in `src-tauri/capabilities/`. Adding commands requires adding capability declarations. Well-documented.

### Engine Path Resolution (LOW)
- Engines are spawned from user-installed paths; CHESS COACH backend launched as sidecar uses Tauri's resolved resource paths — standard.

### Branding / UX Conflict (LOW)
- Their UI is built around the en-croissant brand (logo, donation link, encroissant.org updater). Forking implies stripping/replacing — minor but visible work.

### PostHog Telemetry (LOW)
- `posthog-js` is bundled. Must be removed or replaced before shipping CHESS COACH builds for privacy reasons.

### Updater Endpoint (LOW)
- Tauri auto-updater is wired to en-croissant signing key. Must be repointed to CHESS COACH's own update server (or disabled) before release.

---

## Summary Verdict

En-Croissant is an **excellent technical base** for CHESS COACH's GUI requirement:

- ✅ Tauri 2 (matches CHESS COACH preference for lightweight desktop shell over Electron)
- ✅ Production-quality UCI engine orchestration already in Rust
- ✅ Mature PGN + SQLite + position-search infrastructure
- ✅ Lichess + Chess.com integrations already implemented (incl. OAuth)
- ✅ Repertoire trainer with FSRS spaced repetition already present
- ✅ Annotation, opening explorer, multi-engine, puzzle UI all in place
- ✅ Cross-platform, actively maintained, type-safe Rust↔TS bridge (specta)
- ⚠️ **GPL-3.0 forces any GUI fork to remain open-source**
- ⚠️ Upstream velocity → fork-rebase discipline required
- ⚠️ No formal plugin API → integrate via sidecar + new Tauri commands + new panel directory

**Recommendation**: Fork en-croissant, add a `panels/coach/` panel, expose CHESS COACH backend via sidecar process (FastAPI) launched by Tauri, communicate via HTTP/WebSocket on `localhost`, keep CHESS COACH data in a separate database, and accept GPL-3 for the GUI layer. Backend AI services remain a separately-licensable program at the process boundary.
