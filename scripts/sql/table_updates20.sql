-- Phase 1: add a separate state for system-detected unavailable media.
-- Apply this before deploying the code that reads content_links.is_dead.
ALTER TABLE content_links
    ADD COLUMN IF NOT EXISTS is_dead BOOLEAN NOT NULL DEFAULT FALSE;
