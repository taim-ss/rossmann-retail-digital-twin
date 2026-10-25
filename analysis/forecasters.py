"""Point forecasters. Every function receives a Panel and a cutoff index `c` (the last day whose sales are known)
and predicts the days c+1 .. c+H. Targets on closed days are forecast as 0 and are never scored.

Models
  naive      last observed open day (persistence). Plain "yesterday" would be 0 every Monday after a closed Sunday.
  snaive1    most recent observed same weekday before the cutoff (lag 7, 14 or 21 as the horizon requires)
  snaive4    mean of the 4 most recent observed same weekdays before the cutoff
  hw         Holt-Winters (additive damped trend, weekly season) per store, parameters frozen at `fit_cutoff`
  ml         one global HistGradientBoostingRegressor with origin-anchored features (see ml_features)
Same-weekday lags are taken relative to the CUTOFF, not to the target date, so a 14-day horizon never reads a
sales value from inside its own forecast window.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .panel import Panel

HORIZON = 14
WEEKS_BACK = 8


def target_idx(c: int, horizon: int = HORIZON) -> np.ndarray:
    return c + 1 + np.arange(horizon)


def same_dow_history(panel: Panel, c: int, k: int = 4) -> np.ndarray:
    """(S, 7, k): the k most recent observed sales for each weekday up to and including day c (NaN padded)."""
    dow = panel.dow()
    out = np.full((panel.n_stores, 7, k), np.nan)
    obs = panel.observed
    for d in range(7):
        idx = np.where(dow[: c + 1] == d)[0][-WEEKS_BACK:][::-1]  # newest first
        if len(idx) == 0:
            continue
        vals = np.where(obs[:, idx], panel.sales[:, idx], np.nan)  # (S, <=8)
        for s in range(panel.n_stores):
            good = vals[s][~np.isnan(vals[s])][:k]
            out[s, d, : len(good)] = good
    return out


def last_observed(panel: Panel, c: int) -> np.ndarray:
    obs = panel.observed[:, : c + 1]
    sales = panel.sales[:, : c + 1]
    out = np.full(panel.n_stores, np.nan)
    for s in range(panel.n_stores):
        pos = np.flatnonzero(obs[s])
        if len(pos):
            out[s] = sales[s, pos[-1]]
    return out


def baseline_forecasts(panel: Panel, c: int, horizon: int = HORIZON) -> dict[str, np.ndarray]:
    """naive / snaive1 / snaive4 as (S, horizon) arrays, 0 where the target day is closed."""
    t = target_idx(c, horizon)
    t = t[t < len(panel.dates)]
    hist = same_dow_history(panel, c, 4)
    dow_t = panel.dow()[t]
    snaive1 = hist[:, dow_t, 0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN weekdays (never open) fall back to `last` below
        snaive4 = np.nanmean(hist[:, dow_t, :], axis=2)
    last = last_observed(panel, c)
    naive = np.repeat(last[:, None], len(t), axis=1)
    closed = ~panel.open[:, t]
    out = {}
    for name, arr in (("naive", naive), ("snaive1", snaive1), ("snaive4", snaive4)):
        arr = np.where(np.isnan(arr), np.where(np.isnan(last[:, None]), 0.0, last[:, None]), arr)
        out[name] = np.where(closed, 0.0, arr)
    return out


# ---------------------------------------------------------------- Holt-Winters (frozen parameters)

def filled_series(panel: Panel, c: int, regular_closed: np.ndarray) -> np.ndarray:
    """Calendar series through day c where irregular closures (holidays, refurbishment) are replaced by the value
    one week earlier, so a weekly seasonal model is not dragged by zeros it should not learn.
    Weekdays a store never trades (e.g. Sunday) stay 0: that zero is a real part of its weekly pattern."""
    dow = panel.dow()
    y = panel.sales[:, : c + 1].copy()
    bad = ~panel.observed[:, : c + 1] & ~regular_closed[:, dow[: c + 1]]
    level = np.array([np.nanmean(np.where(panel.observed[s, : c + 1], y[s], np.nan)) if panel.observed[s, : c + 1].any()
                      else 0.0 for s in range(panel.n_stores)])
    for t in range(c + 1):
        if t >= 7:
            y[:, t] = np.where(bad[:, t], y[:, t - 7], y[:, t])
        else:
            y[:, t] = np.where(bad[:, t], level, y[:, t])
    return y


def regular_closed_weekdays(panel: Panel, fit_cutoff: int) -> np.ndarray:
    """(S, 7) True where a store is open on fewer than 10 percent of that weekday's non-holiday days up to fit_cutoff."""
    dow = panel.dow()
    out = np.zeros((panel.n_stores, 7), dtype=bool)
    for d in range(7):
        cols = np.where((dow[: fit_cutoff + 1] == d))[0]
        usable = ~panel.holiday[:, cols] & ~panel.long_closure[:, cols]
        share = (panel.open[:, cols] & usable).sum(axis=1) / np.maximum(usable.sum(axis=1), 1)
        out[:, d] = share < 0.10
    return out


