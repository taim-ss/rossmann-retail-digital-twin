# Power BI build guide (the .pbix was NOT produced or verified)

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
