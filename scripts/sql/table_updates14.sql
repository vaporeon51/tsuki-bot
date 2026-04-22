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

-- Guild (server) ELO per guild per idol
CREATE TABLE IF NOT EXISTS guild_elo (
    guild_id    BIGINT NOT NULL,
    role_id     VARCHAR NOT NULL REFERENCES role_info(role_id) ON DELETE CASCADE,
    guild_elo   INTEGER NOT NULL DEFAULT 1200,
    PRIMARY KEY (guild_id, role_id)
);
