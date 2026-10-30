# ADR 0003 — Qlik Sense model with a link table and measures as variables

**Status:** accepted

## Context

Qlik associates tables by field name. Lots and line stops are both "per day and per plant": if both carried
`DateKey` and `PlantKey`, Qlik would create a synthetic key and a loop between Calendar, Plants and the two facts.
Production and inspections belong to a lot and to an order, not directly to a day.

## Decision

- **Link table:** lots and stops carry one composite key, `%DatePlant` (`date_key|plant_key`); only
  `LinkDatePlant` points to Calendar and Plants.
- **Production and inspections hang from their lot and order** (`LotNumber`, `OrderNumber`) and inherit the day, the
  plant and the farm of the lot.
- **Two line fields** (`Production Line`, `Stop Line`) on purpose: line 2 of one plant is not related to line 2 of
  another.
- **QVD layer:** each CSV is stored once as QVD; the model reloads from the QVDs.
- **Measures as variables** (`$(vDOAPct)`...), always a sum divided by a sum, so every chart uses the same
  definition and the rate stays correct for any selection.
- **Data quality tables as islands:** rejects and checks share no field with the model and never filter it.

## Consequences

- No synthetic keys and no loops; selections on plant or month filter lots, stops, production and inspections.
- Yield is measured per lot (produced kg / live weight). Lines are compared by output vs. plan, because one lot is
  processed on several lines and its live weight cannot be split by line.
