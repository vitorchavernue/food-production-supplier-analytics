"""Connection settings, read from environment variables (defaults = a local setup).

No password is written in the code: the CI pipeline passes throwaway values through the
environment, and in a real deployment they come from the scheduler's secret store.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    # Source: the ERP on Oracle
    ora_host: str = os.getenv("ORA_HOST", "localhost")
    ora_port: int = int(os.getenv("ORA_PORT", "1521"))
    ora_service: str = os.getenv("ORA_SERVICE", "FREEPDB1")
    ora_user: str = os.getenv("ORA_USER", "erp")
    ora_password: str = os.getenv("ORA_PASSWORD", "")
    # Target: the data warehouse on PostgreSQL
    dw_host: str = os.getenv("DW_HOST", "localhost")
    dw_port: int = int(os.getenv("DW_PORT", "5432"))
    dw_database: str = os.getenv("DW_DATABASE", "warehouse")
    dw_user: str = os.getenv("DW_USER", "postgres")
    dw_password: str = os.getenv("DW_PASSWORD", "")
    # Apache Hop (folder with hop-run.sh)
    hop_home: str = os.getenv("HOP_HOME", str(ROOT / "tools" / "hop"))


def settings() -> Settings:
    return Settings()
