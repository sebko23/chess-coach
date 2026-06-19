-- 0003_level1_tables.sql
-- FK-free tables. Source-of-truth: production sqlite_master dump (2026-06-19).
-- Note: jobs is intentionally NOT STRICT (matches production).

CREATE TABLE IF NOT EXISTS training_cards (
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
) STRICT;

CREATE TABLE IF NOT EXISTS analysis_cache (
    cache_key      TEXT NOT NULL PRIMARY KEY,
    fen            TEXT NOT NULL,
    engine_id      TEXT NOT NULL,
    engine_version TEXT NOT NULL DEFAULT '',
    depth          INTEGER NOT NULL,
    multipv        INTEGER NOT NULL DEFAULT 1,
    settings_hash  TEXT NOT NULL DEFAULT '',
    cpu_arch       TEXT NOT NULL DEFAULT '',
    thread_count   INTEGER NOT NULL DEFAULT 1,
    result_json    TEXT NOT NULL,
    hit_count      INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_hit_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;

CREATE TABLE IF NOT EXISTS repertoire_cache (
    id             TEXT NOT NULL PRIMARY KEY,  -- '{player_name}:{color}'
    tree_json      TEXT NOT NULL,
    gaps_json      TEXT NOT NULL,
    novelties_json TEXT NOT NULL DEFAULT '[]',
    game_count     INTEGER NOT NULL,           -- invalidation check
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;

CREATE TABLE IF NOT EXISTS jobs (
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
);

CREATE TABLE IF NOT EXISTS pdf_imports (
    id               TEXT NOT NULL PRIMARY KEY,   -- ingest_id (uuid hex)
    filename         TEXT NOT NULL,
    page_count       INTEGER NOT NULL DEFAULT 0,
    diagrams_found   INTEGER NOT NULL DEFAULT 0,
    diagrams_valid   INTEGER NOT NULL DEFAULT 0,
    errors_json      TEXT NOT NULL DEFAULT '[]',   -- JSON array of error strings
    completed_at     TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;
