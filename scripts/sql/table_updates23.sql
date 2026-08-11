-- Preserve Discord provenance for incremental ingestion and historical backfills.
-- Apply this before deploying the shared content-ingestion code.
ALTER TABLE content_links
    ADD COLUMN IF NOT EXISTS source_message_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS root_message_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS source_kind VARCHAR(32);

-- Makes incremental retries and backfill reruns idempotent without affecting legacy rows,
-- whose provenance columns remain NULL.
CREATE UNIQUE INDEX IF NOT EXISTS content_links_source_message_role_url_unique
    ON content_links (source_message_id, role_id, url)
    WHERE source_message_id IS NOT NULL;
