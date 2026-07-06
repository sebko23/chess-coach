# Chess Coach -- Session Handover (2026-07-03)

## Verified state at session end

| Aspect | Value | Source |
|---|---|---|
| HEAD | `4b9babd` on `master` | git rev-parse |
| Last commit | `test(kb): add perf E2E test for skip-re-embed round-trip` | git log -1 |
| Working tree | Clean (only runtime `.a0proj/memory/index.pkl` modified) | git status --short |
| `backups/` hygiene | Closed (directory removed, zero functional impact verified) | ls + git log |
| Qdrant `positions` collection | 25000 points, stable | curl /collections/positions |
| Perf test | Committed, passed in 457.94s, fixture restore independently confirmed | pytest -v -m perf |

## Recent commits (descending)

| SHA | Subject | Theme |
|---|---|---|
| `4b9babd` | test(kb): add perf E2E test for skip-re-embed round-trip | Test coverage |
| `948d9ea` | fix(infra): bump start_gateway.sh polling threshold 60s -> 120s | Infra |
| `3749a4b` | fix(infra): replace sleep 4 with ss-tln polling loop in start_gateway.sh | Infra |
| `4eb8029` | docs: rewrite H2 entry + cross-ref table | Doc accuracy |
| `b2df5e0` | fix(narration): hide Best Line card when pv_moves is empty | UX |
| `0fff171` | fix(gateway): apply route_guard decorator to 5 unprotected route modules | Errors |
| `878cddb` | fix(infra): defer pip install and migrate until after gateway idempotency check | Startup |
| `6b9d610` | fix(kb): make count() tolerant of Qdrant errors | KB |
| `bd544ff` | fix(kb): skip re-embed in index_positions when Qdrant already has sufficient points | KB |
| `b1a5c5d` | fix(kb): skip _ensure_collection recreation when collection exists with matching dim | KB |

## Architecture (verified against the file tree)

### Backend services (`services/chess_coach/`)
- `gateway/` -- FastAPI app, 8 routes (blunder, game, players, profile, profile_analysis, repertoire, training, kb)
- `engine_orch/` -- EnginePool + supporting (target of Phase 3)
- `kb/` -- `pipeline.py` (index_positions) + `store.py` (PositionStore/Qdrant wrapper)
- `narration/` -- `pipeline.py` (explain_simple) + `validator.py` (target of Phase 3)
- `llm_router/` -- OpenRouter integration
- `jobs/`, `analysis/`, `debug/` -- supporting services

### Libraries (`libs/chess_coach/`)
- `errors/` -- typed error envelope (ADR-0002), `route_guard` decorator
- `storage/` -- SQLite + FAISS + `migrate.py` (writes to `${CHESS_COACH_DATA_DIR}/backups/`, NOT project-root)
- `protocol_types/` -- AnalysisResult, PVLine, Score wire types
- `uci/` -- UCI engine protocol
- `testkit/` -- mock UCI engine for tests

### Storage stack
- SQLite at `/root/.local/share/chess-coach/sqlite/chess_coach.db` (14151 rows in ply 4-40 window)
- Qdrant at port 6333, data at `/a0/usr/projects/chess_coach/data/qdrant/`, `positions` collection at 25000 points
- FAISS at `.a0proj/memory/index.faiss` (project-level memory, separate from Qdrant)
- Snapshots at `data/qdrant/snapshots/positions/` (used by perf test fixture)

### Frontend (`apps/desktop/`)
- Tauri-based, forked from en-croissant
- Jotai state (ADR-0005), TypeScript path alias `@/state/atoms/...`
- Pages: `RepertoirePage.tsx`, `TrainingQueuePage.tsx`
- Components: `src/components/panels/`

### Engines (`data/engines/`)
- Stockfish 18 (primary)
- Leela Chess Zero (`lc0`)
- Maia (`maia-1500.pb`)
- Berserk, Komodo, Ethereal (listed in master prompt, not yet verified integrated)

## Verified this session

1. Perf E2E test for skip-re-embed round-trip -- committed, passed in 457.94s, fixture restore independently confirmed (post-test `points_count = 25000`)
2. Snapshot/restore round-trip with `SnapshotPriority.SNAPSHOT` -- verified end-to-end via the perf test fixture
3. Qdrant recovery from thread-spawn panic (`WouldBlock` in `wal::segment::Segment::flush_async`) -- recovered via process restart; storage on disk intact; root cause NOT fixed at Qdrant level
4. Pytest `@pytest.mark.perf` infrastructure -- marker defined in `pyproject.toml`, `--strict-markers` enforced, `tests/perf/` with own conftest bypassing the top-level `_isolate_env` autouse by passing explicit args
5. `migrate.py` backup path disambiguation -- `${CHESS_COACH_DATA_DIR}/backups/` resolves to `/root/.local/share/chess-coach/backups/`, NOT the project-root `backups/` we removed

## Open / known issues (honest accounting)

| Issue | Status | Severity |
|---|---|---|
| Qdrant thread-spawn panic root cause | Not fixed; recovered via restart | Medium |
| Gateway died from unexplained external kill | Logged as "died for unknown reasons, recovered cleanly" | Low |
| `explain_simple()` synthetic PVLine (`moves=[]`) | UX fixed at `b2df5e0` (hide empty card); API surface still synthetic | Medium |
| Routes needing `route_guard` | 5 of 7 fixed at `0fff171`; 2 remain (need fresh audit) | Low |
| Berserk/Komodo/Ethereal engine integration | Listed, not verified integrated | Low |

## Roadmap

### Phase 3: Engine-backed narration (next major thread)
- Wire `engine_pool.analyze()` into narration pipeline
- Branch on `depth` / `engine_id` / `multipv`
- Replace `explain_simple()`'s synthetic PVLine with real `AnalysisResult` data
- Frontend interaction for `pv_moves` / `score_display` / Best-Line-card (already partially addressed at `b2df5e0`)

### Post-Phase 3 candidates
- Test coverage gaps in the kb pipeline (`count`, `index_positions` decision branch) -- perf test now provides one anchor
- Remaining 2 unprotected routes (`route_guard`)
- Qdrant thread-spawn mitigation (if it recurs)
- Frontend Tauri build verification (per Phase 4 options)
- Repertoire gaps UI (per Phase 4 options)
- Skill selector / training plan UI (per Phase 4 options)

### Defer (lower priority)
- Berserk/Komodo/Ethereal engine integration
- Voice coaching (master prompt explicitly says NOT initially)
- Cloud sync (Lichess/Chess.com) -- currently no infrastructure
- PDF/Vision OCR pipeline -- `ocr_spike.py` exists but not integrated

## Decision discipline notes (logged to memory this session)

1. **Mutating-write discipline**: when a write operation's output is ambiguous (e.g., empty in relay corruption), run read-only verification (`git status`, `git log`). NEVER substitute a different write operation without explicit authorization. The perf-test commit had a violation of this pattern (substituted `git commit -F` for `git commit -m`), caught and corrected within the thread.
2. **Output labeling discipline**: never present output as "fresh" when it was recycled from a prior session/thread. Always run the read fresh in the current thread before reporting.
3. **Memory hygiene**: stale memories (especially about prior "bugs" or "fixes") should be flagged as stale on contact, not applied as directives.

## Open-list H2 entry status (as of session end)

The H2 entry in `docs/13_review_response/session-2026-06-16-repo-hygiene-and-enginespage.md` was rewritten at `4eb8029` to fix an overstated `b1c5bf8` claim. Subsequent commits have closed out most of the open items. Remaining "open" items are now scoped under Phase 3 narration work (per the roadmap above).
