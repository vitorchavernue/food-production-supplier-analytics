"""Deploys the warehouse on PostgreSQL: schemas, control tables, staging, star schema and marts.

The DDL files in sql/dw run in name order on an empty database. Local runs and tests always start from
zero (the database is dropped and created again), so every run of the pipeline is reproducible.
"""

from __future__ import annotations

from pathlib import Path

import psycopg2

from food_dw.config import ROOT, settings

DDL_DIR = ROOT / "sql" / "dw"


def ddl_files() -> list[Path]:
    return sorted(DDL_DIR.glob("*.sql"))


def connect(database: str | None = None):
    s = settings()
    return psycopg2.connect(
        host=s.dw_host, port=s.dw_port, dbname=database or s.dw_database, user=s.dw_user, password=s.dw_password
    )


def recreate_database() -> None:
    """Drops and creates the warehouse database (local runs and tests start from zero)."""
    s = settings()
    conn = connect("postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{s.dw_database}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{s.dw_database}"')
    conn.close()


def deploy() -> None:
    """Creates every warehouse object in an empty PostgreSQL database."""
    recreate_database()
    conn = connect()
    with conn, conn.cursor() as cur:
        for path in ddl_files():
            cur.execute(path.read_text(encoding="utf-8"))
    conn.close()


if __name__ == "__main__":
    deploy()
    print("warehouse deployed")
