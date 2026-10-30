"""The synthetic ERP must be identical on every run and carry the stories and defects the project relies on."""

from datetime import date

from food_dw import seed
from food_dw.oracle_load import COLUMNS


def test_same_data_on_every_run():
    first, _ = seed.generate(date(2025, 1, 1), date(2025, 1, 10))
    second, _ = seed.generate(date(2025, 1, 1), date(2025, 1, 10))
    assert first.tables() == second.tables()


def test_rows_match_the_oracle_columns():
    data, _ = seed.generate(date(2025, 1, 1), date(2025, 1, 5))
    for table, rows in data.tables().items():
        assert all(len(row) == len(COLUMNS[table]) for row in rows), table


def test_cnpj_check_digits_are_valid():
    import random

    cnpj = seed.cnpj_digits(random.Random(1))
    assert len(cnpj) == 14 and cnpj.isdigit()
    assert seed.masked(cnpj).count(".") == 2 and "/" in seed.masked(cnpj)


def test_planted_defects_exist():
    data, _ = seed.generate()
    lots = data.recebimento_lote
    assert any(r[9] == "CANCELADO" and r[4] is None for r in lots)
    assert any(r[9] == "RECEBIDO" and r[6] <= 0 for r in lots)
    assert any(o[8] > 1.3 * o[7] for o in data.ordem_producao)
    assert any(s[4] < s[3] for s in data.parada_linha)
    order_numbers = {o[0] for o in data.ordem_producao}
    assert any(i[1] not in order_numbers for i in data.inspecao_qualidade)
    # farms registered twice: same CNPJ digits under two codes
    digits = [r[2].replace(".", "").replace("/", "").replace("-", "") for r in data.fornecedor]
    assert len(digits) - len(set(digits)) == 4


def test_summer_raises_dead_on_arrival():
    data, _ = seed.generate()
    received = [r for r in data.recebimento_lote if r[9] == "RECEBIDO" and r[6] > 0]
    summer = [r for r in received if r[4].month in (1, 2)]
    winter = [r for r in received if r[4].month in (6, 7)]
    rate = lambda rows: sum(r[7] for r in rows) / sum(r[5] for r in rows)  # noqa: E731
    assert rate(summer) > 1.5 * rate(winter)


def test_next_day_brings_new_rows_and_corrections():
    data, state = seed.generate(date(2025, 1, 1), date(2025, 1, 31))
    new, updates = seed.next_day_changes(state, data)
    assert new.recebimento_lote and new.ordem_producao
    assert {u[0] for u in updates} == {"FORNECEDOR", "RECEBIMENTO_LOTE"}
