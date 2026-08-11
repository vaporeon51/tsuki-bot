-- Track recovery lineage so each replacement is a distinct derivative of the
-- original Discord/Imgur source rather than an endlessly re-encoded prior copy.
ALTER TABLE content_links
    ADD COLUMN IF NOT EXISTS recovery_generation INTEGER NOT NULL DEFAULT 0;

ALTER TABLE content_link_recovery_items
    ADD COLUMN IF NOT EXISTS replacement_generation INTEGER;

-- Preserve the generation number for historical successful recoveries.
WITH ranked_recoveries AS (
    SELECT
        ctid,
        ROW_NUMBER() OVER (
            PARTITION BY content_link_id
            ORDER BY finished_at NULLS LAST, started_at NULLS LAST, batch_id
        )::INTEGER AS generation
    FROM content_link_recovery_items
    WHERE status = 'updated'
)
UPDATE content_link_recovery_items AS item
SET replacement_generation = ranked_recoveries.generation
FROM ranked_recoveries
WHERE item.ctid = ranked_recoveries.ctid
  AND item.replacement_generation IS NULL;

UPDATE content_links AS link
SET recovery_generation = GREATEST(
    link.recovery_generation,
    COALESCE(
        (
            SELECT MAX(item.replacement_generation)
            FROM content_link_recovery_items AS item
            WHERE item.content_link_id = link.content_link_id
              AND item.status = 'updated'
        ),
        0
    )
);
