-- =====================================================================================
-- Staging: what Apache Hop extracted from the ERP in the current run
-- -------------------------------------------------------------------------------------
-- Hop truncates and fills these tables on every run (only the rows changed since the
-- watermark). Columns are already translated to English and a few values are prepared
-- in the extraction query (CNPJ digits, delay in minutes, date keys), so the warehouse
-- SQL only has to validate, conform keys and upsert.
-- source_updated_at = DT_ATUALIZACAO of the ERP row, used to advance the watermark.
-- =====================================================================================

CREATE TABLE stg.plant (
    plant_code          INTEGER,
    plant_name          VARCHAR(120),
    city                VARCHAR(120),
    state               CHAR(2),
    capacity_birds_day  INTEGER,
    source_updated_at   TIMESTAMP
);

CREATE TABLE stg.supplier (
    supplier_code      INTEGER,
    legal_name         VARCHAR(200),
    cnpj_typed         VARCHAR(40),   -- as typed in the ERP (with or without the mask)
    cnpj               VARCHAR(14),   -- digits only: the real identity of the farm
    city               VARCHAR(120),
    state              CHAR(2),
    plant_code         INTEGER,
    distance_km        INTEGER,
    integration_start  DATE,
    active_flag        CHAR(1),
    source_updated_at  TIMESTAMP
);

CREATE TABLE stg.product (
    product_code       INTEGER,
    description        VARCHAR(160),
    category           VARCHAR(40),
    standard_yield     NUMERIC(5, 4),
    source_updated_at  TIMESTAMP
);

CREATE TABLE stg.lot_receipt (
    lot_number          BIGINT,
    supplier_code       INTEGER,
    plant_code          INTEGER,
    scheduled_at        TIMESTAMP,
    arrived_at          TIMESTAMP,
    status              VARCHAR(10),
    delay_minutes       INTEGER,
    birds               INTEGER,
    live_weight_kg      NUMERIC(12, 2),
    doa_birds           INTEGER,
    condemned_kg        NUMERIC(10, 2),
    date_key            INTEGER,      -- arrival day (scheduled day for cancelled loads)
    source_updated_at   TIMESTAMP
);

CREATE TABLE stg.production_order (
    order_number       BIGINT,
    lot_number         BIGINT,
    plant_code         INTEGER,
    product_code       INTEGER,
    line_number        SMALLINT,
    started_at         TIMESTAMP,
    finished_at        TIMESTAMP,
    duration_minutes   INTEGER,
    planned_kg         NUMERIC(12, 2),
    produced_kg        NUMERIC(12, 2),
    date_key           INTEGER,
    source_updated_at  TIMESTAMP
);

CREATE TABLE stg.quality_inspection (
    inspection_number  BIGINT,
    order_number       BIGINT,
    inspected_at       TIMESTAMP,
    sample_size        INTEGER,
    defects            INTEGER,
    result             CHAR(1),
    date_key           INTEGER,
    source_updated_at  TIMESTAMP
);

CREATE TABLE stg.line_stop (
    stop_number        BIGINT,
    plant_code         INTEGER,
    line_number        SMALLINT,
    started_at         TIMESTAMP,
    finished_at        TIMESTAMP,
    minutes            INTEGER,
    reason_typed       VARCHAR(160),
    date_key           INTEGER,
    source_updated_at  TIMESTAMP
);

-- Totals of the WHOLE ERP tables, read at the end of the extraction.
-- The reconciliation compares them with the warehouse: every row and every kilo accounted for.
CREATE TABLE stg.source_totals (
    source_table  VARCHAR(40),
    row_count     BIGINT,
    total_kg      NUMERIC(18, 2)
);
