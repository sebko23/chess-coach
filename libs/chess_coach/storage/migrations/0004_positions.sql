-- 0004_positions.sql
-- positions table. FK -> games, self-ref parent_id.
-- Source-of-truth: production sqlite_master dump (2026-06-19).

CREATE TABLE IF NOT EXISTS positions (
    id          TEXT NOT NULL PRIMARY KEY,
    game_id     TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    parent_id   TEXT REFERENCES positions(id),
    fen         TEXT NOT NULL,
    move_uci    TEXT,
    move_san    TEXT,
    ply         INTEGER NOT NULL DEFAULT 0,
    is_mainline INTEGER NOT NULL DEFAULT 1
) STRICT;
