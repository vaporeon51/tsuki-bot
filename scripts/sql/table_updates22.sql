-- Stop retrying links after two confirmed attempts found no usable media.
ALTER TABLE content_links
    ADD COLUMN IF NOT EXISTS is_recovery_exhausted BOOLEAN NOT NULL DEFAULT FALSE;
