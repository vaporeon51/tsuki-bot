-- Track per-user completions of the /bias daily bracket challenge.
-- Composite PK ensures one completion row per user per KST-date; the gate on
-- /autofeed and /bias autofeed checks for today's row.
CREATE TABLE IF NOT EXISTS bias_daily_completions (
    user_id         BIGINT NOT NULL,
    completion_date DATE NOT NULL,
    PRIMARY KEY (user_id, completion_date)
);