@dataclass
class HoltWintersBank:
    """Per-store Holt-Winters. Smoothing parameters are estimated once on data up to fit_cutoff; at each later
    origin the state is re-filtered with those frozen parameters (no look-ahead, and fast)."""

    panel: Panel
    fit_cutoff: int
    params: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)
    regular_closed: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # local import: slow to load

        self._es = ExponentialSmoothing
        self.regular_closed = regular_closed_weekdays(self.panel, self.fit_cutoff)
        y = filled_series(self.panel, self.fit_cutoff, self.regular_closed)
        for s in range(self.panel.n_stores):
            series = self._trim(y[s], s, self.fit_cutoff)
            if series is None:
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    res = self._es(series, trend="add", damped_trend=True, seasonal="add", seasonal_periods=7,
                                   initialization_method="heuristic").fit()
                p = res.params
                self.params[s] = (float(p["smoothing_level"]), float(p["smoothing_trend"]),
                                  float(p["smoothing_seasonal"]), float(p["damping_trend"]))
            except Exception:  # noqa: BLE001 - a failed fit falls back to seasonal naive, counted in `n_fallback`
                continue

    def _trim(self, series: np.ndarray, s: int, c: int) -> np.ndarray | None:
        pos = np.flatnonzero(self.panel.observed[s, : c + 1])
        if len(pos) < 35:
            return None
        return series[pos[0]: c + 1]

    @property
    def n_fallback(self) -> int:
        return self.panel.n_stores - len(self.params)

    def forecast(self, c: int, horizon: int, fallback: np.ndarray) -> np.ndarray:
        y = filled_series(self.panel, c, self.regular_closed)
        t = target_idx(c, horizon)
        t = t[t < len(self.panel.dates)]
        out = fallback[:, : len(t)].copy()
        for s, (a, b, g, phi) in self.params.items():
            series = self._trim(y[s], s, c)
            if series is None:
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    res = self._es(series, trend="add", damped_trend=True, seasonal="add", seasonal_periods=7,
                                   initialization_method="heuristic").fit(
                        smoothing_level=a, smoothing_trend=b, smoothing_seasonal=g, damping_trend=phi, optimized=False)
                    out[s] = np.clip(res.forecast(len(t)), 0.0, None)
            except Exception:  # noqa: BLE001
                continue
        return np.where(~self.panel.open[:, t], 0.0, out)


# ---------------------------------------------------------------- gradient boosting

ML_FEATURES = (
    "h", "dow", "month", "dom", "doy", "promo", "promo_prev", "holiday", "holiday_next", "holiday_prev", "school",
    "promo2", "store_type", "assortment", "competition_distance",
    "sd_last1", "sd_mean4", "mean28", "mean91", "std28", "promo_mean91", "nonpromo_mean91", "promo_share28",
)
FORBIDDEN_FEATURES = ("Sales", "Customers", "sales", "customers", "actual")


