-- Simplify the recovery schema after the initial additive migration.
-- The initial recovery tables are empty; recreate the item log without run/FK/PK constraints.
DROP TABLE IF EXISTS content_link_recovery_items;
DROP TABLE IF EXISTS content_link_recovery_runs;

ALTER TABLE content_links
    DROP CONSTRAINT IF EXISTS content_links_pkey,
    DROP COLUMN IF EXISTS recovery_error,
    DROP COLUMN IF EXISTS recovered_at,
    DROP COLUMN IF EXISTS recovery_attempted_at;

DROP INDEX IF EXISTS content_links_recovery_candidates;

CREATE TABLE IF NOT EXISTS content_link_recovery_items
(
    batch_id            VARCHAR(64),
    content_link_id     BIGINT,
    original_url        TEXT,
    replacement_url     TEXT,
    num_reports_before  INT,
    num_reports_after   INT,
    status              VARCHAR(16) DEFAULT 'pending',
    recovery_method     VARCHAR(32),
    imgur_id            VARCHAR,
    downloaded_size     BIGINT,
    trimmed_size        BIGINT,
    trimmed_sha256     CHAR(64),
    error               TEXT,
    started_at          TIMESTAMP DEFAULT NOW(),
    finished_at         TIMESTAMP
);
