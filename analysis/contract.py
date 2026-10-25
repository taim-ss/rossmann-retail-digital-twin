"""Files handed to P2 (the AnyLogic replenishment model) and the rule that picks the stores in them.

Store choice is a pure function of the training-period store segments: no random numbers, so the same data always
give the same stores (design: docs/experiment-design.md section D).
Per-store-day files are derived from Rossmann data and stay gitignored; only parameters and aggregates are committable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .panel import Panel

MIN_ORIGIN_GAP_H = 5  # base lead time assumption L = 5 days: the contract forecast was issued at least 5 days ahead
MODEL_FILES = {"forecast_oracle.csv": "oracle", "forecast_naive.csv": "snaive1", "forecast_ml.csv": "ml"}
DEMAND_COLUMNS = ["date", "store", "actual_sales_units", "promo", "holiday", "open"]


def _closest_to_median(frame: pd.DataFrame, n: int = 1) -> list[int]:
    """The n stores whose training-period mean sales are closest to the median of `frame` (tie: lowest store id)."""
    med = frame["mean_sales_open_train"].median()
    ranked = frame.assign(dist=(frame["mean_sales_open_train"] - med).abs()).sort_values(["dist", "store"])
    return [int(s) for s in ranked["store"].head(n)]


def _segments(attrs: pd.DataFrame) -> pd.DataFrame:
    return attrs.rename_axis("store").reset_index()


def select_calibration_store(attrs: pd.DataFrame) -> int:
    seg = _segments(attrs)
    pool = seg[(seg["store_type"] == "a") & (seg["assortment"] == "a")]
    if pool.empty:
        pool = seg[seg["store_type"] == "a"]
    if pool.empty:
        pool = seg
    return _closest_to_median(pool)[0]


def select_10_stores(attrs: pd.DataFrame, calibration_store: int | None = None) -> list[int]:
    """One store per StoreType first (largest cell of that type), then the next-largest (StoreType, volume tercile)
    cells until 10; each store is the one closest to its cell's median. The calibration store is never repeated."""
    seg = _segments(attrs)
    if calibration_store is None:
        calibration_store = select_calibration_store(attrs)
    seg = seg[seg["store"] != calibration_store]
    cells = seg.groupby(["store_type", "volume_tercile"]).size().rename("n").reset_index()
    cells = cells.sort_values(["n", "store_type", "volume_tercile"], ascending=[False, True, True])
    first_per_type = cells.groupby("store_type", sort=True).head(1)
    order = pd.concat([first_per_type, cells.drop(first_per_type.index)], ignore_index=True)
    chosen: list[int] = []
    for row in order.itertuples(index=False):
        cell = seg[(seg["store_type"] == row.store_type) & (seg["volume_tercile"] == row.volume_tercile)]
        cell = cell[~cell["store"].isin(chosen)]
        if not cell.empty:
            chosen.append(_closest_to_median(cell)[0])
        if len(chosen) == 10:
            break
    for store in _closest_to_median(seg[~seg["store"].isin(chosen)], n=max(0, 10 - len(chosen))):
        chosen.append(store)  # fewer than 10 non-empty cells: top up with the closest-to-median leftovers
    return chosen[:10]


def contract_forecast_rows(bt: pd.DataFrame) -> pd.DataFrame:
    """One row per (store, date): the forecast with the smallest horizon h >= MIN_ORIGIN_GAP_H (issued 5+ days ahead)."""
    ok = bt[bt["h"] >= MIN_ORIGIN_GAP_H]
    idx = ok.groupby(["store", "date"])["h"].idxmin()
    return ok.loc[idx.to_numpy()].sort_values(["store", "date"]).reset_index(drop=True)


