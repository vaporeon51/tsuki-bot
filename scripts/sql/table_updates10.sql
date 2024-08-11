-- Start a transaction to ensure atomicity
BEGIN;

-- Create the new table with the desired schema
CREATE TABLE IF NOT EXISTS new_reddit_feeds
(
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    subreddit  VARCHAR(1000) NOT NULL,
    PRIMARY KEY (guild_id, channel_id, subreddit)
);

-- Insert data from the old table into the new table, setting the default value for subreddit
INSERT INTO new_reddit_feeds (guild_id, channel_id, subreddit)
SELECT guild_id, channel_id, 'kpopfap'
FROM reddit_feeds;

-- If everything is correct, drop the old table
DROP TABLE reddit_feeds;

-- Optionally, rename the new table to the old name
ALTER TABLE new_reddit_feeds RENAME TO reddit_feeds;

-- Commit the transaction
COMMIT;
