-- 0006_narrations_and_pdf_diagrams.sql
-- narrations (FK -> positions) and pdf_import_diagrams (FK -> pdf_imports, nullable FK -> games).
-- Source-of-truth: production sqlite_master dump (2026-06-19).

CREATE TABLE IF NOT EXISTS narrations (
    id          TEXT NOT NULL PRIMARY KEY,
    position_id TEXT NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    model       TEXT NOT NULL,
    narration   TEXT NOT NULL,
    validated   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;

CREATE TABLE IF NOT EXISTS pdf_import_diagrams (
    id            TEXT NOT NULL PRIMARY KEY,   -- uuid hex
    ingest_id     TEXT NOT NULL REFERENCES pdf_imports(id) ON DELETE CASCADE,
    page_number   INTEGER NOT NULL,
    diagram_index INTEGER NOT NULL,
    fen           TEXT NOT NULL DEFAULT '',
    valid         INTEGER NOT NULL DEFAULT 0,  -- boolean
    confidence    REAL NOT NULL DEFAULT 0.0,
    issues_json   TEXT NOT NULL DEFAULT '[]',  -- JSON array of issue strings
    game_id       TEXT,                         -- FK into games.id (nullable)
    job_id        TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;
