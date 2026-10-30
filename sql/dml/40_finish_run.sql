-- =====================================================================================
-- Closes a run that passed the quality gate (last step of the Hop workflow)
-- -------------------------------------------------------------------------------------
-- Only now the watermarks move forward: a failed run leaves them where they were,
-- so the next run reads the same changes again (nothing is skipped).
-- =====================================================================================

UPDATE etl.watermark
SET last_updated_at = s.max_updated
FROM (
    SELECT 'UNIDADE' AS source_table, MAX(source_updated_at) AS max_updated FROM stg.plant
    UNION ALL SELECT 'FORNECEDOR', MAX(source_updated_at) FROM stg.supplier
    UNION ALL SELECT 'PRODUTO', MAX(source_updated_at) FROM stg.product
    UNION ALL SELECT 'RECEBIMENTO_LOTE', MAX(source_updated_at) FROM stg.lot_receipt
    UNION ALL SELECT 'ORDEM_PRODUCAO', MAX(source_updated_at) FROM stg.production_order
    UNION ALL SELECT 'INSPECAO_QUALIDADE', MAX(source_updated_at) FROM stg.quality_inspection
    UNION ALL SELECT 'PARADA_LINHA', MAX(source_updated_at) FROM stg.line_stop
) AS s
WHERE watermark.source_table = s.source_table
  AND s.max_updated IS NOT NULL
  AND s.max_updated > watermark.last_updated_at;

UPDATE etl.run_log
SET status = 'passed',
    finished_at = LOCALTIMESTAMP
WHERE run_id = (SELECT MAX(run_id) FROM etl.run_log);
