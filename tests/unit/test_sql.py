"""Rules the warehouse SQL must follow so that the Hop workflow can run it safely."""

import re

from food_dw.config import ROOT

DML = sorted((ROOT / "sql" / "dml").glob("*.sql"))


def code_only(sql: str) -> str:
    return "\n".join(line.split("--")[0] for line in sql.splitlines())


def test_comments_have_no_semicolons():
    """The Hop "SQL" action splits files by semicolon: one inside a comment would break a statement."""
    for path in DML:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "--" in line:
                assert ";" not in line.split("--", 1)[1], f"{path.name}: {line}"


def test_no_hop_variables_in_the_sql():
    """The SQL actions run with variable substitution off: a ${...} would be sent to the database as text."""
    for path in DML:
        assert "${" not in code_only(path.read_text(encoding="utf-8")), path.name


def test_every_fact_has_a_quality_check():
    checks = (ROOT / "sql" / "dml" / "30_quality_checks.sql").read_text(encoding="utf-8")
    for fact in ("fact_lot_receipt", "fact_production", "fact_quality_inspection", "fact_line_stop"):
        assert f"dw.{fact}" in checks


def test_every_load_writes_the_run_id():
    facts = code_only((ROOT / "sql" / "dml" / "20_facts.sql").read_text(encoding="utf-8"))
    inserts = re.findall(r"INSERT INTO dw\.fact_\w+", facts)
    assert len(inserts) == 4
    assert facts.count("(SELECT MAX(run_id) FROM etl.run_log)") >= 8  # every fact and every reject
