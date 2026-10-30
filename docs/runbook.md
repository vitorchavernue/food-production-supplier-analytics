# Runbook — daily warehouse load

## Schedule

The Hop workflow `hop/workflows/load_warehouse.hwf` runs once a day after the plants close the previous day, for
example from cron on the Hop server:

```bash
hop-run.sh --project=food_production --environment=production \
           --file='${PROJECT_HOME}/workflows/load_warehouse.hwf' --runconfig=local --level=Basic
```

When it ends, `python -m food_dw export` writes the CSV files for Qlik and the Qlik reload task runs. The export
refuses to run when the last run did not pass.

## Hop project and environment

Register `hop/` as the project `food_production`. The connections (`hop/metadata/rdbms/erp.json` and `dw.json`) use
only variables; set them in an environment file kept **outside** the repository:

| Variable | Example | Meaning |
|---|---|---|
| `ORA_HOST`, `ORA_PORT`, `ORA_SERVICE` | `erp-db`, `1521`, `FREEPDB1` | Oracle ERP (service name) |
| `ORA_USER`, `ORA_PASSWORD` | `erp`, — | Read-only ERP user |
| `DW_HOST`, `DW_PORT`, `DW_DATABASE` | `dw-db`, `5432`, `warehouse` | PostgreSQL warehouse |
| `DW_USER`, `DW_PASSWORD` | `etl`, — | Warehouse user |

```bash
hop-conf.sh --project=food_production --project-create --project-home=/opt/food-production/hop
hop-conf.sh --environment=production --environment-create --environment-project=food_production \
            --environment-purpose=Production --environment-config-files=/etc/hop/food-production.json
```

## Checking the day

```sql
-- Last runs and their status: running, passed, failed (quality gate), error
SELECT run_id, started_at, finished_at, status FROM etl.run_log ORDER BY run_id DESC LIMIT 10;

-- Checks of the last run
SELECT check_name, severity, expected, actual, passed
FROM dq.check_result WHERE run_id = (SELECT MAX(run_id) FROM etl.run_log)
ORDER BY severity, check_name;

-- What has already been read from each ERP table
SELECT source_table, last_updated_at FROM etl.watermark ORDER BY source_table;
```

## When the workflow fails

| Status | Meaning | What to do |
|---|---|---|
| `error` | A technical problem stopped the workflow (database down, password expired, ERP column changed). Watermarks did not move; Qlik still shows the previous day. | Read the Hop log of the run, fix the cause, run the workflow again. It reads the same changes. |
| `failed` | Data was loaded but a **critical check failed**. Watermarks did not move and nothing was exported. | Look at the failed check. A difference in rows or kilos usually means someone changed the warehouse by hand or an ERP rule changed. After the fix, run again; if the warehouse was damaged, rebuild it (below). |

**Rebuild from the ERP:** set every watermark back to `1900-01-01` and run the workflow. Every row is read again and
the facts are replaced; the result is the same as a fresh load.

```sql
UPDATE etl.watermark SET last_updated_at = TIMESTAMP '1900-01-01';
```

## Rejected rows

```sql
SELECT source_table, reason, COUNT(*) AS rows_rejected, SUM(amount) AS kg
FROM etl.rejected_record
GROUP BY source_table, reason ORDER BY source_table;
```

The list goes to the ERP owners every morning (it is also the last sheet of the Qlik app):

| ERP table | Reason | Owner |
|---|---|---|
| `RECEBIMENTO_LOTE` | Zero or negative weight or bird count | Receiving (scale operators) |
| `ORDEM_PRODUCAO` | Produced weight above 130% of plan or not positive | Production planning |
| `INSPECAO_QUALIDADE` | Inspection of an order that does not exist | Quality |
| `PARADA_LINHA` | Stop that ends before it starts | Maintenance |

When the row is fixed in the ERP its update date changes, the next run reads it again, loads it and removes it from
the reject table.

## A new spelling of a stop reason

Stops whose text matches no rule are grouped as `Other`. Add a `WHEN` to the `CASE` in `sql/dml/20_facts.sql`
(section line stops) and rebuild the stops:

```sql
UPDATE etl.watermark SET last_updated_at = TIMESTAMP '1900-01-01' WHERE source_table = 'PARADA_LINHA';
```