def _trailing(panel: Panel, c: int, window: int, only_promo: bool | None = None) -> np.ndarray:
    lo = max(0, c + 1 - window)
    obs = panel.observed[:, lo: c + 1] & ~panel.holiday[:, lo: c + 1]
    if only_promo is not None:
        obs = obs & (panel.promo[:, lo: c + 1] == only_promo)
    vals = np.where(obs, panel.sales[:, lo: c + 1], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return vals


def ml_features(panel: Panel, c: int, horizon: int = HORIZON) -> pd.DataFrame:
    """Feature rows for every (store, h) at cutoff c. Only the calendar of the target day and sales up to c are used."""
    t = target_idx(c, horizon)
    keep = t < len(panel.dates)
    t = t[keep]
    h = np.arange(1, horizon + 1)[keep]
    S, H = panel.n_stores, len(t)
    dates = panel.dates[t]
    hist = same_dow_history(panel, c, 4)
    dow_t = panel.dow()[t]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m28 = np.nanmean(_trailing(panel, c, 28), axis=1)
        m91 = np.nanmean(_trailing(panel, c, 91), axis=1)
        s28 = np.nanstd(_trailing(panel, c, 28), axis=1)
        pm91 = np.nanmean(_trailing(panel, c, 91, True), axis=1)
        nm91 = np.nanmean(_trailing(panel, c, 91, False), axis=1)
        sd_mean4 = np.nanmean(hist[:, dow_t, :], axis=2)
    promo28 = panel.promo[:, max(0, c - 27): c + 1].mean(axis=1)

    def calendar(arr: np.ndarray, shift: int) -> np.ndarray:
        idx = np.clip(t + shift, 0, len(panel.dates) - 1)
        return arr[:, idx].astype(float)

    def tile(v: np.ndarray) -> np.ndarray:
        return np.repeat(v[:, None], H, axis=1)

    attrs = panel.attrs
    cols = {
        "h": np.tile(h, (S, 1)), "dow": np.tile(dow_t, (S, 1)), "month": np.tile(dates.month.to_numpy(), (S, 1)),
        "dom": np.tile(dates.day.to_numpy(), (S, 1)), "doy": np.tile(dates.dayofyear.to_numpy(), (S, 1)),
        "promo": calendar(panel.promo, 0), "promo_prev": calendar(panel.promo, -1),
        "holiday": calendar(panel.holiday, 0), "holiday_next": calendar(panel.holiday, 1),
        "holiday_prev": calendar(panel.holiday, -1), "school": calendar(panel.school, 0),
        "promo2": tile(attrs["promo2"].to_numpy(float)),
        "store_type": tile(attrs["store_type"].astype("category").cat.codes.to_numpy(float)),
        "assortment": tile(attrs["assortment"].astype("category").cat.codes.to_numpy(float)),
        "competition_distance": tile(attrs["competition_distance"].to_numpy(float)),
        "sd_last1": hist[:, dow_t, 0], "sd_mean4": sd_mean4,
        "mean28": tile(m28), "mean91": tile(m91), "std28": tile(s28),
        "promo_mean91": tile(pm91), "nonpromo_mean91": tile(nm91), "promo_share28": tile(promo28),
    }
    frame = pd.DataFrame({k: v.ravel() for k, v in cols.items()})[list(ML_FEATURES)]
    frame.insert(0, "store_pos", np.repeat(np.arange(S), H))
    frame.insert(1, "t_idx", np.tile(t, S))
    return frame


def training_frame(panel: Panel, first_origin: int, refit_idx: int, step: int = 7) -> tuple[pd.DataFrame, np.ndarray]:
    """Training rows from weekly origins; a row is used only if its target day is before `refit_idx`."""
    frames = []
    for o in range(first_origin, refit_idx - 1, step):
        f = ml_features(panel, o - 1)
        f = f[f["t_idx"] < refit_idx]
        if not f.empty:
            frames.append(f)
    frame = pd.concat(frames, ignore_index=True)
    s, t = frame["store_pos"].to_numpy(), frame["t_idx"].to_numpy()
    usable = panel.observed[s, t]
    frame = frame[usable]
    y = panel.sales[s[usable], t[usable]]
    return frame, y


def fit_ml(panel: Panel, refit_idx: int, first_origin: int = 91, seed: int = 0) -> HistGradientBoostingRegressor:
    x, y = training_frame(panel, first_origin, refit_idx)
    assert set(FORBIDDEN_FEATURES).isdisjoint(ML_FEATURES)
    assert x["t_idx"].max() < refit_idx, "training target at or after the refit point: leakage"
    model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=63, min_samples_leaf=40, l2_regularization=1.0,
        categorical_features=[list(ML_FEATURES).index(c) for c in ("store_type", "assortment")], random_state=seed)
    model.fit(x[list(ML_FEATURES)], y)
    return model


def ml_forecast(panel: Panel, model: HistGradientBoostingRegressor, c: int, horizon: int = HORIZON) -> np.ndarray:
    f = ml_features(panel, c, horizon)
    pred = np.clip(model.predict(f[list(ML_FEATURES)]), 0.0, None)
    H = len(f) // panel.n_stores
    pred = pred.reshape(panel.n_stores, H)
    t = f["t_idx"].to_numpy().reshape(panel.n_stores, H)[0]
    return np.where(~panel.open[:, t], 0.0, pred)
