# SESSION HANDOVER — Storage migrations: missing files

**Date:** 2026-06-19
**Status:** Open — defer to a focused session
**Severity:** Medium (4 unit tests fail on fresh DB; **no production impact** because production DB is at `user_version=7` and the runner skips already-applied migrations)
**Estimated fix effort:** 1–2 hours of focused work

---

## TL;DR

`libs/chess_coach/storage/migrations/0002_perf_indexes.sql` references three tables (`training_cards`, `jobs`, `positions`) that **no migration creates**. On a fresh DB, this raises `MigrationFailedError` and causes 4 tests in `tests/unit/test_storage_migrate.py` to fail.

The bigger problem: the production DB at `/root/.local/share/chess-coach/sqlite/chess_coach.db` has **`PRAGMA user_version = 7`** but the repository only has **2 migration files**. Five migrations (and their table schemas) are missing from the repo.

The fix is non-trivial: it requires adding 5+ new migration files in a specific order, all using `CREATE TABLE IF NOT EXISTS` so they're idempotent across fresh and production DBs. The `discover_migrations()` function also requires contiguous version numbers from 1, which constrains the renumbering.

---

## Root cause (4 tests fail)

**File:** `libs/chess_coach/storage/migrations/0002_perf_indexes.sql`

```sql
CREATE INDEX IF NOT EXISTS idx_training_cards_player_due
    ON training_cards(player_name, due);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_positions_game_id ON positions(game_id, ply);
```

**Problem:** None of `training_cards`, `jobs`, or `positions` are created by `0001_initial.sql`. `0001_initial.sql` only creates the `meta` table (intentionally minimal — see its header comment).

**On a fresh DB:** `migrate()` runs `0001` (creates `meta`, sets `user_version=1`), then tries `0002`. The `CREATE INDEX` statements fail because the tables don't exist. The runner raises `MigrationFailedError`. Four tests in `tests/unit/test_storage_migrate.py` fail:

- `test_creates_db_and_applies_initial`
- `test_idempotent_when_up_to_date`
- `test_meta_table_has_protocol_range`
- `test_wal_mode_after_migrate`

**On production DB (`user_version=7`):** `migrate()` runs `discover_migrations()`, finds 2 migrations with versions 1 and 2, computes `pending = [m for m in migrations if m.version > 7]` → empty list. Logs `up-to-date at user_version=7` and returns. **No error.** Production is unaffected by the 0002 bug because it never tries to run 0002.

---

## The bigger picture (production has 11 tables, repo has 1 in migrations)

`PRAGMA user_version` on the production DB = **7**. The repository has **2 migration files** (`0001_initial.sql`, `0002_perf_indexes.sql`). That means **5 migration files are missing from the repository**.

**All tables in the production DB** (queried via `sqlite_master`):

```
- analyses
- analysis_cache
- games
- jobs
- meta              ← only one with a corresponding migration file (0001)
- narrations
- pdf_import_diagrams
- pdf_imports
- positions
- repertoire_cache
- training_cards
```

The schema has been built ad-hoc, outside the migration runner.

---

## Production schemas (extracted via sqlite_master)

**`training_cards`:**

```sql
CREATE TABLE training_cards (
    id             TEXT NOT NULL PRIMARY KEY,
    player_name    TEXT NOT NULL,
    card_type      TEXT NOT NULL CHECK(card_type IN ('position', 'opening_gap', 'concept')),
    reference_id   TEXT NOT NULL,
    stability      REAL NOT NULL DEFAULT 1.0,
    difficulty     REAL NOT NULL DEFAULT 5.0,
    retrievability REAL NOT NULL DEFAULT 1.0,
    reviews        INTEGER NOT NULL DEFAULT 0,
    lapses         INTEGER NOT NULL DEFAULT 0,
    last_review    TEXT,
    due            TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT
```

**`jobs`:**

```sql
CREATE TABLE jobs (
    id          TEXT NOT NULL PRIMARY KEY,
    type        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','running','done','failed','cancelled')),
    priority    INTEGER NOT NULL DEFAULT 0,
    params      TEXT NOT NULL DEFAULT '{}',
    result      TEXT,
    error       TEXT,
    engine_id   TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
)
```

