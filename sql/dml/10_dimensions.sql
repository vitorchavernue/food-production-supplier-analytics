-- =====================================================================================
-- Dimensions: calendar, plants, products and farms (run by the Hop workflow after the extraction)
-- -------------------------------------------------------------------------------------
-- Upserts are UPDATE ... FROM + INSERT ... WHERE NOT EXISTS, so running twice changes nothing.
-- Statements are separated by semicolons and comments never contain one, because the
-- Hop "SQL" action splits the file by semicolon.
-- =====================================================================================

-- Calendar 2024-2027, built once (the first run fills it, later runs skip it)
INSERT INTO dw.dim_date (date_key, full_date, year, quarter, month, month_name, year_month, day_of_week, is_weekend, is_summer)
SELECT
    CAST(TO_CHAR(d.full_date, 'YYYYMMDD') AS INTEGER),
    d.full_date,
    EXTRACT(YEAR FROM d.full_date),
    EXTRACT(QUARTER FROM d.full_date),
    EXTRACT(MONTH FROM d.full_date),
    TO_CHAR(d.full_date, 'Mon'),
    TO_CHAR(d.full_date, 'YYYY-MM'),
    EXTRACT(DOW FROM d.full_date),
    EXTRACT(DOW FROM d.full_date) IN (0, 6),
    EXTRACT(MONTH FROM d.full_date) IN (12, 1, 2, 3)
FROM (
    SELECT CAST(g AS DATE) AS full_date
    FROM generate_series(DATE '2024-01-01', DATE '2027-12-31', INTERVAL '1 day') AS g
) AS d
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_date);

-- Plants: update the ones that changed, insert the new ones
UPDATE dw.dim_plant
SET plant_name = s.plant_name,
    city = s.city,
    state = s.state,
    capacity_birds_day = s.capacity_birds_day
FROM stg.plant AS s
WHERE dim_plant.plant_code = s.plant_code;

INSERT INTO dw.dim_plant (plant_code, plant_name, city, state, region, capacity_birds_day)
SELECT s.plant_code, s.plant_name, s.city, s.state,
       CASE WHEN s.state IN ('SC', 'PR', 'RS') THEN 'South' ELSE 'Center-West' END,
       s.capacity_birds_day
FROM stg.plant AS s
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_plant AS p WHERE p.plant_code = s.plant_code)
ORDER BY s.plant_code;

-- Products
UPDATE dw.dim_product
SET description = s.description,
    category = s.category,
    standard_yield = s.standard_yield
FROM stg.product AS s
WHERE dim_product.product_code = s.product_code;

INSERT INTO dw.dim_product (product_code, description, category, standard_yield)
SELECT s.product_code, s.description, s.category, s.standard_yield
FROM stg.product AS s
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product AS p WHERE p.product_code = s.product_code)
ORDER BY s.product_code;

-- Farms are identified by the CNPJ digits, not by the ERP code: a farm registered twice
-- becomes one supplier. When both registrations changed, the original (lowest code) wins.
UPDATE dw.dim_supplier
SET legal_name = s.legal_name,
    city = s.city,
    state = s.state,
    plant_code = s.plant_code,
    distance_km = s.distance_km,
    distance_band = s.distance_band,
    integration_start = s.integration_start,
    is_active = s.is_active
FROM (
    SELECT cnpj, legal_name, city, state, plant_code, distance_km,
           CASE WHEN distance_km < 30 THEN 'under 30 km'
                WHEN distance_km < 60 THEN '30-60 km'
                WHEN distance_km < 100 THEN '60-100 km'
                ELSE 'over 100 km' END AS distance_band,
           integration_start,
           active_flag = 'A' AS is_active,
           ROW_NUMBER() OVER (PARTITION BY cnpj ORDER BY supplier_code) AS rn
    FROM stg.supplier
) AS s
WHERE s.rn = 1
  AND dim_supplier.cnpj = s.cnpj;

INSERT INTO dw.dim_supplier (cnpj, legal_name, city, state, plant_code, distance_km, distance_band, integration_start, is_active)
SELECT s.cnpj, s.legal_name, s.city, s.state, s.plant_code, s.distance_km,
       CASE WHEN s.distance_km < 30 THEN 'under 30 km'
            WHEN s.distance_km < 60 THEN '30-60 km'
            WHEN s.distance_km < 100 THEN '60-100 km'
            ELSE 'over 100 km' END,
       s.integration_start,
       s.active_flag = 'A'
FROM (
    SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.cnpj ORDER BY r.supplier_code) AS rn
    FROM stg.supplier AS r
) AS s
WHERE s.rn = 1
  AND NOT EXISTS (SELECT 1 FROM dw.dim_supplier AS d WHERE d.cnpj = s.cnpj)
ORDER BY s.supplier_code;

-- New rows are inserted in code order, so surrogate keys are the same on every rebuild

-- Every ERP code points to its farm (two codes can point to the same CNPJ)
DELETE FROM dw.supplier_code_map
USING stg.supplier AS s
WHERE supplier_code_map.supplier_code = s.supplier_code;

INSERT INTO dw.supplier_code_map (supplier_code, cnpj)
SELECT supplier_code, cnpj
FROM stg.supplier;
