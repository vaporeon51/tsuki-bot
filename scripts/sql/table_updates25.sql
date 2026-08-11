-- Historical recovery attempts all used the one-frame transform. They are not
-- a cumulative frame-removal lineage, so normalize the existing baseline to 1.
BEGIN;

UPDATE content_link_recovery_items
SET replacement_generation = 1
WHERE status = 'updated';

UPDATE content_links
SET recovery_generation = CASE
    WHEN original_url IS NULL THEN 0
    ELSE 1
END;

COMMIT;
