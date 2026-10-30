-- =====================================================================================
-- Facts: validate the extracted rows, reject the invalid ones with a reason, upsert the rest
-- -------------------------------------------------------------------------------------
-- Pattern for every fact (idempotent: running twice gives the same result):
--   1. rows of this batch leave etl.rejected_record (they will be judged again)
--   2. invalid rows go to etl.rejected_record with the reason and the weight involved
--   3. rows of this batch leave the fact, valid rows are inserted again (update = delete + insert)
-- Order matters: lots before production orders (an order needs its lot),
-- production orders before inspections (an inspection needs its order).
-- The current run is the last one in etl.run_log (opened by the Hop workflow).
-- =====================================================================================

-- ---------------------------------------------------------------- 1. lots of live birds
DELETE FROM etl.rejected_record
USING stg.lot_receipt AS s
WHERE rejected_record.source_table = 'RECEBIMENTO_LOTE'
  AND rejected_record.source_key = s.lot_number;

INSERT INTO etl.rejected_record (run_id, source_table, source_key, reason, amount, rejected_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log), 'RECEBIMENTO_LOTE', s.lot_number,
       'Received lot with zero or negative live weight or bird count (scale typing error)',
       COALESCE(s.live_weight_kg, 0), LOCALTIMESTAMP
FROM stg.lot_receipt AS s
WHERE s.status = 'RECEBIDO'
  AND (s.live_weight_kg <= 0 OR s.birds <= 0);

DELETE FROM dw.fact_lot_receipt
USING stg.lot_receipt AS s
WHERE fact_lot_receipt.lot_number = s.lot_number;

INSERT INTO dw.fact_lot_receipt (lot_number, date_key, supplier_key, plant_key, status, scheduled_at, arrived_at,
                                 delay_minutes, is_on_time, birds, live_weight_kg, doa_birds, condemned_kg, run_id)
SELECT s.lot_number,
       s.date_key,
       COALESCE(f.supplier_key, -1),
       COALESCE(p.plant_key, -1),
       CASE WHEN s.status = 'CANCELADO' THEN 'cancelled' ELSE 'received' END,
       s.scheduled_at,
       s.arrived_at,
       s.delay_minutes,
       CASE WHEN s.status = 'CANCELADO' THEN NULL ELSE s.delay_minutes <= 60 END,
       s.birds,
       s.live_weight_kg,
       s.doa_birds,
       s.condemned_kg,
       (SELECT MAX(run_id) FROM etl.run_log)
FROM stg.lot_receipt AS s
LEFT JOIN dw.supplier_code_map AS m ON m.supplier_code = s.supplier_code
LEFT JOIN dw.dim_supplier AS f ON f.cnpj = m.cnpj
LEFT JOIN dw.dim_plant AS p ON p.plant_code = s.plant_code
WHERE NOT (s.status = 'RECEBIDO' AND (s.live_weight_kg <= 0 OR s.birds <= 0));

-- ---------------------------------------------------------------- 2. production orders
DELETE FROM etl.rejected_record
USING stg.production_order AS s
WHERE rejected_record.source_table = 'ORDEM_PRODUCAO'
  AND rejected_record.source_key = s.order_number;

-- An order cannot produce more than 130% of its plan (an extra digit typed) and needs a received lot
INSERT INTO etl.rejected_record (run_id, source_table, source_key, reason, amount, rejected_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log), 'ORDEM_PRODUCAO', s.order_number,
       CASE WHEN l.lot_number IS NULL THEN 'Production order of a lot that was not received'
            ELSE 'Produced weight above 130% of the planned weight or not positive' END,
       s.produced_kg, LOCALTIMESTAMP
FROM stg.production_order AS s
LEFT JOIN dw.fact_lot_receipt AS l ON l.lot_number = s.lot_number AND l.status = 'received'
WHERE l.lot_number IS NULL
   OR s.produced_kg > s.planned_kg * 1.3
   OR s.produced_kg <= 0;

DELETE FROM dw.fact_production
USING stg.production_order AS s
WHERE fact_production.order_number = s.order_number;

INSERT INTO dw.fact_production (order_number, lot_number, date_key, plant_key, product_key, supplier_key,
                                line_number, duration_minutes, planned_kg, produced_kg, run_id)
