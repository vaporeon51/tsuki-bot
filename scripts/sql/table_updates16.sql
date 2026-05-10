-- Per-idol vote stats for /bias analytics.
-- These are scope-local counters: global on role_info, server on guild_elo,
-- and personal on user_elo.
ALTER TABLE role_info
    ADD COLUMN IF NOT EXISTS global_win_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS global_match_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE user_elo
    ADD COLUMN IF NOT EXISTS win_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS match_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE guild_elo
    ADD COLUMN IF NOT EXISTS win_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS match_count INTEGER NOT NULL DEFAULT 0;
