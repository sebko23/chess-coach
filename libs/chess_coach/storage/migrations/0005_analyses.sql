-- 0005_analyses.sql
-- analyses table. FK -> positions.
-- Source-of-truth: production sqlite_master dump (2026-06-19).
-- Includes 2 ad-hoc columns appended after created_at:
--   classification TEXT, cp_delta REAL  (both nullable, no defaults)

CREATE TABLE IF NOT EXISTS analyses (
    id             TEXT NOT NULL PRIMARY KEY,
    position_id    TEXT NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    engine_id      TEXT NOT NULL,
    depth          INTEGER NOT NULL,
    score_cp       INTEGER,
    score_mate     INTEGER,
    best_move      TEXT,
    pv_moves       TEXT,
    result_json    TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    classification TEXT,
    cp_delta       REAL
) STRICT;
