"""Rolling-origin backtest (design: docs/experiment-design.md section A).

An origin date o is the first day being forecast; the information cutoff is the day before (o - 1).
Horizon h = 1..14 forecasts day o + h - 1. Origins are 7 days apart so the folds are date-ordered and
never see a sales value from their own forecast window.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import FINAL_TEST_START, VALID_END, VALID_START
from .forecasters import (HORIZON, HoltWintersBank, baseline_forecasts, fit_ml, ml_forecast)
from .panel import Panel

log = logging.getLogger(__name__)
MODELS = ("naive", "snaive1", "snaive4", "hw", "ml")
ML_REFIT_EVERY = 4  # origins; each refit only sees targets before its own first origin
N_VALID_ORIGINS = 24


def validation_origins() -> list[pd.Timestamp]:
    """2015-01-01 + 7k, k = 0..23; last origin 2015-06-11 whose 14 targets end 2015-06-24 (inside validation)."""
    origins = [pd.Timestamp(VALID_START) + pd.Timedelta(days=7 * k) for k in range(N_VALID_ORIGINS)]
    assert origins[-1] + pd.Timedelta(days=HORIZON - 1) <= pd.Timestamp(VALID_END)
    return origins


def final_test_origins(last_day: pd.Timestamp) -> list[pd.Timestamp]:
    out, o = [], pd.Timestamp(FINAL_TEST_START)
    while o <= last_day:
        out.append(o)
        o += pd.Timedelta(days=7)
    return out


def run_backtest(panel: Panel, origins: list[pd.Timestamp], models: tuple[str, ...] = MODELS,
                 ml_first_origin: int = 91) -> pd.DataFrame:
    """Long table: one row per (store, origin, h) with actual, oracle and every model's forecast.

    `scored` is True where the target day is open and not part of a long closure (the only days WAPE is computed on).
    """
    idx = [panel.index_of(o) for o in origins]
    log.info("backtest: %d origins, %d stores, models=%s", len(idx), panel.n_stores, ",".join(models))
    hw = HoltWintersBank(panel, fit_cutoff=idx[0] - 1) if "hw" in models else None
    if hw is not None:
        log.info("holt-winters parameters fitted (%d stores fell back to seasonal naive)", hw.n_fallback)
    ml_model, ml_group_start = None, -1
    rows = []
    for k, o_idx in enumerate(idx):
        c = o_idx - 1
        log.info("origin %d/%d: %s", k + 1, len(idx), origins[k].date())
        preds = baseline_forecasts(panel, c)
        n_t = preds["naive"].shape[1]
        if hw is not None:
            preds["hw"] = hw.forecast(c, HORIZON, preds["snaive4"])
        if "ml" in models:
            if k % ML_REFIT_EVERY == 0:
                ml_model = fit_ml(panel, refit_idx=o_idx, first_origin=ml_first_origin)
                ml_group_start = o_idx
            assert ml_group_start <= o_idx
            preds["ml"] = ml_forecast(panel, ml_model, c)
        t = c + 1 + np.arange(n_t)
        frame = pd.DataFrame({
            "store": np.repeat(panel.stores, n_t),
            "origin": origins[k],
            "h": np.tile(np.arange(1, n_t + 1), panel.n_stores),
            "date": np.tile(panel.dates[t].to_numpy(), panel.n_stores),
            "promo": panel.promo[:, t].ravel(),
            "dow": np.tile(panel.dow()[t], panel.n_stores),
            "actual": panel.sales[:, t].ravel(),
            "scored": panel.observed[:, t].ravel(),
        })
        frame["oracle"] = frame["actual"]
        for name in models:
            frame[name] = preds[name].ravel()
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def horizon_band(h: pd.Series | np.ndarray) -> np.ndarray:
    h = np.asarray(h)
    return np.where(h <= 3, "short_h1-3", np.where(h <= 7, "mid_h4-7", "long_h8-14"))
