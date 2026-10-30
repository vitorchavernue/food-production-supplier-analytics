"""Synthetic ERP data for a poultry processing company (fixed random seed, so every run is identical).

The data imitates 21 months of a real operation: 4 plants, 120 integrated farms, live-bird lots, production
orders, quality inspections and line stops. It also carries the stories the dashboards tell, and the defects
a legacy ERP accumulates over the years, so the warehouse has something real to clean and to reconcile:

Stories (what the analysis should find)
    * dead-on-arrival (DOA) rises in the summer (December to March) and with the distance to the plant
    * two farms have chronic welfare problems (DOA 2 to 5 times the average)
    * Rio Verde line 2 loses yield from March 2026 (worn equipment) and stops much more often

Planted defects (what the data quality layer must catch)
    * CNPJ typed with and without the mask; 4 farms registered twice under two codes
    * received lots with zero or negative weight (typing errors) -> rejected with a reason
    * cancelled lots (no arrival, no weights) -> kept out of the facts, but counted in the reconciliation
    * production orders producing more than 130% of the planned weight -> rejected
    * inspections pointing to production orders that do not exist (orphans) -> rejected
    * line stops ending before they start -> rejected
    * stop reasons typed in different ways ("Manutenção corretiva", "MANUTENCAO CORRETIVA") -> standardized
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

SEED = 2026
START = date(2025, 1, 1)  # first day of history
END = date(2026, 9, 30)  # last day of the first (full) load
NEXT_DAY = date(2026, 10, 1)  # one more day of business, used to test the incremental load

# Plants: code, name, city, state, birds per day
PLANTS = [
    (1, "Unidade Chapecó", "Chapecó", "SC", 160_000),
    (2, "Unidade Toledo", "Toledo", "PR", 140_000),
    (3, "Unidade Rio Verde", "Rio Verde", "GO", 150_000),
    (4, "Unidade Dourados", "Dourados", "MS", 120_000),
]

# Cities around each plant where the integrated farms are (city, distance range in km)
FARM_CITIES = {
    1: [("Chapecó", 5, 30), ("Xaxim", 20, 40), ("Seara", 35, 60), ("Concórdia", 70, 110), ("Pinhalzinho", 45, 75)],
    2: [("Toledo", 5, 30), ("Marechal Cândido Rondon", 30, 55), ("Palotina", 50, 80), ("Cascavel", 45, 70)],
    3: [("Rio Verde", 5, 35), ("Montividiu", 40, 70), ("Santa Helena de Goiás", 35, 60), ("Jataí", 90, 140)],
    4: [("Dourados", 5, 30), ("Itaporã", 15, 35), ("Ponta Porã", 100, 130), ("Rio Brilhante", 50, 80)],
}
STATE_OF_PLANT = {1: "SC", 2: "PR", 3: "GO", 4: "MS"}

# Products: code, description, category, expected share of the live weight
PRODUCTS = [
    (1001, "Frango inteiro congelado", "INTEIRO", 0.2600),
    (1002, "Peito com osso", "CORTE", 0.1200),
    (1003, "Filé de peito", "CORTE", 0.1000),
    (1004, "Coxa e sobrecoxa", "CORTE", 0.1000),
    (1005, "Asa", "CORTE", 0.0500),
    (1006, "Miúdos (coração, fígado, moela)", "MIUDO", 0.0450),
    (1007, "Linguiça de frango", "PROCESSADO", 0.0350),
    (1008, "Empanado de frango", "PROCESSADO", 0.0250),
]

# How operators type the stop reasons (same reason, several spellings)
STOP_REASONS = [
    ["Manutenção corretiva", "MANUTENCAO CORRETIVA", "manutencao corretiva"],
    ["Manutenção preventiva", "MANUTENCAO PREVENTIVA"],
    ["Falta de aves", "FALTA DE AVES", "Falta aves"],
    ["Limpeza e higienização", "LIMPEZA"],
    ["Troca de produto", "TROCA DE PRODUTO"],
    ["Falha elétrica", "FALHA ELETRICA", "falha eletrica"],
]

COMPANY_SUFFIXES = ["Ltda", "Ltda.", "LTDA", "ME", "EIRELI"]
FARM_WORDS = ["Granja", "Sítio", "Avícola", "Fazenda"]
FARM_NAMES = [
    "Boa Vista",
    "Santa Clara",
    "São José",
    "Três Irmãos",
    "Bela Vista",
    "Primavera",
    "Esperança",
    "Santa Rita",
    "Recanto",
    "Vale Verde",
    "Pinheiros",
    "Do Sol",
    "Nova Era",
    "Ouro Verde",
    "Água Limpa",
    "Bom Jesus",
    "Santo Antônio",
    "Cachoeira",
    "Alvorada",
    "Paraíso",
]


@dataclass
class ErpData:
    """Rows of every ERP table, in the column order of oracle/01_erp_schema.sql."""

    unidade: list[tuple] = field(default_factory=list)
    fornecedor: list[tuple] = field(default_factory=list)
    produto: list[tuple] = field(default_factory=list)
    recebimento_lote: list[tuple] = field(default_factory=list)
    ordem_producao: list[tuple] = field(default_factory=list)
    inspecao_qualidade: list[tuple] = field(default_factory=list)
    parada_linha: list[tuple] = field(default_factory=list)

    def tables(self) -> dict[str, list[tuple]]:
        return {
            "UNIDADE": self.unidade,
            "FORNECEDOR": self.fornecedor,
            "PRODUTO": self.produto,
            "RECEBIMENTO_LOTE": self.recebimento_lote,
            "ORDEM_PRODUCAO": self.ordem_producao,
            "INSPECAO_QUALIDADE": self.inspecao_qualidade,
            "PARADA_LINHA": self.parada_linha,
        }


def cnpj_digits(rng: random.Random) -> str:
    """A valid CNPJ (14 digits with the two check digits), so it looks like a real one."""
    base = [rng.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    for weights in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        total = sum(d * w for d, w in zip(base, weights, strict=False))
        rest = total % 11
        base.append(0 if rest < 2 else 11 - rest)
    return "".join(map(str, base))


def masked(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def at(day: date, hour: float) -> datetime:
    """Timestamp of a day plus a fractional hour, rounded to the minute (Oracle DATE has no milliseconds)."""
    return datetime(day.year, day.month, day.day) + timedelta(minutes=round(hour * 60))


def summer_factor(day: date) -> float:
    """Heat stress: Brazilian summer (December to March) raises the deaths during transport."""
    return {12: 1.8, 1: 2.0, 2: 1.9, 3: 1.4, 11: 1.2}.get(day.month, 1.0)


def build_dimensions(rng: random.Random, data: ErpData) -> dict:
    """Plants, products and farms. Returns the farms grouped by plant for the daily simulation."""
    registered = datetime(2018, 1, 1)
    data.unidade = [(*p, registered) for p in PLANTS]
    data.produto = [(*p, registered) for p in PRODUCTS]

    farms_by_plant: dict[int, list[dict]] = {p[0]: [] for p in PLANTS}
    code = 100_000
    for plant_code in farms_by_plant:
        for i in range(30):
            code += 1
            city, near, far = rng.choice(FARM_CITIES[plant_code])
            cnpj = cnpj_digits(rng)
            name = f"{rng.choice(FARM_WORDS)} {rng.choice(FARM_NAMES)} {rng.choice(COMPANY_SUFFIXES)}"
            farm = {
                "code": code,
                "name": name,
                "cnpj": cnpj,
                "city": city,
                "uf": STATE_OF_PLANT[plant_code],
                "plant": plant_code,
                "distance": rng.randint(near, far),
                "since": datetime(rng.randint(2012, 2023), rng.randint(1, 12), 1),
                "welfare": 1.0,
                "punctuality": rng.uniform(0.6, 1.4),
                "codes": [code],
            }
            # Two farms with chronic welfare problems (crowded trucks, long waits): the DOA outliers
            if (plant_code, i) in {(2, 7), (3, 12)}:
                farm["welfare"] = 4.0
            farms_by_plant[plant_code].append(farm)

    rows = []
    duplicates = {(1, 3), (2, 11), (3, 5), (4, 20)}  # farms registered twice by different clerks
    for plant_code, farms in farms_by_plant.items():
        for i, f in enumerate(farms):
            # Half of the CNPJs were typed with the mask, half without
            cnpj_text = masked(f["cnpj"]) if rng.random() < 0.5 else f["cnpj"]
            status = "A"
            rows.append(
                (f["code"], f["name"], cnpj_text, f["city"], f["uf"], plant_code, f["distance"], f["since"], status, registered)
            )
            if (plant_code, i) in duplicates:
                code += 1
                f["codes"].append(code)
                other_text = f["cnpj"] if "/" in cnpj_text else masked(f["cnpj"])
                rows.append(
                    (
                        code,
                        f["name"].upper(),
                        other_text,
                        f["city"],
                        f["uf"],
                        plant_code,
                        f["distance"],
                        datetime(2024, 6, 1),
                        "A",
                        registered,
                    )
                )
    data.fornecedor = rows
    return farms_by_plant


def simulate_day(rng: random.Random, day: date, farms_by_plant: dict, data: ErpData, ids: dict) -> None:
    """One day of business in every plant: lots received, production orders, inspections and line stops."""
    for plant_code, _name, _city, _uf, capacity in PLANTS:
        lots_today = round(capacity / 21_000)  # one truck carries about 20 thousand birds
        for n in range(lots_today):
            farm = rng.choice(farms_by_plant[plant_code])
            ids["lot"] += 1
            lot = ids["lot"]
            farm_code = rng.choice(farm["codes"])  # duplicated farms deliver under both codes
            scheduled = at(day, 1 + n * 22 / lots_today)
            updated = scheduled + timedelta(hours=1)

            # About 1% of the loads are cancelled: no arrival, no weights
            if rng.random() < 0.01:
                data.recebimento_lote.append(
                    (lot, farm_code, plant_code, scheduled, None, None, None, None, None, "CANCELADO", updated)
                )
                continue

            # Arrival: farther farms and less punctual drivers arrive later
            delay = rng.gauss(10 + farm["distance"] * 0.25, 25) * farm["punctuality"]
            arrival = scheduled + timedelta(minutes=round(delay))
            birds = rng.randint(18_000, 23_000)
            avg_weight = rng.gauss(2.85, 0.12)
            live_kg = round(birds * avg_weight, 2)
            doa_rate = 0.0012 * summer_factor(day) * farm["welfare"] * (1 + farm["distance"] / 150)
            doa = max(0, round(rng.gauss(birds * doa_rate, math.sqrt(birds * doa_rate))))
            condemned = round(live_kg * rng.uniform(0.003, 0.008), 2)

            # Typing errors at the scale: zero or negative weight (rejected by the warehouse)
            if rng.random() < 0.003:
                live_kg = rng.choice([0.0, -live_kg])

            data.recebimento_lote.append(
                (
                    lot,
                    farm_code,
                    plant_code,
                    scheduled,
                    arrival,
                    birds,
                    live_kg,
                    doa,
                    condemned,
                    "RECEBIDO",
                    arrival + timedelta(minutes=30),
                )
            )
            if live_kg <= 0:
                continue

            # Production: the lot is split into products; each order runs on one of three lines
            start = arrival + timedelta(minutes=rng.randint(60, 180))
            for code, _desc, category, share in PRODUCTS:
                if category == "PROCESSADO" and rng.random() < 0.3:  # processed items are not made from every lot
                    continue
                line = rng.randint(1, 3)
                planned = round(live_kg * share, 2)
                efficiency = rng.gauss(0.985, 0.025)
                worn_line = plant_code == 3 and line == 2 and day >= date(2026, 3, 1)
                if worn_line:
                    efficiency -= 0.06  # Rio Verde line 2: worn equipment loses yield
                produced = round(planned * efficiency, 2)
                if rng.random() < 0.002:
                    produced = round(planned * rng.uniform(1.35, 2.0), 2)  # extra digit typed: impossible yield
                ids["order"] += 1
                end = start + timedelta(minutes=round(planned / 90))
                data.ordem_producao.append((ids["order"], lot, plant_code, code, line, start, end, planned, produced, end))

                # One sampled inspection per order; worn equipment causes more defects
                ids["inspection"] += 1
                sample = rng.choice([30, 40, 50, 60])
                rate = 0.018 * (2.2 if worn_line else 1.0)
                defects = sum(1 for _ in range(sample) if rng.random() < rate)
                result = "R" if defects / sample > 0.05 else "A"
                inspected = end + timedelta(minutes=rng.randint(10, 90))
                order_ref = ids["order"]
                if rng.random() < 0.0005:
                    order_ref = ids["order"] + 50_000_000  # inspection typed against an order that does not exist
                data.inspecao_qualidade.append((ids["inspection"], order_ref, inspected, sample, defects, result, inspected))

        # Line stops: about one stop per line every four days; the worn line stops three times more
        for line in (1, 2, 3):
            chance = 0.25 * (3.0 if plant_code == 3 and line == 2 and day >= date(2026, 3, 1) else 1.0)
            if rng.random() < chance:
                ids["stop"] += 1
                begin = at(day, rng.uniform(0, 23))
                minutes = max(5, round(rng.lognormvariate(3.6, 0.6)))
                finish = begin + timedelta(minutes=minutes)
                reason = rng.choice(rng.choice(STOP_REASONS))
                if rng.random() < 0.004:
                    begin, finish = finish, begin  # end typed before the start
                data.parada_linha.append((ids["stop"], plant_code, line, begin, finish, reason, max(begin, finish)))


def generate(start: date = START, end: date = END) -> tuple[ErpData, dict]:
    """Full history for the first load. Returns the data and the simulation state for later days."""
    rng = random.Random(SEED)
    data = ErpData()
    farms_by_plant = build_dimensions(rng, data)
    ids = {"lot": 500_000, "order": 9_000_000, "inspection": 3_000_000, "stop": 70_000}
    day = start
    while day <= end:
        simulate_day(rng, day, farms_by_plant, data, ids)
        day += timedelta(days=1)
    return data, {"rng": rng, "farms": farms_by_plant, "ids": ids}


def next_day_changes(state: dict, first_load: ErpData) -> tuple[ErpData, list[tuple]]:
    """One more day of business plus changes to old records, to test the incremental load.

    Returns the new rows and the updates to existing rows as (table, key column, key, {column: value}).
    """
    rng = state["rng"]
    new = ErpData()
    simulate_day(rng, NEXT_DAY, state["farms"], new, state["ids"])
    stamp = datetime(NEXT_DAY.year, NEXT_DAY.month, NEXT_DAY.day, 23, 0)
    first_farm = first_load.fornecedor[0]
    received = [r for r in first_load.recebimento_lote if r[9] == "RECEBIDO" and r[6] and r[6] > 0]
    corrected = received[len(received) // 2]
    updates = [
        # A farm moved its activity to another city (the supplier dimension must follow)
        ("FORNECEDOR", "COD_FORNECEDOR", first_farm[0], {"CIDADE": "Xaxim", "DISTANCIA_KM": 33, "DT_ATUALIZACAO": stamp}),
        # A farm stopped delivering
        ("FORNECEDOR", "COD_FORNECEDOR", first_load.fornecedor[5][0], {"SITUACAO": "I", "DT_ATUALIZACAO": stamp}),
        # The scale weight of an old lot was corrected (the fact must be updated, not duplicated)
        ("RECEBIMENTO_LOTE", "NR_LOTE", corrected[0], {"PESO_VIVO_KG": round(corrected[6] * 1.01, 2), "DT_ATUALIZACAO": stamp}),
    ]
    return new, updates
