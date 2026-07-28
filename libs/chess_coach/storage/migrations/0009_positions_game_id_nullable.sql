-- 0009_positions_game_id_nullable.sql
--
-- BBF-87.1.y: make positions.game_id nullable.
--
-- The positions table was originally created in 0004_positions.sql
-- with `game_id TEXT NOT NULL REFERENCES games(id)`, which assumes
-- every position belongs to a game. This held for the import-PGN
-- flow (services/chess_coach/gateway/routes/pgn_import.py), but
-- the narration route (services/chess_coach/gateway/routes/narration.py)
-- is FEN-only: it receives a FEN with no game context.
--
-- BBF-87.1 dropped the narrations.position_id FK to unblock the
-- route (it was inserting FEN strings into a position_id column
-- that should reference positions.id). BBF-87.1.y makes the
-- positions table FEN-friendly: positions.game_id becomes NULL-able,
-- and the route inserts a freeform positions row (game_id=NULL)
-- when a FEN is narrated without a game.
--
-- After this migration:
--   - Existing positions rows (with valid game_id) keep working;
--     the import-PGN flow's INSERT statements still satisfy the
--     semantics of "every position is game-scoped" when they fill
--     in game_id.
--   - The narration route can now insert positions rows with
--     game_id=NULL for FEN-only cases.
--   - The narrations.position_id FK to positions(id) is re-satisfied
--     by the lookup-or-insert pattern in the route.
--
-- Implementation note (portable to old SQLite, per BBF-87.1
-- lesson): ALTER TABLE ... ALTER COLUMN ... DROP NOT NULL was added
-- in SQLite 3.35.0 but the python:3.11-slim-bookworm image (used
-- in CI) ships with a pre-3.35 _sqlite3 module on some
-- distributions, so the modern syntax fails with
-- "near ALTER: syntax error". This migration uses the
-- table-rebuild pattern (rename, recreate, copy) which works on
-- every SQLite >= 3.0.
--
-- Source-of-truth: BBF-87.1.y brief at
-- docs/16_audit/BBF-87.1.y-position-fk.md.

-- 1. Disable FK constraints for the rebuild (so we can drop the old
--    positions table without violating any FK that points at it).
PRAGMA foreign_keys=OFF;

-- 2. Rename the existing table to a backup name.
ALTER TABLE positions RENAME TO positions__0009_old;

-- 3. Create the new positions table with game_id nullable, plus
--    a new index on fen for the narration route's lookup.
CREATE TABLE positions (
    id          TEXT NOT NULL PRIMARY KEY,
    game_id     TEXT REFERENCES games(id) ON DELETE CASCADE,
    parent_id   TEXT REFERENCES positions(id),
    fen         TEXT NOT NULL,
    move_uci    TEXT,
    move_san    TEXT,
    ply         INTEGER NOT NULL DEFAULT 0,
    is_mainline INTEGER NOT NULL DEFAULT 1
) STRICT;

-- 4. Copy data from the old table to the new. Columns that were
--    NOT NULL in 0004 stay NOT NULL here; only game_id loses its
--    NOT NULL constraint. All other columns copy through 1:1.
INSERT INTO positions (id, game_id, parent_id, fen, move_uci, move_san, ply, is_mainline)
SELECT id, game_id, parent_id, fen, move_uci, move_san, ply, is_mainline
FROM positions__0009_old;

-- 5. Drop the backup table.
DROP TABLE positions__0009_old;

-- 6. Add an index on positions.fen for the narration route's
--    lookup step ("SELECT id FROM positions WHERE fen = ?").
--    Without this index, every narration request does a table scan
--    on positions. With 30+ game positions, the scan is small, but
--    as the corpus grows the index becomes load-bearing.
CREATE INDEX positions_fen_idx ON positions (fen);

PRAGMA foreign_keys=ON;

-- Note: the FOREIGN KEY (game_id REFERENCES games(id)) is preserved
-- as a NULL-able constraint, so when game_id IS NOT NULL the value
-- must still be a valid games.id. The narration route's freeform
-- positions rows (with game_id=NULL) are exempt from the FK
-- constraint by the null exemption (SQLite allows NULL in FK
-- columns).