def build_contract(panel: Panel, bt: pd.DataFrame, out_dir: Path, units_per_currency: float = 1.0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cal = select_calibration_store(panel.attrs)
    ten = select_10_stores(panel.attrs, cal)
    stores = [cal, *ten]
    pos = {int(s): i for i, s in enumerate(panel.stores)}
    parts = []
    for s in stores:
        i = pos[s]
        parts.append(pd.DataFrame({
            "date": panel.dates.strftime("%Y-%m-%d"), "store": s,
            "actual_sales_units": panel.sales[i] / units_per_currency,
            "promo": panel.promo[i].astype(int), "holiday": panel.holiday[i].astype(int),
            "open": panel.open[i].astype(int)}))
    demand = pd.concat(parts, ignore_index=True)[DEMAND_COLUMNS]
    demand.to_csv(out_dir / "store_day_demand.csv", index=False)

    sub = contract_forecast_rows(bt[bt["store"].isin(stores)])
    for fname, col in MODEL_FILES.items():
        order = {s: k for k, s in enumerate(stores)}
        f = sub.assign(forecast_mean=sub[col] / units_per_currency, o=sub["store"].map(order))
        f = f.sort_values(["o", "date"])[["date", "store", "forecast_mean"]]
        f["date"] = pd.to_datetime(f["date"]).dt.strftime("%Y-%m-%d")
        f.to_csv(out_dir / fname, index=False)

    resid = []
    scored = bt[bt["scored"] & bt["store"].isin(stores)]
    for name, col in (("naive", "snaive1"), ("ml", "ml")):
        resid.append(pd.DataFrame({
            "model": name, "store": scored["store"], "date": pd.to_datetime(scored["date"]).dt.strftime("%Y-%m-%d"),
            "origin": scored["origin"].dt.strftime("%Y-%m-%d"), "horizon": scored["h"], "promo": scored["promo"].astype(int),
            "actual": scored["actual"] / units_per_currency, "forecast": scored[col] / units_per_currency,
            "error": (scored["actual"] - scored[col]) / units_per_currency}))
    pd.concat(resid, ignore_index=True).to_csv(out_dir / "forecast_error_distribution.csv", index=False)

    seg = panel.attrs.loc[stores, ["store_type", "assortment", "volume_tercile"]].reset_index()
    seg.insert(1, "role", ["calibration"] + ["set10"] * len(ten))
    seg.to_csv(out_dir / "selected_stores.csv", index=False)
    return {"calibration_store": cal, "stores": stores, "forecast_first": str(sub["date"].min())[:10],
            "forecast_last": str(sub["date"].max())[:10], "n_forecast_rows_per_file": int(len(sub)),
            "n_demand_rows": int(len(demand)), "n_residual_rows": int(sum(len(r) for r in resid))}


def write_contract_md(out_dir: Path, info: dict, is_demo: bool) -> Path:
    banner = ("> SYNTHETIC DEMO OUTPUT: generated from make_demo_data.py, not Rossmann.\n\n" if is_demo else "")
    text = f"""{banner}# P1 -> P2 file contract

Files in this folder are consumed by the AnyLogic replenishment model (P2). Per-store-day files are derived from the
Kaggle Rossmann data and are gitignored; regenerate them with `python run_pipeline.py`.

## Stores
`selected_stores.csv` lists them: the **calibration store first** ({info['calibration_store']}), then 10 stores
({', '.join(map(str, info['stores'][1:]))}). Rule (deterministic, no random numbers): calibration store = StoreType a,
Assortment a, training-period mean sales closest to the median of that group; the 10 = one store per StoreType plus
the largest (StoreType, volume tercile) cells until 10, each closest to its cell's median.

## Files
| File | Columns | Rows | Notes |
|---|---|---|---|
| `store_day_demand.csv` | date, store, actual_sales_units, promo, holiday, open | {info['n_demand_rows']} | calibration store rows first; whole data range; closed days have 0 |
| `forecast_oracle.csv` | date, store, forecast_mean | {info['n_forecast_rows_per_file']} | the actual value; zero-error reference only |
| `forecast_naive.csv` | date, store, forecast_mean | {info['n_forecast_rows_per_file']} | seasonal naive: most recent same weekday before the cutoff |
| `forecast_ml.csv` | date, store, forecast_mean | {info['n_forecast_rows_per_file']} | one global gradient-boosted model |
| `forecast_error_distribution.csv` | model, store, date, origin, horizon, promo, actual, forecast, error | {info['n_residual_rows']} | empirical residuals, error = actual - forecast, open days only |
| `calibration_table.csv` | see docs/experiment-design.md section B | all stores | parameters and fit diagnostics (committable) |

## Definitions you must respect
* **Units.** Rossmann records daily turnover, not units sold. `actual_sales_units` is turnover divided by
  `units_per_currency` (= 1, so one unit = EUR 1 of turnover, ASSUMPTION). The currency itself is the community reading,
  not an official statement. P2 inventory levels are in these units.
* **Forecast timing.** `forecast_mean` for a date was issued from the latest weekly origin that is at least
  {MIN_ORIGIN_GAP_H} days before that date (horizon {MIN_ORIGIN_GAP_H} to 11 days, matching the assumed 5-day lead time).
  Dates covered: {info['forecast_first']} to {info['forecast_last']} (validation months, 2015). Forecast is 0 on closed days.
* **holiday** = state holiday (codes a, b, c). **open** is treated as known in advance (ASSUMPTION), as are promo and holiday.
* **No stock, orders, lead times or costs exist in the data.** P2 supplies them as labelled assumptions.
* Dates before the first forecast date have actuals only: use them to calibrate, never to score a forecast.

## For the P2 comparison
Same `repSeed` and one random stream per stochastic source across oracle, naive and ML (common random numbers); analyse paired
differences. Base offsets: demand noise 10000, lead-time variation 20000, reserved 30000 (`java.util.Random(base + repSeed)`).
"""
    path = out_dir / "CONTRACT.md"
    path.write_text(text, encoding="utf-8")
    return path
