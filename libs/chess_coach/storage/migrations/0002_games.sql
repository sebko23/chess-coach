-- 0002_games.sql
-- Games table. Source-of-truth: production schema dump (live, 2026-06-19).

CREATE TABLE IF NOT EXISTS games (
    id            TEXT NOT NULL PRIMARY KEY,
    pgn_raw       TEXT NOT NULL,
    white         TEXT,
    black         TEXT,
    date          TEXT,
    event         TEXT,
    site          TEXT,
    result        TEXT,
    import_status TEXT NOT NULL DEFAULT 'pending'
                      CHECK(import_status IN ('pending','analyzing','done','failed')),
    job_id        TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;
