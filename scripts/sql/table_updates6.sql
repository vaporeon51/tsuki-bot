CREATE TABLE IF NOT EXISTS update_log
(
    processed_date                  TIMESTAMP NOT NULL PRIMARY KEY,
    last_message_id                 VARCHAR(1000) NOT NULL,
    rows_inserted                   INT
);

INSERT INTO "update_log" ("processed_date", "last_message_id", "rows_inserted") VALUES
    ('2024-06-15 17:00:00', '1251627543191355495', 50012);

-- Update content links with processed date column
ALTER TABLE content_links
ADD COLUMN processed_date TIMESTAMP;

UPDATE content_links
SET processed_date = '2024-06-15 17:00:00';

-- Remove unused columns
ALTER TABLE content_links
DROP COLUMN num_downvotes, 
DROP COLUMN is_broken;