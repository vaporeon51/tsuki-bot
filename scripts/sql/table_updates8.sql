CREATE TABLE IF NOT EXISTS bot_stats
(
    "stat_name"                    VARCHAR(1000) NOT NULL PRIMARY KEY,
    "value"                        INT NOT NULL DEFAULT 0
);