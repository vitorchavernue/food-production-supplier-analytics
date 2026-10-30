"""Creates the ERP tables on Oracle and fills them with the synthetic history (and later changes).

Only for tests and demos: in a real project the ERP already exists and the warehouse only reads it.
"""

from __future__ import annotations

import re

from food_dw import seed
from food_dw.config import ROOT, settings

# Column types of each table (N = number, S = text, D = date), in the order of oracle/01_erp_schema.sql.
# Declared up front because some columns start with empty values (cancelled lots) and the driver
# must not guess the type from the first row.
COLUMNS = {
    "UNIDADE": "NSSSND",
    "FORNECEDOR": "NSSSSNNDSD",
    "PRODUTO": "NSSND",
    "RECEBIMENTO_LOTE": "NNNDDNNNNSD",
    "ORDEM_PRODUCAO": "NNNNNDDNND",
    "INSPECAO_QUALIDADE": "NNDNNSD",
    "PARADA_LINHA": "NNNDDSD",
}


def connect():
    import oracledb  # thin mode: no Oracle client installation needed

    s = settings()
    return oracledb.connect(user=s.ora_user, password=s.ora_password, dsn=f"{s.ora_host}:{s.ora_port}/{s.ora_service}")


def statements(sql: str) -> list[str]:
    """Splits the DDL file into statements (Oracle drivers run one statement at a time, without ';')."""
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)  # block comments
    return [s.strip() for s in sql.split(";") if s.strip()]


def create_schema(conn) -> None:
    with conn.cursor() as cur:
        for table in COLUMNS:
            cur.execute(
                f"BEGIN EXECUTE IMMEDIATE 'DROP TABLE {table} PURGE'; "
                "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"
            )
        for stmt in statements((ROOT / "oracle" / "01_erp_schema.sql").read_text(encoding="utf-8")):
            cur.execute(stmt)


def insert(conn, data: seed.ErpData) -> dict[str, int]:
    import oracledb

    types = {"N": oracledb.DB_TYPE_NUMBER, "S": 200, "D": oracledb.DB_TYPE_DATE}
    counts = {}
    with conn.cursor() as cur:
        for table, rows in data.tables().items():
            if not rows:
                continue
            kinds = COLUMNS[table]
            cur.setinputsizes(*[types[k] for k in kinds])
            binds = ", ".join(f":{i + 1}" for i in range(len(kinds)))
            cur.executemany(f"INSERT INTO {table} VALUES ({binds})", rows)
            counts[table] = len(rows)
    conn.commit()
    return counts


def apply_updates(conn, updates: list[tuple]) -> None:
    with conn.cursor() as cur:
        for table, key_column, key, changes in updates:
            assignments = ", ".join(f"{column} = :{column}" for column in changes)
            cur.execute(f"UPDATE {table} SET {assignments} WHERE {key_column} = :k", {**changes, "k": key})
    conn.commit()


def load_history() -> tuple[seed.ErpData, dict]:
    """Recreates the ERP with the full history (01/2025 to 09/2026)."""
    data, state = seed.generate()
    conn = connect()
    create_schema(conn)
    insert(conn, data)
    conn.close()
    return data, state


def load_next_day(data: seed.ErpData, state: dict) -> seed.ErpData:
    """One more day of business plus corrections to old records (input of the incremental load)."""
    new, updates = seed.next_day_changes(state, data)
    conn = connect()
    insert(conn, new)
    apply_updates(conn, updates)
    conn.close()
    return new