**`positions`:**

```sql
CREATE TABLE positions (
    id          TEXT NOT NULL PRIMARY KEY,
    game_id     TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    parent_id   TEXT REFERENCES positions(id),
    fen         TEXT NOT NULL,
    move_uci    TEXT,
    move_san    TEXT,
    ply         INTEGER NOT NULL DEFAULT 0,
    is_mainline INTEGER NOT NULL DEFAULT 1
) STRICT
```

(`games` must exist before `positions` because of the FK reference.)

**Other production tables** (full schemas should be extracted via `sqlite_master` SELECT before writing the migration files):

- `analyses`
- `analysis_cache`
- `games`
- `narrations`
- `pdf_imports`
- `pdf_import_diagrams`
- `repertoire_cache`

Command to extract them:

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('/a0/usr/projects/chess_coach/data/sqlite/chess_coach.db')
for table in ['games', 'analyses', 'analysis_cache', 'narrations',
              'pdf_imports', 'pdf_import_diagrams', 'repertoire_cache']:
    rows = db.execute(f\"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'\").fetchall()
    if rows:
        print(f'-- {table}')
        print(rows[0][0] + ';')
        print()
"
```

Don't forget the indexes too:

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('/a0/usr/projects/chess_coach/data/sqlite/chess_coach.db')
for row in db.execute(\"SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name\").fetchall():
    print(row[0] + ';')
"
```

---

## Migration runner behavior — the constraint that shapes the fix

**ADR-0003 (in `libs/chess_coach/storage/migrate.py` lines 1-23):** "On startup we read the database's `PRAGMA user_version`, apply every migration with number > current, each in its own transaction, and bump `user_version` after success."

**Key code paths** (lines 127-180 of `migrate.py`):

```python
current = get_user_version(conn)                              # line 129
pending = [m for m in migrations if m.version > current]      # line 130
if not pending:
    logger.info("storage.migrate: up-to-date at user_version=%d", current)
    return []
# ... applies pending migrations in order ...
full_script = (
    "BEGIN;\n"
    + m.sql.rstrip()
    + f"\nPRAGMA user_version = {int(m.version)};\n"            # line 158
    + "COMMIT;\n"
)
conn.executescript(full_script)
```

**Constraint 1 — runner skips already-applied migrations.** A migration with version <= current `user_version` is silently skipped. This means **any fix must use migration version numbers > 7** for the migrations to actually run on production. Versions 1-7 won't execute.

**Constraint 2 — `discover_migrations()` requires contiguous versions from 1** (lines 60-72):

```python
if migrations:
    expected = list(range(1, len(migrations) + 1))
    actual = [m.version for m in migrations]
    if expected != actual:
        raise MigrationFailedError(
            f"Migration versions are non-contiguous; expected {expected}, got {actual}"
        )
```

So if we have N migration files, they must be numbered exactly 1..N with no gaps. No skipping, no `0002_...` then `0008_...`.

**Constraint 3 — the existing 0001 and 0002 can't be renumbered** without breaking fresh DBs that have already run them. Their schema version is permanently 1 and 2.

---

## The fix path (proposed)

The cleanest path forward:

**Step 1: Add 5 new migration files (0003-0007) that create the missing tables.**

Use `CREATE TABLE IF NOT EXISTS` for idempotency. The ordering must respect FK constraints (`positions.game_id REFERENCES games(id)`):

```
0003_training_cards.sql      -- training_cards table
0004_jobs.sql                -- jobs table
0005_games.sql               -- games table (must exist before positions)
0006_positions.sql           -- positions table (FK to games)
0007_other_tables.sql        -- analyses, narrations, analysis_cache, pdf_imports,
                               -- pdf_import_diagrams, repertoire_cache (single file OK,
                               -- or split if large)
```

**Step 2: Rename `0002_perf_indexes.sql` → `0008_perf_indexes.sql`.**

The indexes now run AFTER all the table-creation migrations. On a fresh DB: tables are created (0003-0007), then indexes (0008). On production at `user_version=7`: only 0008 runs (CREATE INDEX IF NOT EXISTS is idempotent — production already has the indexes, no-op).

**Step 3: Verify the version numbering is contiguous (1..8) and `discover_migrations()` accepts it.**

Run `tests/unit/test_storage_migrate.py::TestDiscovery::test_versions_are_contiguous` to confirm.

**Step 4: Run the 4 failing tests + the full unit suite to confirm green.**

```bash
cd /a0/usr/projects/chess_coach
python -m pytest tests/unit/test_storage_migrate.py -v
python -m pytest tests/ --ignore=tests/integration/test_engine_orch.py
```

**Step 5: Verify on a production-like DB.**

Create a test DB, set `user_version=7`, write the 11 tables, then run `migrate()`. Confirm:
- `pending` is just `[0008]`
- 0008 succeeds (CREATE INDEX IF NOT EXISTS is no-op)
- Final `user_version=8`

**Step 6: Commit.**

```
fix(storage): add missing migration files for tables created ad-hoc

The repository only contained 0001_initial.sql and 0002_perf_indexes.sql,
but 0002 referenced 3 tables that no migration created. Production DB
had reached user_version=7 with 11 tables built ad-hoc outside the
migration runner, which masked the bug for production but caused 4
fresh-DB tests in test_storage_migrate.py to fail.

- Add 0003-0007 with CREATE TABLE IF NOT EXISTS for the missing tables
- Rename 0002_perf_indexes.sql -> 0008_perf_indexes.sql
- All migrations use IF NOT EXISTS for idempotency across fresh DBs and
  production DBs at user_version=7
- 4 failing tests now pass on fresh DBs
- Production DBs at user_version=7 see only 0008 applied (no-op)
```

---

## Alternative (NOT recommended): inline CREATE TABLE in 0002

Adding `CREATE TABLE IF NOT EXISTS training_cards(...)` at the top of `0002_perf_indexes.sql` would fix the 4 failing tests on a fresh DB. **But it doesn't address the bigger problem**: the production schema isn't represented in migrations. Future schema changes will continue to be made ad-hoc, and the migration system will remain incomplete.

Also, this puts table creation in what is conceptually an "index migration" — semantically wrong.

**Skip this path.** The proper fix above is the right one.

---

## Verified facts (with raw outputs captured in this session)

| Fact | Source |
|---|---|
| Production DB path | `/root/.local/share/chess-coach/sqlite/chess_coach.db` (symlinked from `/a0/usr/projects/chess_coach/data/sqlite/chess_coach.db`) |
| Production `user_version` | 7 |
| Production table count | 11 (analyses, analysis_cache, games, jobs, meta, narrations, pdf_import_diagrams, pdf_imports, positions, repertoire_cache, training_cards) |
| Repo migration files | 2 (0001_initial.sql, 0002_perf_indexes.sql) |
| Test files in tests/unit/test_storage_migrate.py | 7 tests; 4 fail (the migration-applied ones), 3 pass (the discovery/contiguous ones) |
| Migration runner behavior | Skips migrations with version <= current user_version; requires contiguous versions from 1 |

---

## Why this isn't being fixed in the current session

Per the user's direction: "the gap between 'production DB has 11 tables at version 7' and 'repo has 2 migration files creating 1 table' is a real, non-trivial problem that deserves its own focused session with the full schema dump in front of us — not a rushed patch tacked onto the end of a session that's already covered a lot of ground."

The current session has covered:
- Memory audit (23 fabricated entries deleted)
- Memory pipeline disable (autodream plugin)
- Rule doc update + commit
- Gateway route_guard work (3 commits)
- Narration response contract (commit `b1c5bf8`)

Piling the storage migration fix on top would be a "rush job" with high risk of getting the FK ordering wrong or missing a table.

---

## Suggested next session agenda

1. Run the two schema-extraction commands in this doc to get full `CREATE TABLE` statements for the 7 missing tables + all indexes
2. Determine FK ordering (`positions → games`, `pdf_import_diagrams → pdf_imports`, etc.)
3. Write 0003-0007 with `CREATE TABLE IF NOT EXISTS`
4. Rename 0002 → 0008
5. Run discovery test + 4 failing tests + full unit suite
6. Commit
7. (Optional) extract the same schema dump to a baseline file in `libs/chess_coach/storage/schema_snapshots/` for future drift detection

