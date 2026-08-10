-- Phase 2: seed the new dead-link state after the is_dead-aware code is deployed.
-- Historically a detected broken link added REPORT_THRESHOLD (5) to num_reports.
-- Preserve any reports above that first synthetic increment.
UPDATE content_links
SET is_dead = TRUE,
    num_reports = GREATEST(num_reports - 5, 0)
WHERE num_reports >= 5
  AND is_dead = FALSE;
