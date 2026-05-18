-- 0001_initial.sql
-- Initial Phase-1 schema. Just the meta table for now; real Phase-1 tables
-- (games, analyses, engines, narrations, jobs, kb_documents, fts5 indexes)
-- will be added in their own migrations as the corresponding features land.
--
-- This migration is intentionally minimal so that the gateway can boot
-- against a writable database before any feature code is in place.

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

INSERT INTO meta (key, value) VALUES
    ('schema_origin', 'chess_coach.storage 0001_initial'),
    ('created_by',    'migrate.migrate()'),
    ('protocol_min',  '1.0.0'),
    ('protocol_max',  '1.0.0');
