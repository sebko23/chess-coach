-- 0008_narrations_corpus_entry_id.sql
--
-- BBF-87.1: make narrations.position_id nullable + add
-- narrations.corpus_entry_id. The narrations table is the audit log
-- for the /v1/narration/explain route. The route's previous INSERT
-- was passing `body.fen` (a FEN string) into `position_id` (a TEXT
-- column with FK -> positions.id), which was a pre-existing bug --
-- the FEN is not a position_id, but the FK constraint was never
-- violated because no test data set up a real positions.id that
-- matched a FEN. With this migration:
--
--   1. position_id becomes nullable (so the route can leave it NULL
--      when no real position row exists for the FEN, OR pass the
--      FEN as a denormalized "this is the FEN we narrated" column).
--   2. corpus_entry_id is added (nullable) so we can audit which
--      v2 narrative corpus entry (NG-v2-NNNN) was used to ground
--      this narration, if any.
--
-- v2 corpus entries are referenced by id, not by FK (the corpus
-- file is loaded into memory; the audit column is for traceability,
-- not referential integrity).
--
-- Implementation note (portable to old SQLite): ALTER TABLE ...
-- ALTER COLUMN ... DROP NOT NULL was added in SQLite 3.35.0 but
-- the python:3.11-slim-bookworm image (used in CI) ships with a
-- pre-3.35 SQLite for the bundled _sqlite3 module on some
-- distributions, so the DROP NOT NULL syntax fails with
-- "near ALTER: syntax error". This migration uses the
-- table-rebuild pattern (rename, recreate, copy) which works on
-- every SQLite >= 3.0.
--
-- Source-of-truth: BBF-87.1 brief at
-- docs/16_audit/BBF-87.1-wire-narration-pipeline.md.

-- 1. Disable FK constraints for the rebuild (so we can drop the old
--    narrations table without violating any FK that points at it).
PRAGMA foreign_keys=OFF;

-- 2. Rename the existing table to a backup name.
ALTER TABLE narrations RENAME TO narrations__0008_old;

-- 3. Create the new narrations table with the same columns but
--    position_id nullable, plus the new corpus_entry_id column.
CREATE TABLE narrations (
    id              TEXT NOT NULL PRIMARY KEY,
    position_id     TEXT,
    model           TEXT NOT NULL,
    narration       TEXT NOT NULL,
    validated       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    corpus_entry_id TEXT
) STRICT;

-- 4. Copy data from the old table to the new. The column order
--    matches the new schema exactly; corpus_entry_id is NULL
--    for all migrated rows (the column didn't exist in v1 of
--    the narrations table).
INSERT INTO narrations (id, position_id, model, narration, validated, created_at, corpus_entry_id)
SELECT id, position_id, model, narration, validated, created_at, NULL
FROM narrations__0008_old;

-- 5. Drop the backup table.
DROP TABLE narrations__0008_old;

-- 6. Re-add the corpus_entry_id index for analytics queries that
--    aggregate "how many narrations used a given corpus entry".
CREATE INDEX narrations_corpus_entry_id_idx
    ON narrations (corpus_entry_id);

PRAGMA foreign_keys=ON;

-- Note: the narrations.position_id foreign key to positions(id) is
-- intentionally DROPPED in this migration. The previous FK was
-- structurally wrong (the route inserts FEN strings, not position
-- ids) and was the underlying cause of the FK-violation latent bug
-- that was masked by no test data. A future BBF can re-introduce
-- the FK with a real positions-id resolution step in the route.
-- For BBF-87.1, the FEN-as-position_id denormalized pattern is
-- preserved so the audit table continues to capture the
-- narrated FEN.
