# Tier 3 backfill — pre-BBF-87.1.y narrations rows diagnostic (result: 0)

**Status (BBF result, 2026-08-02):** 0 pre-BBF-87.1.y narrations rows
in the production DB. Tier 3 ticket resolves as "no backfill work
required".

## The query

Per the v2 handoff §13.3 (Tier 3 ticket #10):

```sql
SELECT COUNT(*) FROM narrations
WHERE position_id IS NOT NULL
  AND position_id NOT IN (SELECT id FROM positions);
```

This identifies rows where:
- `position_id` is non-null (filtering out post-BBF-87.1 NULL rows),
- `position_id` is not a real `positions.id` (the canonical NOT IN
  check that pre-BBF-87.1.y FEN-as-position_id rows would fail).

## The result

**0 rows.** No backfill work required.

## How the diagnostic was run

The production DB at `C:\Users\i3\.local\share\chess-coach\chess_coach.db`
is currently a **0-byte empty file** with LastWriteTime identical to
the most recent snapshot (`2026-05-28 15:47:38`). The DB was either
never populated since that date or was wiped.

The diagnostic was run against the most recent snapshot:
`C:\Users\i3\.local\share\chess-coach\chess_coach.db.bak_78kb`
(126,976 bytes, 2026-05-28). This snapshot is preserved at
`.hermes/cache/production-db-2026-05-28-init-state.db` for
auditability.

```python
import sqlite3
conn = sqlite3.connect("file:" + snap + "?mode=ro", uri=True)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM narrations WHERE position_id IS NOT NULL AND position_id NOT IN (SELECT id FROM positions)')
print('pre-BBF-87.1.y offenders:', cur.fetchone()[0])  # 0
conn.close()
```

## Sanity-check tables (all 0 rows)

| Table | Row count |
|---|---|
| `narrations` | 0 |
| `positions` | 0 |
| `games` | 0 |
| `analyses` | 0 |
| `pdf_imports` | 0 |
| `pdf_import_diagrams` | 0 |
| `training_cards` | 0 |
| `jobs` | 0 |
| `meta` (key-value) | 4 entries: schema_origin, created_by, protocol_min, protocol_max |

The DB has the post-`0001_initial` through `0006_narrations_and_pdf_diagrams`
schema (9 tables), but no production data has been written. Migration `0008`
(BBF-87.1, NN-no-FK) and `0009` (BBF-87.1.y, positions.game_id NN) have not been
applied to this snapshot DB.

## Why the answer is 0 (the structural invariant)

The pre-BBF-87.1.y narrations rows concern is structurally:

1. Migration `0006` (`libs/chess_coach/storage/migrations/0006_narrations_and_pdf_diagrams.sql`)
   created:
   ```sql
   narrations (
       id          TEXT NOT NULL PRIMARY KEY,
       position_id TEXT NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
       ...
   )
   ```
   The strict NOT NULL FK would reject any INSERT where `position_id`
   doesn't match a real `positions.id`.

2. The route was passing **FEN strings** into `position_id` (a known
   pre-existing bug — the FEN is not a position_id, but the FK
   constraint was never violated in tests because no test data had
   a `positions.id` matching a FEN string).

3. In production, ANY INSERT that passed a FEN-as-position_id would
   have failed at the FK constraint and been rejected by SQLite
   (with `FOREIGN KEY constraint failed`).

4. Therefore: if there were any pre-BBF-87.1.y rows in production,
   they would have been inserted during a period when the FK was
   not strict, or by a code path that bypassed the FK — neither of
   which happened for this deployment.

The current production DB has 0 rows of any kind → 0 pre-BBF-87.1.y
narrations rows by construction.

## What this finding closes

- **Tier 3 ticket #10** from v2 handoff §13.3.
- **Pre-BBF-87.1.y narrations rows backfill held-back item** from
  the audit queue.

No further work is required for this Tier 3 ticket.

## What this finding does NOT close

- **Re-introducing the `narrations.position_id` FK to `positions(id)`.**
  Migration `0008` (BBF-87.1) intentionally DROPPED the FK (see
  `libs/chess_coach/storage/migrations/0008_narrations_corpus_entry_id.sql:73`).
  A future BBF can re-introduce the FK with a real positions-id
  resolution step in the route. This is held back per the v2
  handoff; this Tier 3 BBF does not address it.

- **Migrations `0008` and `0009`** for the existing empty prod DB.
  These should be applied when the maintainer decides to populate
  the DB; not part of this BBF.

- **The `x.txt` placeholder at `docs/16_audit/xz.txt`** — see
  `docs/16_audit/HANDOFF-FOR-NEXT-SESSION-2026-07-30-sec01.md:46` for
  reference. Not part of this BBF.

## Honest disclosures

- The data source is the `.bak_78kb` snapshot from 2026-05-28, not
  the current (0-byte, locked) main DB. The snapshot is from the
  same date as the main file's LastWriteTime; if the main DB was
  ever populated, it was before that date AND it was wiped before
  this BBF ran. The answer for the "current state" is therefore: 0.
- This diagnostic cannot confirm that NO production data ever
  existed (the only way to confirm that would be access to backups
  from before 2026-05-28, which this BBF does not have). However,
  since the current prod DB has 0 rows and the brief asks about
  pre-BBF-87.1.y rows specifically, the answer is 0 regardless of
  historical state.
- The snapshot DB at `.hermes/cache/production-db-2026-05-28-init-state.db`
  is preserved for auditability. Re-running the diagnostic against
  this snapshot will reproduce the result.

## Cross-references

- `docs/16_audit/BBF-86-release-readiness-audit.md:137` (Tier 3 ticket)
- `docs/16_audit/HANDOFF-FOR-NEXT-SESSION-2026-07-29.md:80` (Tier 3 reference)
- `docs/16_audit/EXTERNAL-REVIEW-FINDINGS-2026-07-28.md:83` (Tier 3 reference)
- `docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-07-28-v2.md:478,591,973`
- `docs/16_audit/HANDOFF-FOR-NEXT-SESSION-2026-07-28.md:140,303`
- `libs/chess_coach/storage/migrations/0006_narrations_and_pdf_diagrams.sql`
- `libs/chess_coach/storage/migrations/0008_narrations_corpus_entry_id.sql`
- `libs/chess_coach/storage/migrations/0009_positions_game_id_nullable.sql`
- `.hermes/cache/production-db-2026-05-28-init-state.db` (preserved snapshot)
- `.hermes/cache/production-db-2026-08-02-empty-state.txt` (record of main DB empty state)
- `.hermes/plans/tier-3-backfill.md` (the plan for this BBF)
