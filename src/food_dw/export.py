"""Exports the star schema to CSV files: the input of the Qlik Sense app (qlik/load_script.qvs).

Qlik Sense Desktop and Qlik Cloud cannot reach a database running inside CI, so the app loads these files.
They are deterministic (fixed seed, rows ordered by key) and CI checks that the committed files are exactly
what the pipeline produces (qlik/data/manifest.json holds their SHA-256): a change in the ETL that changes a
number in the dashboard cannot go unnoticed.
"""

from __future__ import annotations

import hashlib
import io
import json

from food_dw.config import ROOT
from food_dw.deploy import connect

OUT = ROOT / "qlik" / "data"
MANIFEST = OUT / "manifest.json"

# (schema, table) -> sort key (stable order, so the same data always gives the same file).
# Besides the star schema, the app shows the rejected ERP rows and the quality checks of the last run.
TABLES = {
    ("dw", "dim_date"): "date_key",
    ("dw", "dim_plant"): "plant_key",
    ("dw", "dim_supplier"): "supplier_key",
    ("dw", "dim_product"): "product_key",
    ("dw", "fact_lot_receipt"): "lot_number",
    ("dw", "fact_production"): "order_number",
    ("dw", "fact_quality_inspection"): "inspection_number",
    ("dw", "fact_line_stop"): "stop_number",
    ("etl", "rejected_record"): "source_table, source_key",
    ("dq", "check_result"): "severity, check_name",
}
# Technical columns left out: the run id and the clock time of the run (they change on every run)
SKIP = {"run_id", "rejected_at", "checked_at"}


def select_list(cur, schema: str, table: str) -> str:
    """Columns in table order; booleans become 1/0, which Qlik reads as numbers (easy to sum and count)."""
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table),
    )
    cols = []
    for name, kind in cur.fetchall():
        if name in SKIP:
            continue
        cols.append(f"CAST({name} AS INTEGER) AS {name}" if kind == "boolean" else name)
    return ", ".join(cols)


def table_csv(cur, schema: str, table: str, order_by: str) -> bytes:
    buffer = io.StringIO()
    # Quality checks: only the last run (the table keeps the history of every run)
    where = " WHERE run_id = (SELECT MAX(run_id) FROM etl.run_log)" if table == "check_result" else ""
    query = f"SELECT {select_list(cur, schema, table)} FROM {schema}.{table}{where} ORDER BY {order_by}"
    cur.copy_expert(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true)", buffer)
    return buffer.getvalue().encode("utf-8")


def export_all() -> dict[str, str]:
    """Writes every file and returns {file name: sha256}.

    Only the result of a run that passed the release gate goes to Qlik: if the last run failed a critical
    check (or stopped with an error), the warehouse may hold numbers that do not reconcile, so nothing is written.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = {}
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT run_id, status FROM etl.run_log ORDER BY run_id DESC LIMIT 1")
            run_id, status = cur.fetchone()
            if status != "passed":
                raise RuntimeError(f"Run {run_id} ended as '{status}': nothing is exported to Qlik")
            for (schema, table), key in TABLES.items():
                data = table_csv(cur, schema, table, key)
                (OUT / f"{table}.csv").write_bytes(data)
                hashes[f"{table}.csv"] = hashlib.sha256(data).hexdigest()
    finally:
        conn.close()
    return hashes


def write_manifest(hashes: dict[str, str]) -> None:
    MANIFEST.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def differences(hashes: dict[str, str]) -> list[str]:
    """Files whose content differs from the committed manifest (empty list = identical)."""
    committed = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    return sorted(k for k in set(committed) | set(hashes) if committed.get(k) != hashes.get(k))
