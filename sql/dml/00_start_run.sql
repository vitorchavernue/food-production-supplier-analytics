-- =====================================================================================
-- Opens a new run in the run log (first step of the Hop workflow)
-- Every row written by this run carries its run_id (the last one in etl.run_log).
-- =====================================================================================
INSERT INTO etl.run_log (started_at, status)
VALUES (LOCALTIMESTAMP, 'running');
