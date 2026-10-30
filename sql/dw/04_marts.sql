-- =====================================================================================
-- Marts: business views on top of the star schema 
-- -------------------------------------------------------------------------------------
-- Rates are returned as numerators and denominators too, so a dashboard can add them up
-- correctly for any selection (a rate of rates would be wrong).
-- =====================================================================================

-- Farm scorecard per month: welfare (DOA), punctuality, losses and the yield of its birds
CREATE VIEW mart.supplier_monthly AS
SELECT d.year_month,
       s.supplier_key,
       s.legal_name,
       s.city,
       s.distance_band,
       p.plant_name,
       COUNT(*) AS lots,
       SUM(l.birds) AS birds,
       SUM(l.live_weight_kg) AS live_weight_kg,
       SUM(l.doa_birds) AS doa_birds,
       ROUND(100.0 * SUM(l.doa_birds) / NULLIF(SUM(l.birds), 0), 3) AS doa_pct,
       SUM(CASE WHEN l.is_on_time THEN 1 ELSE 0 END) AS lots_on_time,
       ROUND(100.0 * SUM(CASE WHEN l.is_on_time THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,
       SUM(l.condemned_kg) AS condemned_kg,
       SUM(y.produced_kg) AS produced_kg,
       ROUND(100.0 * SUM(y.produced_kg) / NULLIF(SUM(l.live_weight_kg), 0), 2) AS yield_pct
FROM dw.fact_lot_receipt AS l
JOIN dw.dim_date AS d ON d.date_key = l.date_key
JOIN dw.dim_supplier AS s ON s.supplier_key = l.supplier_key
JOIN dw.dim_plant AS p ON p.plant_key = l.plant_key
LEFT JOIN (
    SELECT lot_number, SUM(produced_kg) AS produced_kg FROM dw.fact_production GROUP BY lot_number
) AS y ON y.lot_number = l.lot_number
WHERE l.status = 'received'
GROUP BY d.year_month, s.supplier_key, s.legal_name, s.city, s.distance_band, p.plant_name;

-- Plant and line performance per month: output against plan, quality and stops
CREATE VIEW mart.plant_line_monthly AS
SELECT d.year_month,
       p.plant_name,
       o.line_number,
       SUM(o.planned_kg) AS planned_kg,
       SUM(o.produced_kg) AS produced_kg,
       ROUND(100.0 * SUM(o.produced_kg) / NULLIF(SUM(o.planned_kg), 0), 2) AS output_vs_plan_pct,
       MAX(q.inspections) AS inspections,
       MAX(q.approved) AS inspections_approved,
       MAX(st.stops) AS stops,
       MAX(st.stop_minutes) AS stop_minutes
FROM dw.fact_production AS o
JOIN dw.dim_date AS d ON d.date_key = o.date_key
JOIN dw.dim_plant AS p ON p.plant_key = o.plant_key
LEFT JOIN (
    SELECT dd.year_month, qi.plant_key, qi.line_number,
           COUNT(*) AS inspections,
           SUM(CASE WHEN qi.is_approved THEN 1 ELSE 0 END) AS approved
    FROM dw.fact_quality_inspection AS qi
    JOIN dw.dim_date AS dd ON dd.date_key = qi.date_key
    GROUP BY dd.year_month, qi.plant_key, qi.line_number
) AS q ON q.year_month = d.year_month AND q.plant_key = o.plant_key AND q.line_number = o.line_number
LEFT JOIN (
    SELECT dd.year_month, ls.plant_key, ls.line_number,
           COUNT(*) AS stops,
           SUM(ls.minutes) AS stop_minutes
    FROM dw.fact_line_stop AS ls
    JOIN dw.dim_date AS dd ON dd.date_key = ls.date_key
    GROUP BY dd.year_month, ls.plant_key, ls.line_number
) AS st ON st.year_month = d.year_month AND st.plant_key = o.plant_key AND st.line_number = o.line_number
GROUP BY d.year_month, p.plant_name, o.line_number;
