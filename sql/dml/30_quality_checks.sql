-- =====================================================================================
-- Data quality checks: the release gate of every run
-- -------------------------------------------------------------------------------------
-- Critical checks compare the WHOLE warehouse with the totals of the WHOLE ERP tables
-- (read by Hop at the end of the extraction): every ERP row must be either in a fact
-- or in etl.rejected_record with a reason, and every kilo must be accounted for.
-- If any critical check fails, the Hop workflow marks the run as failed and does not
-- advance the watermarks, so the same changes are read again in the next run.
-- Info checks only record facts worth knowing about the data.
-- =====================================================================================

-- Rows: ERP = warehouse + rejected, per table
INSERT INTO dq.check_result (run_id, check_name, severity, expected, actual, passed, checked_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log),
       'Every ERP row is in the warehouse or rejected: ' || t.source_table,
       'critical',
       t.row_count,
       w.loaded + COALESCE(r.rejected, 0),
       t.row_count = w.loaded + COALESCE(r.rejected, 0),
       LOCALTIMESTAMP
FROM stg.source_totals AS t
JOIN (
    SELECT 'RECEBIMENTO_LOTE' AS source_table, COUNT(*) AS loaded FROM dw.fact_lot_receipt
    UNION ALL SELECT 'ORDEM_PRODUCAO', COUNT(*) FROM dw.fact_production
    UNION ALL SELECT 'INSPECAO_QUALIDADE', COUNT(*) FROM dw.fact_quality_inspection
    UNION ALL SELECT 'PARADA_LINHA', COUNT(*) FROM dw.fact_line_stop
) AS w ON w.source_table = t.source_table
LEFT JOIN (
    SELECT source_table, COUNT(*) AS rejected FROM etl.rejected_record GROUP BY source_table
) AS r ON r.source_table = t.source_table;

-- Kilos: live weight received and weight produced, ERP = warehouse + rejected
INSERT INTO dq.check_result (run_id, check_name, severity, expected, actual, passed, checked_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log),
       'Every kilo is in the warehouse or rejected: ' || t.source_table,
       'critical',
       t.total_kg,
       w.kg + COALESCE(r.kg, 0),
       t.total_kg = w.kg + COALESCE(r.kg, 0),
       LOCALTIMESTAMP
FROM stg.source_totals AS t
JOIN (
    SELECT 'RECEBIMENTO_LOTE' AS source_table, COALESCE(SUM(live_weight_kg), 0) AS kg FROM dw.fact_lot_receipt
    UNION ALL SELECT 'ORDEM_PRODUCAO', COALESCE(SUM(produced_kg), 0) FROM dw.fact_production
) AS w ON w.source_table = t.source_table
LEFT JOIN (
    SELECT source_table, SUM(amount) AS kg FROM etl.rejected_record GROUP BY source_table
) AS r ON r.source_table = t.source_table;

-- Every fact row points to a real plant, farm and product (no Unknown members)
INSERT INTO dq.check_result (run_id, check_name, severity, expected, actual, passed, checked_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log),
       'Facts pointing to an unknown plant, farm or product',
       'critical', 0, n, n = 0, LOCALTIMESTAMP
FROM (
    SELECT (SELECT COUNT(*) FROM dw.fact_lot_receipt WHERE supplier_key = -1 OR plant_key = -1)
         + (SELECT COUNT(*) FROM dw.fact_production WHERE supplier_key = -1 OR plant_key = -1 OR product_key = -1)
         + (SELECT COUNT(*) FROM dw.fact_line_stop WHERE plant_key = -1) AS n
) AS x;

-- One farm per CNPJ in the supplier dimension (duplicated registrations merged)
INSERT INTO dq.check_result (run_id, check_name, severity, expected, actual, passed, checked_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log),
       'Farms with more than one row in the supplier dimension',
       'critical', 0, n, n = 0, LOCALTIMESTAMP
FROM (
    SELECT COUNT(*) AS n
    FROM (SELECT cnpj FROM dw.dim_supplier GROUP BY cnpj HAVING COUNT(*) > 1) AS d
) AS x;

-- Info: ERP codes merged into another farm (the same CNPJ registered twice)
INSERT INTO dq.check_result (run_id, check_name, severity, expected, actual, passed, checked_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log),
       'ERP codes merged into an existing farm (same CNPJ registered twice)',
       'info', NULL, COUNT(*) - COUNT(DISTINCT cnpj), TRUE, LOCALTIMESTAMP
FROM dw.supplier_code_map;

-- Info: lots whose carcass yield (produced / live weight) is outside the usual 65% to 80%
INSERT INTO dq.check_result (run_id, check_name, severity, expected, actual, passed, checked_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log),
       'Lots with yield outside 65%-80% of the live weight',
       'info', NULL, COUNT(*), TRUE, LOCALTIMESTAMP
FROM (
    SELECT l.lot_number
    FROM dw.fact_lot_receipt AS l
    JOIN dw.fact_production AS o ON o.lot_number = l.lot_number
    WHERE l.status = 'received'
    GROUP BY l.lot_number, l.live_weight_kg
    HAVING SUM(o.produced_kg) < l.live_weight_kg * 0.65
        OR SUM(o.produced_kg) > l.live_weight_kg * 0.80
) AS y;

-- Info: rejected rows waiting for a fix in the ERP
INSERT INTO dq.check_result (run_id, check_name, severity, expected, actual, passed, checked_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log),
       'Rejected rows waiting for a fix in the ERP: ' || source_table,
       'info', NULL, COUNT(*), TRUE, LOCALTIMESTAMP
FROM etl.rejected_record
GROUP BY source_table;
