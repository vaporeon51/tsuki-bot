-- Add the missing aggregate counter used by the downvote button and sampler.
ALTER TABLE content_links
    ADD COLUMN IF NOT EXISTS num_downvotes INT NOT NULL DEFAULT 0;
