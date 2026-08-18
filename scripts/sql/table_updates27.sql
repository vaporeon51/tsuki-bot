-- Mark role assignments that an admin has explicitly reviewed with /admin disambiguate.
ALTER TABLE content_links
    ADD COLUMN IF NOT EXISTS disambiguated BOOLEAN NOT NULL DEFAULT FALSE;
