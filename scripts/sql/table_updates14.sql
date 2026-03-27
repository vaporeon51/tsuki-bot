-- Global ELO per idol (keyed off existing role_info.role_id)
ALTER TABLE role_info ADD COLUMN IF NOT EXISTS global_elo INTEGER NOT NULL DEFAULT 1200;
ALTER TABLE role_info ADD COLUMN IF NOT EXISTS image_url VARCHAR;

-- Personal ELO per user per idol
CREATE TABLE IF NOT EXISTS user_elo (
    user_id     BIGINT NOT NULL,
    role_id     VARCHAR NOT NULL REFERENCES role_info(role_id) ON DELETE CASCADE,
    personal_elo INTEGER NOT NULL DEFAULT 1200,
    PRIMARY KEY (user_id, role_id)
);

-- Match log
CREATE TABLE IF NOT EXISTS elo_matches (
    id          SERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    winner_id   VARCHAR NOT NULL REFERENCES role_info(role_id) ON DELETE CASCADE,
    loser_id    VARCHAR NOT NULL REFERENCES role_info(role_id) ON DELETE CASCADE,
    global_winner_delta INTEGER NOT NULL,
    global_loser_delta  INTEGER NOT NULL,
    personal_winner_delta INTEGER NOT NULL,
    personal_loser_delta  INTEGER NOT NULL,
    matched_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS elo_matches_user_id ON elo_matches(user_id);
