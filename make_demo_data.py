"""Generate a SYNTHETIC dataset with the same schema as the Rossmann Store Sales files.

Purpose: let anyone (and the test suite) run the whole pipeline without the Kaggle files.
Nothing here is Rossmann data: every number comes from a seeded random generator, and the
parameters below are invented. Results computed from this file are pipeline tests, not findings.

Quirks are planted on purpose so the cleaning rules have something to catch:
  - Sundays closed for most stores (a few "type b" stores stay open),
  - state holidays (codes a/b/c) closed with Sales 0,
  - three stores closed for a 90-day refurbishment block in 2014,
  - a handful of missing Open values on one store,
  - a few Open=0 rows with positive Sales and Open=1 rows with zero Sales,
  - CompetitionDistance missing for a few stores.

Usage:  python make_demo_data.py [--out data/demo] [--stores 60] [--seed 20260101]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

START, END = "2013-01-01", "2015-07-31"
WEEKDAY_FACTOR = {1: 1.15, 2: 1.00, 3: 0.97, 4: 0.98, 5: 1.05, 6: 0.95, 7: 0.60}  # 1=Mon .. 7=Sun


def _state_holidays(dates: pd.DatetimeIndex, rng: np.random.Generator) -> pd.Series:
    """Fixed national-style holidays per year (about 10 days), codes a (public), b (Easter), c (Christmas)."""
    codes = pd.Series("0", index=dates)
    for year in sorted(set(dates.year)):
        fixed = [(1, 1, "a"), (5, 1, "a"), (10, 3, "a"), (12, 25, "c"), (12, 26, "c")]
        easter = pd.Timestamp(year=year, month=3, day=28) + pd.Timedelta(days=int(rng.integers(0, 28)))
        fixed += [((easter - pd.Timedelta(days=2)).month, (easter - pd.Timedelta(days=2)).day, "b"),
                  ((easter + pd.Timedelta(days=1)).month, (easter + pd.Timedelta(days=1)).day, "b")]
        for month, day, code in fixed:
            ts = pd.Timestamp(year=year, month=month, day=day)
            if ts in codes.index:
                codes.loc[ts] = code
    return codes


def generate(n_stores: int = 60, seed: int = 20260101) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(START, END, freq="D")
    n_days = len(dates)
    holidays = _state_holidays(dates, rng)
    school = np.zeros(n_days, dtype=int)
    for year in sorted(set(dates.year)):  # two school-holiday blocks per year
        for month, day, length in ((7, 10, 35), (12, 22, 12)):
            start = pd.Timestamp(year=year, month=month, day=day)
            school[(dates >= start) & (dates < start + pd.Timedelta(days=length))] = 1

    store_rows = []
    for store in range(1, n_stores + 1):
        store_type = rng.choice(list("abcd"), p=[0.55, 0.05, 0.15, 0.25])
        assortment = rng.choice(list("abc"), p=[0.5, 0.05, 0.45])
        comp = float(np.round(rng.lognormal(7.0, 1.0), 0)) if rng.random() > 0.03 else np.nan
        promo2 = int(rng.random() < 0.5)
        store_rows.append({
            "Store": store, "StoreType": store_type, "Assortment": assortment,
            "CompetitionDistance": comp,
            "CompetitionOpenSinceMonth": np.nan if np.isnan(comp) else int(rng.integers(1, 13)),
            "CompetitionOpenSinceYear": np.nan if np.isnan(comp) else int(rng.integers(2005, 2014)),
            "Promo2": promo2,
            "Promo2SinceWeek": int(rng.integers(1, 53)) if promo2 else np.nan,
            "Promo2SinceYear": int(rng.integers(2009, 2014)) if promo2 else np.nan,
            "PromoInterval": "Jan,Apr,Jul,Oct" if promo2 else np.nan,
        })
    stores = pd.DataFrame(store_rows)

    dow = dates.dayofweek.to_numpy() + 1
    day_of_year = dates.dayofyear.to_numpy()
    season = 1 + 0.10 * np.cos(2 * np.pi * (day_of_year - 355) / 365.25)  # December peak
    trend = 1 + 0.03 * (np.arange(n_days) / 365.25)
    refurb_stores = set(rng.choice(np.arange(1, n_stores + 1), size=3, replace=False))

    frames = []
    for row in stores.itertuples(index=False):
        base = rng.lognormal(mean=np.log(5800), sigma=0.35)
        uplift = rng.uniform(1.20, 1.55)
        promo_phase = int(rng.integers(0, 2))
        week = (np.arange(n_days) // 7 + promo_phase) % 2
        promo = ((week == 0) & (dow <= 5)).astype(int)
        open_flag = np.ones(n_days, dtype=int)
        sunday_open = row.StoreType == "b"
        open_flag[(dow == 7) & (not sunday_open)] = 0
        open_flag[holidays.to_numpy() != "0"] = 0
        if row.Store in refurb_stores:
            block_start = int(rng.integers(500, 800))
            open_flag[block_start:block_start + 90] = 0
        type_factor = {"a": 1.0, "b": 1.5, "c": 1.0, "d": 1.15}[row.StoreType]
        mean = base * type_factor * season * trend * np.array([WEEKDAY_FACTOR[d] for d in dow])
        mean = mean * np.where(promo == 1, uplift, 1.0)
        mean = mean * np.where(school == 1, 1.03, 1.0)
        shape = 40.0  # gamma noise, CV about 16 percent
        sales = rng.gamma(shape, mean / shape)
        sales = np.round(sales * open_flag, 0)
        customers = np.round(sales / rng.uniform(8.5, 10.5), 0)
        frame = pd.DataFrame({
            "Store": row.Store, "DayOfWeek": dow, "Date": dates.strftime("%Y-%m-%d"),
            "Sales": sales.astype(int), "Customers": customers.astype(int), "Open": open_flag,
            "Promo": promo, "StateHoliday": holidays.to_numpy(), "SchoolHoliday": school,
        })
        frames.append(frame)
    train = pd.concat(frames, ignore_index=True)

    # planted data-quality problems
    quirk_store = n_stores // 2
    idx = train.index[(train.Store == quirk_store) & (train.Date.between("2014-03-03", "2014-03-09"))]
    train["Open"] = train["Open"].astype("float")
    train.loc[idx, "Open"] = np.nan
    bad_closed = rng.choice(train.index[train.Open == 0], size=8, replace=False)
    train.loc[bad_closed, "Sales"] = rng.integers(50, 400, size=8)
    open_idx = train.index[(train.Open == 1) & (train.Sales > 0)]
    train.loc[rng.choice(open_idx, size=5, replace=False), "Sales"] = 0
    train["Open"] = train["Open"].astype("Int64")  # whole numbers in the CSV, blank where missing
    train = train.sort_values(["Date", "Store"], ascending=[False, True]).reset_index(drop=True)  # Kaggle order
    return train, stores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="data/demo")
    parser.add_argument("--stores", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260101)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    train, stores = generate(args.stores, args.seed)
    train.to_csv(out / "train.csv", index=False)
    stores.to_csv(out / "store.csv", index=False)
    (out / "SYNTHETIC_README.txt").write_text(
        "SYNTHETIC DATA generated by make_demo_data.py. Not Rossmann data. "
        "Same columns as the Kaggle files so the pipeline can be tested without them.\n")
    print(f"wrote {len(train):,} synthetic store-days for {args.stores} stores to {out}")


if __name__ == "__main__":
    main()
