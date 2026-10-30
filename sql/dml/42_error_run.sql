-- =====================================================================================
-- Closes a run that stopped with a technical error (extraction or load step failed).
-- Watermarks stay where they were.
-- =====================================================================================
UPDATE etl.run_log
SET status = 'error',
    finished_at = LOCALTIMESTAMP
WHERE run_id = (SELECT MAX(run_id) FROM etl.run_log);
