"""Cost of forecast error under an order-up-to policy (design: docs/experiment-design.md section C).

Everything here is ASSUMPTION-driven: Rossmann has no stock, orders, lead times or costs. The functions are the
Python twin of the live formulas in excel/assumptions_and_sensitivity.xlsx; tests assert the two agree.

Unit convention: one "unit" is EUR 1 of daily turnover (the data hold turnover, not physical units).
Unit value p = 1; unit cost c = p (1 - m) because m is the gross margin; a lost sale costs the margin m p.

    SS(sigma)        = z sigma sqrt(R + L)                      safety stock
    Holding(sigma)   = SS * c * h                               yearly cost of carrying that safety stock
    Lz               = phi(z) - z (1 - Phi(z))                  standard normal loss function
    Shortage(sigma)  = (365 / R) sigma sqrt(R + L) Lz * m p     yearly expected lost margin
    Extra(sigma)     = Holding + Shortage = sigma * k
    Finding          = Extra(sigma_promo) - Extra(sigma_nonpromo)

sigma is the root-mean-square daily forecast error (a biased forecaster is penalised, unlike a plain std).
The sqrt(R + L) scaling assumes errors are uncorrelated across days; calibration_table.csv reports Ljung-Box so
the reader can see where that is optimistic.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass(frozen=True)
class Assumptions:
    lead_time_days: float = 5.0
    review_period_days: float = 7.0
    holding_rate: float = 0.25        # per year, of unit cost
    margin: float = 0.30              # gross margin: lost sale costs m p, unit cost is p (1 - m)
    order_cost: float = 50.0          # EUR per order, not part of the finding
    unit_price: float = 1.0           # normalisation: one unit = EUR 1 of turnover
    service_level: float = 0.95       # cycle service level; z = Phi^-1

    @property
    def z(self) -> float:
        return float(norm.ppf(self.service_level))


BASE = Assumptions()
RANGES = {  # parameter -> (low, high), from docs/experiment-design.md C.1
    "lead_time_days": (2.0, 10.0),
    "review_period_days": (1.0, 14.0),
    "holding_rate": (0.15, 0.35),
    "margin": (0.15, 0.50),
    "order_cost": (10.0, 150.0),
}


def loss_function(z: float) -> float:
    return float(norm.pdf(z) - z * (1.0 - norm.cdf(z)))


def k_factor(a: Assumptions) -> float:
    """Extra yearly cost per 1 EUR of daily RMSE: Extra(sigma) = sigma * k."""
    unit_cost = a.unit_price * (1.0 - a.margin)
    cover = np.sqrt(a.review_period_days + a.lead_time_days)
    holding = a.z * unit_cost * a.holding_rate
    shortage = (365.0 / a.review_period_days) * loss_function(a.z) * a.margin * a.unit_price
    return float(cover * (holding + shortage))


def extra_cost(sigma: float | np.ndarray, a: Assumptions = BASE) -> float | np.ndarray:
    return np.asarray(sigma) * k_factor(a) if isinstance(sigma, np.ndarray) else float(sigma) * k_factor(a)


def finding_per_store(sigma_promo: np.ndarray, sigma_nonpromo: np.ndarray, a: Assumptions = BASE) -> np.ndarray:
    return extra_cost(np.asarray(sigma_promo, float), a) - extra_cost(np.asarray(sigma_nonpromo, float), a)


def store_error_inputs(bt: pd.DataFrame, model: str) -> pd.DataFrame:
    """Per-store RMSE of the daily error on promo and non-promo scored days (pooled over horizons 1-14)."""
    d = bt[bt["scored"]].copy()
    d["sq"] = (d["actual"] - d[model]) ** 2
    g = d.groupby(["store", "promo"]).agg(n=("sq", "size"), mse=("sq", "mean"), mean_sales=("actual", "mean")).reset_index()
    wide = g.pivot(index="store", columns="promo", values=["n", "mse", "mean_sales"])
    out = pd.DataFrame({
        "store": wide.index,
        "rmse_promo": np.sqrt(wide[("mse", True)]).to_numpy(),
        "rmse_nonpromo": np.sqrt(wide[("mse", False)]).to_numpy(),
        "n_promo": wide[("n", True)].to_numpy(),
        "n_nonpromo": wide[("n", False)].to_numpy(),
        "mean_daily_sales": d.groupby("store")["actual"].mean().reindex(wide.index).to_numpy(),
    })
    return out.dropna().reset_index(drop=True)


def bootstrap_mean_ci(values: np.ndarray, n_boot: int = 2000, seed: int = 5, level: float = 0.95):
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), size=(n_boot, len(values)))].mean(axis=1)
    lo, hi = np.percentile(means, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(values.mean()), float(lo), float(hi)


def tornado(delta_mean: float, a: Assumptions = BASE) -> pd.DataFrame:
    rows = []
    base = delta_mean * k_factor(a)
    for name, (lo, hi) in RANGES.items():
        f_lo = delta_mean * k_factor(Assumptions(**{**a.__dict__, name: lo}))
        f_hi = delta_mean * k_factor(Assumptions(**{**a.__dict__, name: hi}))
        rows.append({"parameter": name, "low": lo, "high": hi, "finding_low": f_lo, "finding_high": f_hi,
                     "swing": abs(f_hi - f_lo), "base": base})
    return pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)
