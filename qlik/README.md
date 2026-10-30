# Qlik Sense app — Poultry Operations

The app reads the CSV files in [`data/`](data/), exported from the PostgreSQL warehouse after the Hop
workflow passed its quality gate. [`load_script.qvs`](load_script.qvs) builds a QVD layer and the data model;
this page describes the sheets.

## Setup (Qlik Sense Desktop)

1. Create a new app and open the **Data load editor**.
2. Create a folder data connection called **FoodProduction** pointing to this `qlik/data` folder.
3. Paste `load_script.qvs` (keep the tabs) and click **Load data**. The script also creates `qlik/data/qvd/`.

In **Qlik Cloud**, upload the CSV files to *Data files* and set `vSource` and `vQvd` to `'lib://DataFiles/'`.

## Data model

```
                 Calendar            Plants
                     \                 /
                      LinkDatePlant (%DatePlant = day | plant)
                     /                 \
 Farms ── Lots (LotNumber)          LineStops
             │
        Production (OrderNumber) ── Products
             │
        Inspections

 Data islands (never filter the business numbers): RejectedRows, QualityChecks
```

- **Link table:** lots and line stops are both "per day and per plant". Linking both to Calendar and Plants
  would create a loop, so only `LinkDatePlant` points to them.
- **Production and inspections** inherit the day, the plant and the farm from their lot.
- **Measures** are variables (`$(vDOAPct)`, `$(vYieldPct)`...) defined once in the script. Every rate is a
  sum divided by a sum, so it stays correct for any selection.

## Sheets

Reference values (full history, January 2025 – September 2026) to check the app after the first reload.

### 1. Overview

| Object | Dimension | Measure | Reference |
|---|---|---|---|
| KPI | — | `$(vLotsReceived)` | 17,652 lots |
| KPI | — | `$(vLiveWeightTon)` | 1,030,887 t |
| KPI | — | `$(vDOAPct)` (dead on arrival) | 0.215% |
| KPI | — | `$(vYieldPct)` (carcass yield) | 70.36% |
| KPI | — | `$(vOnTimePct)` (lots on time) | 89.1% |
| KPI | — | `$(vApprovalPct)` (inspections approved) | 93.9% |
| Line chart | YearMonth | `$(vDOAPct)` | peaks every summer (December to March) |
| Bar chart | Plant | `$(vLiveWeightTon)`, `$(vYieldPct)` | |
| Filter panes | Year, Plant, Season | | |

### 2. Animal welfare and farms

| Object | Dimension | Measure | Reference |
|---|---|---|---|
| Bar chart | Season | `$(vDOAPct)` | summer 0.300% vs 0.173% the rest of the year |
| Bar chart | Distance Band | `$(vDOAPct)` | 0.170% under 30 km up to 0.319% over 100 km |
| Scatter plot | Farm | x: `Avg([Distance (km)])`, y: `$(vDOAPct)`, size: `$(vBirds)` | two farms far above the others |
| Table | Farm, Plant, Distance Band | `$(vLotsReceived)`, `$(vDOAPct)`, `$(vOnTimePct)`, `$(vCondemnedPct)` | top: Avícola Ouro Verde (Rio Verde) 1.12%, Avícola Bela Vista (Toledo) 0.50% |

### 3. Plants and lines

| Object | Dimension | Measure | Reference |
|---|---|---|---|
| Line chart | YearMonth, Production Line (filter Plant = Unidade Rio Verde) | `$(vOutputVsPlan)` | line 2 falls from 98.5% to 92.5% from March 2026 |
| Bar chart | Stop Reason | `$(vStopMinutes)` | |
| Combo chart | YearMonth | `Count(StopNumber)` (bars), `$(vStopMinutes)` (line) | Rio Verde line 2: about 3 times more stops from March 2026 |
| Table | Plant, Production Line | `$(vOutputVsPlan)`, `$(vApprovalPct)`, `$(vDefectRate)` | Rio Verde line 2 after March 2026: 73.8% approved, 3.9% defects |

Use **output vs plan** (not carcass yield) to compare lines: a lot is processed on several lines, so its live
weight cannot be split by line.

### 4. Data quality

| Object | Dimension | Measure | Reference |
|---|---|---|---|
| Table | Check, Check Severity, Check Result | `Sum([Check Expected])`, `Sum([Check Actual])` | every critical check passed |
| Bar chart | Rejected ERP Table, Reject Reason | `$(vRejectedRows)` | 47 lots, 245 production orders, 321 inspections, 11 line stops |
| Table | Rejected ERP Table, Rejected ERP Key, Reject Reason | `Sum([Rejected Kg])` | the list the ERP team must fix |
