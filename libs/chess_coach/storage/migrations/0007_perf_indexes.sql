-- 0007_perf_indexes.sql
-- All 17 production indexes. Source-of-truth: production sqlite_master dump (2026-06-19).
-- 3 are from the original 0002_perf_indexes.sql; 14 were created ad-hoc in production.
-- All use IF NOT EXISTS for idempotency. idx_training_cards_ref is a UNIQUE INDEX.
-- Production has 2 duplicate index pairs (intentionally not dropped):
--   idx_positions_game_id + positions_game_id (both on positions(game_id, ply))
--   idx_training_cards_player_due + training_cards_due (both on training_cards(player_name, due))

CREATE INDEX IF NOT EXISTS analyses_position_engine
    ON analyses(position_id, engine_id, depth DESC);

CREATE INDEX IF NOT EXISTS analysis_cache_evict
    ON analysis_cache(last_hit_at);

CREATE INDEX IF NOT EXISTS analysis_cache_lookup
    ON analysis_cache(fen, engine_id, depth);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON jobs(status, created_at);

CREATE INDEX IF NOT EXISTS idx_positions_game_id
    ON positions(game_id, ply);

CREATE INDEX IF NOT EXISTS idx_training_cards_player_due
    ON training_cards(player_name, due);

CREATE UNIQUE INDEX IF NOT EXISTS idx_training_cards_ref
    ON training_cards(reference_id);

CREATE INDEX IF NOT EXISTS jobs_created_at
    ON jobs(created_at ASC);

CREATE INDEX IF NOT EXISTS jobs_status_priority
    ON jobs(status, priority DESC, created_at ASC);

CREATE INDEX IF NOT EXISTS narrations_position
    ON narrations(position_id);

CREATE INDEX IF NOT EXISTS pdf_import_diagrams_game
    ON pdf_import_diagrams(game_id) WHERE game_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS pdf_import_diagrams_ingest
    ON pdf_import_diagrams(ingest_id);

CREATE INDEX IF NOT EXISTS positions_fen
    ON positions(fen);

CREATE INDEX IF NOT EXISTS positions_game_id
    ON positions(game_id, ply);

CREATE INDEX IF NOT EXISTS training_cards_due
    ON training_cards(player_name, due ASC);

CREATE INDEX IF NOT EXISTS training_cards_type
    ON training_cards(player_name, card_type);
