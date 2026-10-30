# ADR 0002 — Incremental load by watermark, upserts and a release gate

**Status:** accepted

## Context

Every ERP table has an update date (`DT_ATUALIZACAO`) maintained by the application. Reading the full history
every night is slow and heavy on the production database. Corrections are common: an order's produced weight or an
inspection result can be changed days later. The Qlik app must never show numbers from a load that did not reconcile.

## Decision

- **Watermark per ERP table** (`etl.watermark`): each extraction reads rows with `DT_ATUALIZACAO` after the last good
  watermark **minus 5 minutes**, so a transaction committed while the previous run was reading is not lost.
- **Idempotent load:** dimensions are upserted (`UPDATE ... FROM` for rows that exist, `INSERT ... WHERE NOT EXISTS`
  for new ones); the facts of the extracted rows are deleted and inserted again by their ERP number. Reading a row
  twice changes nothing and a correction replaces the old version.
- **Rejects instead of silent filters:** a row that fails a rule goes to `etl.rejected_record` with the reason and
  the kilos involved, and leaves it when the ERP fixes the row.
- **Release gate:** after the quality checks, the workflow counts the failed critical checks of the run. If any:
  the run is marked `failed`, **the watermarks do not move** and the workflow aborts. The next run reads the same
  changes again once the cause is fixed. A technical error marks the run `error` and also keeps the watermarks.
- **Only passed runs are exported** to Qlik, with a SHA-256 manifest of every file.

## Consequences

- A normal run reads one day of changes; a rerun with no ERP change loads nothing new and changes no number
  (tested in CI).
- Rows deleted in the ERP are not detected by an update-date watermark. The ERP cancels lots instead of deleting
  them (status `CANCELADO`); if hard deletes appear, a periodic full comparison of keys is the next step.
- The 5-minute overlap re-reads a few rows every run, which the upserts make harmless.
