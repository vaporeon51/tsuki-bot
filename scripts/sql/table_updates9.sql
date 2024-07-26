CREATE TABLE IF NOT EXISTS reddit_feeds
(
    guild_id                  BIGINT NOT NULL PRIMARY KEY,
    channel_id                BIGINT NOT NULL
);