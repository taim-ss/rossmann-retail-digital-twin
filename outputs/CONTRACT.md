# P1 -> P2 file contract

Files in this folder are consumed by the AnyLogic replenishment model (P2). Per-store-day files are derived from the
Kaggle Rossmann data and are gitignored; regenerate them with `python run_pipeline.py`.

## Stores
`selected_stores.csv` lists them: the **calibration store first** (164), then 10 stores
(39, 693, 962, 259, 913, 848, 279, 98, 130, 668). Rule (deterministic, no random numbers): calibration store = StoreType a,
Assortment a, training-period mean sales closest to the median of that group; the 10 = one store per StoreType plus
the largest (StoreType, volume tercile) cells until 10, each closest to its cell's median.

## Files
| File | Columns | Rows | Notes |
|---|---|---|---|
| `store_day_demand.csv` | date, store, actual_sales_units, promo, holiday, open | 10362 | calibration store rows first; whole data range; closed days have 0 |
| `forecast_oracle.csv` | date, store, forecast_mean | 1881 | the actual value; zero-error reference only |
| `forecast_naive.csv` | date, store, forecast_mean | 1881 | seasonal naive: most recent same weekday before the cutoff |
| `forecast_ml.csv` | date, store, forecast_mean | 1881 | one global gradient-boosted model |
| `forecast_error_distribution.csv` | model, store, date, origin, horizon, promo, actual, forecast, error | 6166 | empirical residuals, error = actual - forecast, open days only |
| `calibration_table.csv` | see docs/experiment-design.md section B | all stores | parameters and fit diagnostics (committable) |

## Definitions you must respect
* **Units.** Rossmann records daily turnover, not units sold. `actual_sales_units` is turnover divided by
  `units_per_currency` (= 1, so one unit = EUR 1 of turnover, ASSUMPTION). The currency itself is the community reading,
  not an official statement. P2 inventory levels are in these units.
* **Forecast timing.** `forecast_mean` for a date was issued from the latest weekly origin that is at least
  5 days before that date (horizon 5 to 11 days, matching the assumed 5-day lead time).
  Dates covered: 2015-01-05 to 2015-06-24 (validation months, 2015). Forecast is 0 on closed days.
* **holiday** = state holiday (codes a, b, c). **open** is treated as known in advance (ASSUMPTION), as are promo and holiday.
* **No stock, orders, lead times or costs exist in the data.** P2 supplies them as labelled assumptions.
* Dates before the first forecast date have actuals only: use them to calibrate, never to score a forecast.

## For the P2 comparison
Same `repSeed` and one random stream per stochastic source across oracle, naive and ML (common random numbers); analyse paired
differences. Base offsets: demand noise 10000, lead-time variation 20000, reserved 30000 (`java.util.Random(base + repSeed)`).
