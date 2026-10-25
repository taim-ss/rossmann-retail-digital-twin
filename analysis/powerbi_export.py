"""Power BI inputs: aggregate CSVs, a DAX measures file and a build guide.

Power BI Desktop is not installed on the build machine and cannot be driven here, so NO .pbix is produced and none was
opened or verified. Everything in powerbi/ is a text file you load into Desktop by hand (powerbi/BUILD-GUIDE.md).
Only aggregates and parameters are written; never per-store-day rows.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

MEASURES_DAX = """// measures.dax: paste each measure into Power BI Desktop (Modeling > New measure).
// Tables: fact_month_segment, fact_accuracy, fact_cost_kpi (CSV files in powerbi/data/).
// WAPE and bias cannot be recomputed from monthly aggregates, so they are read from fact_accuracy, which the Python
// pipeline computed per model, segment and horizon band with store-bootstrap confidence intervals.

Sales (EUR) = SUM ( fact_month_segment[sales_total] )

Open store days = SUM ( fact_month_segment[open_store_days] )

Sales per open store day = DIVIDE ( [Sales (EUR)], [Open store days] )

Promo share of open days =
    DIVIDE ( SUM ( fact_month_segment[promo_open_days] ), [Open store days] )

Promo sales per promo day =
    DIVIDE ( SUM ( fact_month_segment[sales_promo_days] ), SUM ( fact_month_segment[promo_open_days] ) )

Non-promo sales per day =
    DIVIDE (
        SUM ( fact_month_segment[sales_total] ) - SUM ( fact_month_segment[sales_promo_days] ),
        SUM ( fact_month_segment[open_store_days] ) - SUM ( fact_month_segment[promo_open_days] )
    )

// Descriptive only: promotions are not randomised, so this ratio is not a causal uplift.
Promo day sales ratio = DIVIDE ( [Promo sales per promo day], [Non-promo sales per day] )

// Forecast accuracy: choose a model and horizon band with slicers (one row remains after filtering).
WAPE = SELECTEDVALUE ( fact_accuracy[wape] )
WAPE low (95% CI) = SELECTEDVALUE ( fact_accuracy[wape_lo] )
WAPE high (95% CI) = SELECTEDVALUE ( fact_accuracy[wape_hi] )
Bias = SELECTEDVALUE ( fact_accuracy[bias] )

// Assumed-cost KPIs: ASSUMPTION-driven, see excel/assumptions_and_sensitivity.xlsx.
Finding EUR per store-year (base) = MAX ( fact_cost_kpi[base_finding] )
Tornado swing = SUM ( fact_cost_kpi[swing] )

// Date table: one row per day, explicit bounds (CALENDARAUTO would scan unrelated columns).
Dim Date =
    ADDCOLUMNS (
        CALENDAR ( DATE ( 2013, 1, 1 ), DATE ( 2015, 12, 31 ) ),
        "Year", YEAR ( [Date] ),
        "Month number", MONTH ( [Date] ),
        "Month start", DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 )
    )
"""

GUIDE = """# Power BI build guide (the .pbix was NOT produced or verified)

Power BI Desktop is not installed on the machine that built this repository, and no tool here can create or check a
.pbix. This guide gives you the data, the measures and the steps. Build it yourself so you can explain every visual.
Install route that needs no admin rights: Microsoft Store, "Power BI Desktop" (the direct installer needs admin).
Authoring works without signing in; do not publish anything you have not reviewed.

## Load the data
1. Home > Get data > Text/CSV, load the three files in `powerbi/data/`:
   `fact_month_segment.csv`, `fact_accuracy.csv`, `fact_cost_kpi.csv`. Check the types: `month_start` = Date,
   numbers = Decimal.
2. Modeling > New table, paste `Dim Date` from `measures.dax`. Relationship: `Dim Date[Date]` 1-to-many
   `fact_month_segment[month_start]` (single direction).
3. Paste the other measures from `measures.dax`.

## Pages
| Page | Visuals | Fields |
|---|---|---|
| 1 Sales and promotions | Line: sales by month. Clustered column: promo day sales ratio by store_type. Cards: Sales, Promo share. | measures; slicers store_type, assortment, volume_tercile |
| 2 Forecast accuracy | Bar: WAPE by model (slicer horizon_band = pooled_h1-14, segment_dim = all) with error bars from WAPE low/high. Table: segment_dim, segment, WAPE, Bias. | `fact_accuracy` |
| 3 Assumed cost of error | Card: Finding EUR per store-year. Bar: tornado swing by parameter. Text box: the ASSUMPTION list. | `fact_cost_kpi` |

## Honesty checklist for the dashboard
* Title every page with the data gap: "Rossmann has no stock, orders, lead times or costs; cost figures are assumptions".
* Page 3 must show the assumption values next to the finding.
* WAPE bars show confidence intervals; do not rank two models whose intervals overlap as different without saying so.
* If any numbers come from `outputs/demo/`, the pages must say SYNTHETIC.
* Screenshot each page into `powerbi/screenshots/` once built; then say "built in Power BI Desktop" only if you built it.
"""


def export_powerbi(con: sqlite3.Connection, accuracy: pd.DataFrame, tornado: pd.DataFrame, base_finding: float,
                   out_dir: Path) -> dict:
    data = out_dir / "data"
    data.mkdir(parents=True, exist_ok=True)
    month = pd.read_sql_query("SELECT * FROM agg_month_segment", con)
    month["month_start"] = month["month"] + "-01"
    month.to_csv(data / "fact_month_segment.csv", index=False)
    accuracy.to_csv(data / "fact_accuracy.csv", index=False)
    cost = tornado.assign(base_finding=base_finding)
    cost.to_csv(data / "fact_cost_kpi.csv", index=False)
    (out_dir / "measures.dax").write_text(MEASURES_DAX, encoding="utf-8")
    (out_dir / "BUILD-GUIDE.md").write_text(GUIDE, encoding="utf-8")
    return {"month_rows": len(month), "accuracy_rows": len(accuracy), "cost_rows": len(cost)}
