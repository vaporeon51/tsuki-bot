CREATE TABLE IF NOT EXISTS dead_link_check_state
(
    state_id    SMALLINT PRIMARY KEY DEFAULT 1 CHECK (state_id = 1),
    last_url    TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
