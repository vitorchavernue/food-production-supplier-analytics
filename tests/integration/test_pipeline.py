"""The whole pipeline against a real Oracle, a real PostgreSQL and Apache Hop (hop-run).

Runs in CI (see .github/workflows/ci.yml), in this order, on the same database:
    1. first load of 21 months of ERP history: every row and every kilo reconciled, defects rejected
    2. the exported files are exactly the committed ones (the input of the Qlik Sense app)
    3. one more ERP day plus corrections: incremental load updates instead of duplicating
    4. a rerun without ERP changes changes nothing
    5. a broken warehouse is caught by the release gate: run failed, watermarks not moved
"""

import os

import pytest

from food_dw import deploy, export, oracle_load, run

pytestmark = pytest.mark.skipif(not os.getenv("HOP_HOME"), reason="needs Oracle, PostgreSQL and Apache Hop (CI)")


def query(sql: str, params=None):
    conn = deploy.connect()
    with conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
    conn.close()
    return rows


def oracle_count(sql: str) -> float:
    conn = oracle_load.connect()
    with conn.cursor() as cur:
        cur.execute(sql)
        value = cur.fetchone()[0]
    conn.close()
    return value


def totals() -> dict:
    return dict(
        query("SELECT 'lots', COUNT(*) FROM dw.fact_lot_receipt UNION ALL SELECT 'orders', COUNT(*) FROM dw.fact_production")
    )


@pytest.fixture(scope="module")
def erp():
    deploy.deploy()
    return oracle_load.load_history()


@pytest.fixture(scope="module")
def first_load(erp):
    result = run.run_job("first_load")
    print(run.report(result, "First load (01/2025 - 09/2026)"))
    return result


def test_first_load_passes_the_gate(first_load):
    assert first_load.passed, first_load.checks
    assert all(c[4] for c in first_load.checks if c[1] == "critical")


def test_every_erp_lot_is_loaded_or_rejected(first_load):
    erp_lots = oracle_count("SELECT COUNT(*) FROM RECEBIMENTO_LOTE")
    loaded = query("SELECT COUNT(*) FROM dw.fact_lot_receipt")[0][0]
    rejected = query("SELECT COUNT(*) FROM etl.rejected_record WHERE source_table = 'RECEBIMENTO_LOTE'")[0][0]
    assert loaded + rejected == erp_lots
    bad_weight = oracle_count("SELECT COUNT(*) FROM RECEBIMENTO_LOTE WHERE STATUS = 'RECEBIDO' AND PESO_VIVO_KG <= 0")
    assert rejected == bad_weight


def test_live_weight_matches_the_erp_to_the_cent(first_load):
    erp_kg = oracle_count("SELECT SUM(PESO_VIVO_KG) FROM RECEBIMENTO_LOTE WHERE STATUS = 'RECEBIDO' AND PESO_VIVO_KG > 0")
    dw_kg = query("SELECT SUM(live_weight_kg) FROM dw.fact_lot_receipt")[0][0]
    assert float(dw_kg) == pytest.approx(float(erp_kg), abs=0.005)


def test_duplicated_farms_are_merged(first_load):
    erp_codes = oracle_count("SELECT COUNT(*) FROM FORNECEDOR")
    farms = oracle_count("SELECT COUNT(DISTINCT REGEXP_REPLACE(CNPJ, '[^0-9]', '')) FROM FORNECEDOR")
    assert erp_codes - farms == 4
    assert query("SELECT COUNT(*) FROM dw.dim_supplier WHERE supplier_key > 0")[0][0] == farms
    assert query("SELECT COUNT(*) FROM dw.supplier_code_map")[0][0] == erp_codes


def test_stop_reasons_are_standardized(first_load):
    groups = {r[0] for r in query("SELECT DISTINCT reason_group FROM dw.fact_line_stop")}
    assert "Other" not in groups and len(groups) == 6


def test_exported_files_are_the_committed_ones(first_load):
    assert export.differences(export.export_all()) == []


@pytest.fixture(scope="module")
def incremental(erp, first_load):
    data, state = erp
    before = totals()
    new = oracle_load.load_next_day(data, state)
    result = run.run_job("incremental")
    print(run.report(result, "Incremental load (one more ERP day + corrections)"))
    return result, before, new


def test_incremental_load_adds_only_the_new_day(incremental):
    result, before, new = incremental
    assert result.passed, result.checks
    after = totals()
    valid_lots = [r for r in new.recebimento_lote if not (r[9] == "RECEBIDO" and r[6] <= 0)]
    assert after["lots"] == before["lots"] + len(valid_lots)
    assert after["orders"] - before["orders"] == len(new.ordem_producao) - sum(1 for o in new.ordem_producao if o[8] > 1.3 * o[7])


def test_incremental_load_applies_corrections(incremental):
    erp_kg = oracle_count("SELECT SUM(PESO_VIVO_KG) FROM RECEBIMENTO_LOTE WHERE STATUS = 'RECEBIDO' AND PESO_VIVO_KG > 0")
    assert float(query("SELECT SUM(live_weight_kg) FROM dw.fact_lot_receipt")[0][0]) == pytest.approx(float(erp_kg), abs=0.005)
    assert query("SELECT COUNT(*) FROM dw.dim_supplier WHERE is_active = FALSE AND supplier_key > 0")[0][0] == 1


def test_rerun_without_changes_changes_nothing(incremental):
    before = totals()
    kg = query("SELECT SUM(live_weight_kg) FROM dw.fact_lot_receipt")[0][0]
    result = run.run_job("rerun")
    print(run.report(result, "Rerun without ERP changes"))
    assert result.passed
    assert totals() == before
    assert query("SELECT SUM(live_weight_kg) FROM dw.fact_lot_receipt")[0][0] == kg


def test_release_gate_stops_a_broken_load(incremental):
    watermarks = query("SELECT source_table, last_updated_at FROM etl.watermark ORDER BY 1")
    query("DELETE FROM dw.fact_lot_receipt WHERE lot_number = (SELECT MIN(lot_number) FROM dw.fact_lot_receipt)")
    result = run.run_job("broken")
    print(run.report(result, "Broken warehouse (one lot deleted on purpose)"))
    assert result.status == "failed" and result.exit_code != 0
    failed = [c[0] for c in result.checks if c[1] == "critical" and not c[4]]
    assert failed == [
        "Every ERP row is in the warehouse or rejected: RECEBIMENTO_LOTE",
        "Every kilo is in the warehouse or rejected: RECEBIMENTO_LOTE",
    ]
    assert query("SELECT source_table, last_updated_at FROM etl.watermark ORDER BY 1") == watermarks
    # Nothing from a failed run reaches Qlik
    with pytest.raises(RuntimeError, match="nothing is exported"):
        export.export_all()
