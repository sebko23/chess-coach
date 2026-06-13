-- 0002_perf_indexes.sql
-- Performance indexes for hot query paths.
-- Positions joined via game_id, so ply index helps range scans.
-- Training cards and jobs use direct player_name / status filters.
CREATE INDEX IF NOT EXISTS idx_training_cards_player_due
    ON training_cards(player_name, due);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_positions_game_id ON positions(game_id, ply);
