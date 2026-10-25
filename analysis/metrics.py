"""Forecast accuracy metrics.

WAPE = sum(|forecast - actual|) / sum(actual)      (0 is perfect; undefined when the actuals sum to 0)
bias = sum(forecast - actual) / sum(actual)        (positive = over-forecast; same denominator as WAPE)

Both are ratios of sums, so zero-sales days do not blow them up the way a per-row percentage error would.
Confidence intervals resample whole STORES, because days of one store are strongly dependent; resampling
store-days would make the intervals far too narrow.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd


def wape(actual: np.ndarray | pd.Series, forecast: np.ndarray | pd.Series) -> float:
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    denom = a.sum()
    if denom <= 0:
        return float("nan")
    return float(np.abs(f - a).sum() / denom)


def bias(actual: np.ndarray | pd.Series, forecast: np.ndarray | pd.Series) -> float:
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    denom = a.sum()
    if denom <= 0:
        return float("nan")
    return float((f - a).sum() / denom)


def store_bootstrap_ci(
    frame: pd.DataFrame,
    metric: Callable[[np.ndarray, np.ndarray], float],
    n_boot: int = 1000,
    seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float, float]:
    """Point estimate and percentile CI of `metric(actual, forecast)`, resampling stores with replacement.

    `frame` needs the columns store, actual, forecast. Per-store sums are precomputed, which is exact for
    ratio-of-sums metrics (WAPE and bias) and makes the bootstrap fast.
    """
    if frame.empty:
        return float("nan"), float("nan"), float("nan")
    per_store = frame.assign(abs_err=(frame["forecast"] - frame["actual"]).abs(),
                             err=frame["forecast"] - frame["actual"]).groupby("store").agg(
        actual=("actual", "sum"), abs_err=("abs_err", "sum"), err=("err", "sum"))
    point = metric(frame["actual"].to_numpy(), frame["forecast"].to_numpy())
    rng = np.random.default_rng(seed)
    n = len(per_store)
    actual, abs_err, err = per_store["actual"].to_numpy(), per_store["abs_err"].to_numpy(), per_store["err"].to_numpy()
    draws = rng.integers(0, n, size=(n_boot, n))
    denom = actual[draws].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        if metric is wape:
            values = abs_err[draws].sum(axis=1) / denom
        elif metric is bias:
            values = err[draws].sum(axis=1) / denom
        else:
            raise ValueError("store_bootstrap_ci supports wape and bias only")
    values = values[np.isfinite(values)]
    lo, hi = np.percentile(values, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(point), float(lo), float(hi)
