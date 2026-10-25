"""Dense store x day arrays built from the cleaned SQL table.

Every forecaster works on these arrays, so "what is known at the forecast cutoff" is a slice of the second axis
and cannot silently leak: a forecaster is only ever handed `panel.sales[:, :cutoff_idx]` for the target series.

Calendar columns (promo, holiday, school holiday, open) are treated as known in advance at any origin:
a retailer knows its own promotion plan, public holidays and trading hours. Sales and Customers are never known.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Panel:
    stores: np.ndarray          # (S,) store ids, ascending
    dates: pd.DatetimeIndex     # (T,)
    sales: np.ndarray           # (S, T) float, 0 on closed days
    open: np.ndarray            # (S, T) bool
    promo: np.ndarray           # (S, T) bool
    holiday: np.ndarray         # (S, T) bool, state holiday
    school: np.ndarray          # (S, T) bool
    long_closure: np.ndarray    # (S, T) bool
    attrs: pd.DataFrame         # index store: store_type, assortment, volume_tercile, competition_distance, promo2

    @property
    def n_stores(self) -> int:
        return len(self.stores)

    @property
    def observed(self) -> np.ndarray:
        """Days that carry demand information: open and not part of a long closure."""
        return self.open & ~self.long_closure

    def index_of(self, date: str | pd.Timestamp) -> int:
        return int(self.dates.get_loc(pd.Timestamp(date)))

    def dow(self) -> np.ndarray:
        """Monday=0 .. Sunday=6 for every date column."""
        return np.asarray(self.dates.dayofweek)


def build_panel(con: sqlite3.Connection) -> Panel:
    clean = pd.read_sql_query(
        "SELECT store, date, sales, open, promo, holiday, school_holiday, long_closure FROM clean_store_day", con)
    clean["date"] = pd.to_datetime(clean["date"])
    seg = pd.read_sql_query(
        "SELECT store, store_type, assortment, volume_tercile, mean_sales_open_train, competition_distance, promo2 FROM store_segment", con)
    # stores with no usable training days have no segment row; they cannot be scored, so they are dropped here
    keep = set(seg["store"])
    clean = clean[clean["store"].isin(keep)]
    stores = np.array(sorted(keep))
    dates = pd.DatetimeIndex(sorted(clean["date"].unique()))
    s_idx = {s: i for i, s in enumerate(stores)}
    rows = clean["store"].map(s_idx).to_numpy()
    cols = dates.get_indexer(clean["date"])

    def dense(column: str, dtype) -> np.ndarray:
        arr = np.zeros((len(stores), len(dates)), dtype=dtype)
        arr[rows, cols] = clean[column].to_numpy()
        return arr

    return Panel(
        stores=stores, dates=dates,
        sales=dense("sales", float), open=dense("open", bool), promo=dense("promo", bool),
        holiday=dense("holiday", bool), school=dense("school_holiday", bool),
        long_closure=dense("long_closure", bool),
        attrs=seg.set_index("store").loc[stores],
    )
