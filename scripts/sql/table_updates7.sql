CREATE TABLE IF NOT EXISTS guild_settings
(
    guild_id                  BIGINT NOT NULL PRIMARY KEY,
    min_age                   VARCHAR(1000)
);