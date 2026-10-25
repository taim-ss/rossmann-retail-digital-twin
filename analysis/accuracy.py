"""Accuracy tables: WAPE and bias per model, segment and horizon band, each with a store-level bootstrap CI."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import horizon_band
from .metrics import bias, store_bootstrap_ci, wape
from .panel import Panel

SCORED_MODELS = ("naive", "snaive1", "snaive4", "hw", "ml")
N_BOOT = 2000
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def attach_segments(bt: pd.DataFrame, panel: Panel) -> pd.DataFrame:
    seg = panel.attrs[["store_type", "assortment", "volume_tercile"]].rename_axis("store").reset_index()
    out = bt.merge(seg, on="store", how="left")
    out["weekday"] = np.array(WEEKDAYS)[out["dow"].to_numpy()]
    out["promo_label"] = np.where(out["promo"], "promo", "non-promo")
    out["band"] = horizon_band(out["h"])
    return out


def _segment_levels(df: pd.DataFrame):
    yield "all", "all", df
    for dim, col in (("store_type", "store_type"), ("assortment", "assortment"), ("promo", "promo_label"),
                     ("weekday", "weekday"), ("volume_tercile", "volume_tercile")):
        for level, part in df.groupby(col, observed=True):
            yield dim, str(level), part


def accuracy_table(bt: pd.DataFrame, panel: Panel, models=SCORED_MODELS, n_boot: int = N_BOOT) -> pd.DataFrame:
    """One row per (model, segment dimension, level, horizon band) with WAPE, bias and 95 percent store-bootstrap CIs."""
    df = attach_segments(bt[bt["scored"]], panel)
    rows = []
    for band_name, band_df in (("pooled_h1-14", df), *[(b, d) for b, d in df.groupby("band")]):
        for dim, level, part in _segment_levels(band_df):
            for model in ("oracle", *models):
                frame = pd.DataFrame({"store": part["store"], "actual": part["actual"], "forecast": part[model]})
                w, w_lo, w_hi = store_bootstrap_ci(frame, wape, n_boot=n_boot, seed=11)
                b, b_lo, b_hi = store_bootstrap_ci(frame, bias, n_boot=n_boot, seed=12)
                rows.append({"model": model, "segment_dim": dim, "segment": level, "horizon_band": band_name,
                             "n_store_days": len(part), "n_stores": part["store"].nunique(),
                             "wape": w, "wape_lo": w_lo, "wape_hi": w_hi, "bias": b, "bias_lo": b_lo, "bias_hi": b_hi})
    return pd.DataFrame(rows)


def best_model_summary(table: pd.DataFrame) -> pd.DataFrame:
    """Pooled h1-14 WAPE per model, ranked, so the README can quote one honest table (oracle excluded)."""
    pooled = table[(table["segment_dim"] == "all") & (table["horizon_band"] == "pooled_h1-14")
                   & (table["model"] != "oracle")]
    return pooled.sort_values("wape")[["model", "wape", "wape_lo", "wape_hi", "bias", "bias_lo", "bias_hi"]]