SELECT s.order_number,
       s.lot_number,
       s.date_key,
       COALESCE(p.plant_key, -1),
       COALESCE(d.product_key, -1),
       l.supplier_key,
       s.line_number,
       s.duration_minutes,
       s.planned_kg,
       s.produced_kg,
       (SELECT MAX(run_id) FROM etl.run_log)
FROM stg.production_order AS s
JOIN dw.fact_lot_receipt AS l ON l.lot_number = s.lot_number AND l.status = 'received'
LEFT JOIN dw.dim_plant AS p ON p.plant_code = s.plant_code
LEFT JOIN dw.dim_product AS d ON d.product_code = s.product_code
WHERE s.produced_kg <= s.planned_kg * 1.3
  AND s.produced_kg > 0;

-- ---------------------------------------------------------------- 3. quality inspections
DELETE FROM etl.rejected_record
USING stg.quality_inspection AS s
WHERE rejected_record.source_table = 'INSPECAO_QUALIDADE'
  AND rejected_record.source_key = s.inspection_number;

INSERT INTO etl.rejected_record (run_id, source_table, source_key, reason, amount, rejected_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log), 'INSPECAO_QUALIDADE', s.inspection_number,
       'Inspection of a production order that does not exist in the warehouse', 0, LOCALTIMESTAMP
FROM stg.quality_inspection AS s
WHERE NOT EXISTS (SELECT 1 FROM dw.fact_production AS o WHERE o.order_number = s.order_number);

DELETE FROM dw.fact_quality_inspection
USING stg.quality_inspection AS s
WHERE fact_quality_inspection.inspection_number = s.inspection_number;

INSERT INTO dw.fact_quality_inspection (inspection_number, order_number, date_key, plant_key, product_key,
                                        line_number, sample_size, defects, is_approved, run_id)
SELECT s.inspection_number,
       s.order_number,
       s.date_key,
       o.plant_key,
       o.product_key,
       o.line_number,
       s.sample_size,
       s.defects,
       s.result = 'A',
       (SELECT MAX(run_id) FROM etl.run_log)
FROM stg.quality_inspection AS s
JOIN dw.fact_production AS o ON o.order_number = s.order_number;

-- ---------------------------------------------------------------- 4. line stops
DELETE FROM etl.rejected_record
USING stg.line_stop AS s
WHERE rejected_record.source_table = 'PARADA_LINHA'
  AND rejected_record.source_key = s.stop_number;

INSERT INTO etl.rejected_record (run_id, source_table, source_key, reason, amount, rejected_at)
SELECT (SELECT MAX(run_id) FROM etl.run_log), 'PARADA_LINHA', s.stop_number,
       'Line stop ends before it starts', 0, LOCALTIMESTAMP
FROM stg.line_stop AS s
WHERE s.finished_at < s.started_at;

DELETE FROM dw.fact_line_stop
USING stg.line_stop AS s
WHERE fact_line_stop.stop_number = s.stop_number;

-- The reason is free text: group the many spellings into a few standard reasons
INSERT INTO dw.fact_line_stop (stop_number, date_key, plant_key, line_number, minutes, reason_group, run_id)
SELECT s.stop_number,
       s.date_key,
       COALESCE(p.plant_key, -1),
       s.line_number,
       s.minutes,
       CASE WHEN UPPER(s.reason_typed) LIKE '%CORRETIVA%' THEN 'Corrective maintenance'
            WHEN UPPER(s.reason_typed) LIKE '%PREVENTIVA%' THEN 'Preventive maintenance'
            WHEN UPPER(s.reason_typed) LIKE '%FALTA%' THEN 'No birds available'
            WHEN UPPER(s.reason_typed) LIKE '%LIMPEZA%' THEN 'Cleaning'
            WHEN UPPER(s.reason_typed) LIKE '%TROCA%' THEN 'Product changeover'
            WHEN UPPER(s.reason_typed) LIKE '%TRICA%' THEN 'Electrical failure'
            ELSE 'Other' END,
       (SELECT MAX(run_id) FROM etl.run_log)
FROM stg.line_stop AS s
LEFT JOIN dw.dim_plant AS p ON p.plant_code = s.plant_code
WHERE s.finished_at >= s.started_at;
