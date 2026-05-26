-- Sparse historical snapshots for bias idol leaderboards.
-- A scope only gets a new weekly snapshot when its top-N ranks or ELOs differ
-- from the previous stored snapshot for that same scope.
CREATE TABLE IF NOT EXISTS bias_leaderboard_snapshots (
    snapshot_date   DATE NOT NULL,
    snapshot_period VARCHAR NOT NULL DEFAULT 'weekly',
    scope_type      VARCHAR NOT NULL,
    scope_id        BIGINT NOT NULL DEFAULT 0,
    role_id         VARCHAR NOT NULL REFERENCES role_info(role_id) ON DELETE CASCADE,
    rank            INTEGER NOT NULL,
    elo             INTEGER NOT NULL,
    vote_count      INTEGER NOT NULL DEFAULT 0,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (snapshot_date, snapshot_period, scope_type, scope_id, role_id),
    UNIQUE (snapshot_date, snapshot_period, scope_type, scope_id, rank),
    CONSTRAINT bias_leaderboard_snapshots_scope_type_chk
        CHECK (scope_type IN ('global', 'guild', 'personal')),
    CONSTRAINT bias_leaderboard_snapshots_period_chk
        CHECK (snapshot_period IN ('weekly', 'daily'))
);

CREATE INDEX IF NOT EXISTS bias_leaderboard_snapshots_lookup_idx
ON bias_leaderboard_snapshots (
    scope_type,
    scope_id,
    snapshot_period,
    snapshot_date DESC,
    rank
);

CREATE INDEX IF NOT EXISTS bias_leaderboard_snapshots_cleanup_idx
ON bias_leaderboard_snapshots (snapshot_date);

CREATE INDEX IF NOT EXISTS birthday_messages_post_datetime_idx
ON birthday_messages (post_datetime);

CREATE INDEX IF NOT EXISTS bias_daily_completions_completion_date_idx
ON bias_daily_completions (completion_date);
