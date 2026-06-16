# Session Outcome — 2026-06-16

## Scope
Repo hygiene verification, cleanup of uncommitted container-specific config, and an honest accounting
of what's still open vs. what was misdiagnosed as still-open earlier in the session.

## What was done

### 1. Verified repo state after multi-session hiatus
- `git log` confirmed 6 commits at top of master, with the 3 from the previous session
  (`781bcb8`, `17d3ee6`, `919d441`) properly in place
- `git status` showed 3 real uncommitted changes: `pnpm-lock.yaml`, `pnpm-workspace.yaml`,
  and an untracked `.npmrc`

### 2. Cleaned up container-specific workarounds
The earlier session had left behind these from the tauri-dev attempt:
- `pnpm-workspace.yaml` had: `packages: - .`, `allowBuilds` (placeholder text),
  `dangerouslyAllowAllBuilds: true`, `nodeLinker: hoisted`, plus the legitimate `onlyBuiltDependencies`
- `.npmrc` was created with `onlyBuiltDependencies[]=` entries (redundant with pnpm-workspace.yaml)
- `pnpm-lock.yaml` was regenerated with the hoisted config

**Kept (legitimate, low-risk):**
- `onlyBuiltDependencies` block in `pnpm-workspace.yaml` (the four standard build tools:
  `@swc/core`, `core-js`, `esbuild`, `protobufjs`)

**Reverted (container-specific, not for repo):**
- All other entries in `pnpm-workspace.yaml`
- `.npmrc` (deleted)
- `pnpm-lock.yaml` (reverted via `git checkout`)

### 3. Key finding: the `onlyBuiltDependencies` pin was never introduced by us
`git log -- apps/desktop/pnpm-workspace.yaml` shows only ONE commit ever touched that file:
`f4b87c0 feat(desktop)!: import en-croissant v0.15.0 working tree (commit 6f2d262) into apps/desktop/`

The clean version of the file is the **imported state from en-croissant**. The earlier session's
plan to "commit the onlyBuiltDependencies pin" was based on a false premise — it was already
committed via the en-croissant import. `git diff HEAD` confirmed zero delta, so no new commit
was needed. Creating one would have been an empty commit that misleadingly implied we added
the pin.

## What was learned (corrections to prior state docs)

### Qdrant is a working feature, not a spike
Earlier summary said "ChromaDB/Qdrant for vectors (spike stage)". That was wrong. The actual state:

- `services/chess_coach/memory_kb/` has 4 files: `embedder.py`, `__init__.py`, `pipeline.py`, `store.py`
- `__init__.py` documents it as: "Memory Knowledge Base — position similarity search via Qdrant + TF-IDF"
- `embedder.py` uses TF-IDF on center-weighted piece-square text
- `embedder.py` has a documented upgrade path: "replace TF-IDF with sentence-transformers
  'all-MiniLM-L6-v2' once token format reduces e4 vs d4 cosine similarity below 0.90"
- `scripts/qdrant_spike.py` is the original spike that proved the approach, now superseded by
  the production `memory_kb` module

**Correction:** Qdrant vector search is a WORKING feature with TF-IDF embeddings. The
sentence-transformers upgrade is tracked work, not the current state.

## What remains open (in priority order)

1. **EnginesPage Local tab** — Stockfish and Maia-1500 entries are in `engines.json` at
   `~/.local/share/chess-coach/engines/engines.json` (verified readable, valid JSON, both
   binaries exist and are executable). Tauri scope (`fs:scope-appdata-recursive` with `**`)
   is correct. The `enginesFileStorage.getItem` catch block is currently empty — would need
   a diagnostic log to see the actual error. **Blocked on a Rust-capable environment for
   `pnpm tauri dev` to actually run.**

2. **Backend: populate `pv_moves`/`score_display` in `explain_simple()`** — CoachPanel's
   defensive null check (Fix 1, commit `17d3ee6`) prevents the crash, but PV lines render
   empty. The frontend fix is a band-aid; the real fix is backend.

3. **Backend: narration route handler field-name mismatch** — route uses
   `depth`/`engine_id` instead of `move_san`/`eval_cp`/`game_phase`. This is the same
   root issue as item 2 — a backend field-naming contract that doesn't match what the
   narrator pipeline actually produces. Two bugs in the same component.

4. **Original Priority 4/5** (still queued from much earlier):
   - Architecture doc update
   - Chess.com sync

5. **Optional Phase 4 work** (estimated ~1 hr each):
   - Training queue card polish
   - Opening repertoire gaps UI
   - Tauri production build (.exe/.msi packaging)
   - Qdrant vector DB → sentence-transformers upgrade (the documented path)

## Session hygiene

- **Commits in master:** 6 (unchanged from start of session — no new commit needed)
- **Working tree:** clean (only auto-modified `.a0proj/memory/*` files, Agent Zero internal)
- **No container-specific config** in the repo
- **No phantom commits** created
- **One documentation file added:** this one (`docs/13_review_response/session-2026-06-16-repo-hygiene-and-enginespage.md`)

## Recommendation for next session

The single highest-leverage next action is a successful `pnpm tauri dev` run in a Rust-capable
environment. That resolves the EnginesPage question (most likely root cause: Tauri env path
resolution differs from Node XDG fallback) and confirms the Practice panel UX in a real browser.

Both backend bugs (items 2 and 3 above) are mechanical fixes to `explain_simple()` and the
narration route handler — well-scoped, ~30 min total work, can be done independently of the
Tauri question.
