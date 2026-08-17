-- Aggregate personal taste signals from feeds and content feedback. This is a
-- counter rather than an event log, so storage remains one row per user/idol.
ALTER TABLE user_elo
    ADD COLUMN IF NOT EXISTS activity_score BIGINT NOT NULL DEFAULT 0;
