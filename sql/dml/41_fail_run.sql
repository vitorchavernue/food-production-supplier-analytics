-- =====================================================================================
-- Closes a run that did not pass the quality gate. Watermarks stay where they were.
-- =====================================================================================
UPDATE etl.run_log
SET status = 'failed',
    finished_at = LOCALTIMESTAMP
WHERE run_id = (SELECT MAX(run_id) FROM etl.run_log);
