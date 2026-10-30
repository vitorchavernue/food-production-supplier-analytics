"""Runs the Apache Hop workflow (hop-run, the Hop command line) and reports what the run did.

The workflow itself is the ETL: extraction, dimensions, facts, quality checks and release gate all live in
hop/ and sql/dml/. This module only prepares the Hop configuration of the run (project + environment with the
connection variables), starts hop-run and reads the result of the run from the warehouse (run log, quality
checks, rows loaded, rows rejected).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from food_dw.config import ROOT, settings
from food_dw.deploy import connect

PROJECT = "food_production"
ENVIRONMENT = "pipeline"
WORKFLOW = "${PROJECT_HOME}/workflows/load_warehouse.hwf"
REPORTS = ROOT / "reports"
FACTS = ["fact_lot_receipt", "fact_production", "fact_quality_inspection", "fact_line_stop"]


@dataclass
class RunResult:
    run_id: int
    status: str
    exit_code: int
    loaded: dict[str, int]
    rejected: dict[str, int]
    checks: list[tuple]

    @property
    def passed(self) -> bool:
        return self.status == "passed" and self.exit_code == 0


def hop_config() -> dict[str, str]:
    """A private Hop configuration folder with the project and an environment holding the connection variables.

    The connections in hop/metadata/rdbms only contain variables (${ORA_HOST}, ${DW_PASSWORD}...): the values
    live in an environment file created here, outside the repository, so no password is ever committed.
    """
    s = settings()
    folder = Path(tempfile.mkdtemp(prefix="hop_config_"))
    variables = {
        "ORA_HOST": s.ora_host,
        "ORA_PORT": str(s.ora_port),
        "ORA_SERVICE": s.ora_service,
        "ORA_USER": s.ora_user,
        "ORA_PASSWORD": s.ora_password,
        "DW_HOST": s.dw_host,
        "DW_PORT": str(s.dw_port),
        "DW_DATABASE": s.dw_database,
        "DW_USER": s.dw_user,
        "DW_PASSWORD": s.dw_password,
    }
    env_file = folder / "pipeline-environment.json"
    env_file.write_text(
        json.dumps({"variables": [{"name": k, "value": v, "description": ""} for k, v in variables.items()]}, indent=2),
        encoding="utf-8",
    )
    env = {**os.environ, "HOP_CONFIG_FOLDER": str(folder)}
    conf = str(Path(s.hop_home) / "hop-conf.sh")
    commands = [
        [conf, f"--project={PROJECT}", "--project-create", f"--project-home={ROOT / 'hop'}"],
        [
            conf,
            f"--environment={ENVIRONMENT}",
            "--environment-create",
            f"--environment-project={PROJECT}",
            "--environment-purpose=Testing",
            f"--environment-config-files={env_file}",
        ],
    ]
    for command in commands:
        proc = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"hop-conf failed: {' '.join(command[1:])}\n{proc.stdout}\n{proc.stderr}")
    return env


def run_job(label: str) -> RunResult:
    """Runs load_warehouse.hwf once and returns what happened (the hop-run log goes to reports/)."""
    REPORTS.mkdir(exist_ok=True)
    env = hop_config()
    command = [
        str(Path(settings().hop_home) / "hop-run.sh"),
        f"--project={PROJECT}",
        f"--environment={ENVIRONMENT}",
        f"--file={WORKFLOW}",
        "--runconfig=local",
        "--level=Basic",
    ]
    proc = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    (REPORTS / f"hop_{label}.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    return read_result(proc.returncode)


def read_result(exit_code: int) -> RunResult:
    conn = connect()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT run_id, status FROM etl.run_log ORDER BY run_id DESC LIMIT 1")
        run_id, status = cur.fetchone()
        loaded = {}
        for fact in FACTS:
            cur.execute(f"SELECT COUNT(*) FROM dw.{fact} WHERE run_id = %s", (run_id,))
            loaded[fact] = cur.fetchone()[0]
        cur.execute("SELECT source_table, COUNT(*) FROM etl.rejected_record WHERE run_id = %s GROUP BY 1 ORDER BY 1", (run_id,))
        rejected = dict(cur.fetchall())
        cur.execute(
            "SELECT check_name, severity, expected, actual, passed FROM dq.check_result "
            "WHERE run_id = %s ORDER BY severity, check_name",
            (run_id,),
        )
        checks = cur.fetchall()
    conn.close()
    return RunResult(run_id, status, exit_code, loaded, rejected, checks)


def report(result: RunResult, title: str) -> str:
    """Markdown summary of one run (used in the CI summary and in reports/)."""
    icon = "✅" if result.passed else "❌"
    lines = [f"### {icon} {title} — run {result.run_id}: {result.status} (hop-run exit code {result.exit_code})", ""]
    lines += ["| Fact | Rows loaded in this run |", "|---|---:|"]
    lines += [f"| {k} | {v:,} |" for k, v in result.loaded.items()]
    if result.rejected:
        lines += ["", "| ERP table | Rows rejected in this run |", "|---|---:|"]
        lines += [f"| {k} | {v:,} |" for k, v in result.rejected.items()]
    lines += ["", "| Check | Severity | Expected | Actual | Result |", "|---|---|---:|---:|---|"]
    for name, severity, expected, actual, passed in result.checks:
        exp = "" if expected is None else f"{expected:,.2f}"
        lines.append(f"| {name} | {severity} | {exp} | {actual:,.2f} | {'✅' if passed else '❌'} |")
    text = "\n".join(lines) + "\n"
    (REPORTS / f"run_{result.run_id}.md").write_text(text, encoding="utf-8")
    return text
