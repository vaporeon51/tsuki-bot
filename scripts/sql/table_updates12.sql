CREATE TABLE IF NOT EXISTS birthday_feeds
(
    guild_id                  BIGINT NOT NULL PRIMARY KEY,
    channel_id                BIGINT NOT NULL
    PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS birthday_messages
(
    guild_id                  BIGINT NOT NULL PRIMARY KEY,
    channel_id                BIGINT NOT NULL,
    role_id                   VARCHAR,
    post_datetime             TIMESTAMP
);