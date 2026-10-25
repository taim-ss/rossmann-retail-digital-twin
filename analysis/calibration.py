"""Calibration table: for every simulation input, the fitted distribution, goodness of fit, parameters and source.

Design: docs/experiment-design.md section B. Rules that matter:
  * fits use training-period days only (<= train_end); forecast-error rows use the validation folds;
  * the KS p-value is a parametric-bootstrap (Lilliefors-style) p-value, because a textbook KS table is wrong
    when parameters were estimated from the same sample;
  * a family is accepted only if it has the lowest AIC AND bootstrap p > 0.05; otherwise the row says
    'empirical' (resample the observed values) and the parameters describe the best parametric summary only.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox

from .panel import Panel

COLUMNS = ["store_id", "input_name", "segment", "source_column", "n_obs", "fit_window_start", "fit_window_end",
           "fitted_distribution", "param1_name", "param1_value", "param2_name", "param2_value", "param3_name",
           "param3_value", "goodness_of_fit_stat", "goodness_of_fit_pvalue", "notes_assumption"]
MIN_OBS = 180
ALPHA = 0.05
FAMILIES = ("gamma", "lognormal", "normal")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _fit(family: str, x: np.ndarray) -> tuple[tuple, float, float]:
    """(params, KS statistic, AIC). gamma/lognormal are fitted with location 0 (demand cannot be negative)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if family == "gamma":
            a, _, scale = stats.gamma.fit(x, floc=0)
            params, dist = (a, 0.0, scale), stats.gamma
        elif family == "lognormal":
            s, _, scale = stats.lognorm.fit(x, floc=0)
            params, dist = (s, 0.0, scale), stats.lognorm
        else:
            params, dist = stats.norm.fit(x), stats.norm
        ks = stats.kstest(x, dist.cdf, args=params).statistic
        aic = 2 * len(params if family == "normal" else (params[0], params[2])) - 2 * dist.logpdf(x, *params).sum()
    return params, float(ks), float(aic)


def _sample(family: str, params: tuple, n: int, rng: np.random.Generator) -> np.ndarray:
    if family == "gamma":
        return rng.gamma(params[0], params[2], n)
    if family == "lognormal":
        return rng.lognormal(np.log(params[2]), params[0], n)
    return rng.normal(params[0], params[1], n)


def lilliefors_p(family: str, params: tuple, ks_obs: float, n: int, rng: np.random.Generator, n_boot: int) -> float:
    """Parametric-bootstrap p-value of the KS statistic with parameters re-estimated on every simulated sample."""
    exceed = 0
    for _ in range(n_boot):
        sim = _sample(family, params, n, rng)
        if family != "normal" and sim.min() <= 0:
            continue
        exceed += _fit(family, sim)[1] >= ks_obs
    return (1 + exceed) / (n_boot + 1)


def select_distribution(x: np.ndarray, rng: np.random.Generator, n_boot: int) -> dict:
    fits = {fam: _fit(fam, x) for fam in FAMILIES}
    best = min(fits, key=lambda f: fits[f][2])
    params, ks, aic = fits[best]
    p = lilliefors_p(best, params, ks, len(x), rng, n_boot)
    accepted = p > ALPHA
    return {"family": best, "params": params, "ks": ks, "aic": aic, "p": p, "accepted": accepted,
            "distribution": best if accepted else "empirical"}


def _param_cols(family: str, params: tuple) -> dict:
    if family == "gamma":
        return {"param1_name": "shape", "param1_value": params[0], "param2_name": "scale", "param2_value": params[2],
                "param3_name": "mean", "param3_value": params[0] * params[2]}
    if family == "lognormal":
        return {"param1_name": "sigma_log", "param1_value": params[0], "param2_name": "scale_exp_mu",
                "param2_value": params[2], "param3_name": "mean",
                "param3_value": params[2] * np.exp(params[0] ** 2 / 2)}
    return {"param1_name": "mu", "param1_value": params[0], "param2_name": "sd", "param2_value": params[1],
            "param3_name": "mean", "param3_value": params[0]}


def _row(store, input_name, segment, source, n, start, end, dist, cols, stat, p, note) -> dict:
    row = dict.fromkeys(COLUMNS, np.nan)
    row.update({"store_id": store, "input_name": input_name, "segment": segment, "source_column": source, "n_obs": n,
                "fit_window_start": start, "fit_window_end": end, "fitted_distribution": dist,
                "goodness_of_fit_stat": stat, "goodness_of_fit_pvalue": p, "notes_assumption": note})
    row.update(cols)
    return row


def weekday_indices(panel: Panel, c: int) -> np.ndarray:
    """(S, 7) mean sales on ordinary days of each weekday divided by the store's mean over its open ordinary days."""
    dow = panel.dow()[: c + 1]
    ok = panel.observed[:, : c + 1] & ~panel.holiday[:, : c + 1] & ~panel.promo[:, : c + 1]
    sales = panel.sales[:, : c + 1]
    overall = np.where(ok, sales, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mean_all = np.nanmean(overall, axis=1)
        out = np.zeros((panel.n_stores, 7))
        for d in range(7):
            out[:, d] = np.nanmean(np.where(dow[None, :] == d, overall, np.nan), axis=1) / mean_all
    return np.nan_to_num(out, nan=0.0)


def demand_and_weekday_rows(panel: Panel, train_end: int, n_boot: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    dow = panel.dow()[: train_end + 1]
    ok = panel.observed[:, : train_end + 1] & ~panel.holiday[:, : train_end + 1] & ~panel.promo[:, : train_end + 1]
    sales = panel.sales[:, : train_end + 1]
    widx = weekday_indices(panel, train_end)
    start, end = str(panel.dates[0].date()), str(panel.dates[train_end].date())
    norm_sales = sales / np.where(widx[:, dow] > 0, widx[:, dow], np.nan)  # weekday-normalised demand level
    types = panel.attrs["store_type"].to_numpy()
    rows: list[dict] = []
    pooled_cache: dict[str, dict] = {}
    for s, store in enumerate(panel.stores):
        x = norm_sales[s][ok[s]]
        x = x[np.isfinite(x) & (x > 0)]
        note = "weekday-normalised ordinary days (non-promo, non-holiday, open)"
        segment = "store"
        if len(x) < MIN_OBS:
            seg_type = types[s]
            if seg_type not in pooled_cache:
                pool = norm_sales[(types == seg_type)[:, None] & ok]
                pool = pool[np.isfinite(pool) & (pool > 0)]
                pooled_cache[seg_type] = select_distribution(pool / pool.mean(), rng, n_boot)
            fit, segment = pooled_cache[seg_type], f"store_type_{seg_type}"
            fit = dict(fit)
            note += f"; pooled by StoreType because n<{MIN_OBS} (shape only, scale = store mean)"
            x = x if len(x) else np.array([np.nan])
        else:
            fit = select_distribution(x, rng, n_boot)
        if not fit["accepted"]:
            note += "; parametric family rejected (bootstrap p<=0.05): use empirical resampling"
        cols = _param_cols(fit["family"], fit["params"])
        rows.append(_row(store, "daily_demand_level", segment, "Sales", len(x), start, end, fit["distribution"],
                         cols, fit["ks"], fit["p"], note + f"; best-AIC family={fit['family']}"))
        rows.extend(_weekday_rows(store, s, sales, ok, dow, widx, types, start, end, panel))
    return rows


def _weekday_rows(store, s, sales, ok, dow, widx, types, start, end, panel) -> list[dict]:
    groups = [sales[s][ok[s] & (dow == d)] for d in range(7)]
    usable = [g for g in groups if len(g) >= 10]
    if len(usable) >= 4:
        p = float(stats.kruskal(*usable).pvalue)
        pooled = p >= ALPHA
    else:
        p, pooled = np.nan, True
    same_type = types == types[s]
    rows = []
    for d in range(7):
        factor = widx[s, d]
        note = "store-level factor"
        if len(groups[d]) < 10:
            factor, note = 0.0, "regularly closed or too few open days: factor 0"
        elif pooled:
            factor = float(np.nanmean(widx[same_type, d][widx[same_type, d] > 0]))
            note = "pooled by StoreType (weekday effect not significant or n small)"
        rows.append(_row(store, f"weekday_factor_{DAYS[d]}", "store" if not pooled else f"store_type_{types[s]}",
                         "Sales by DayOfWeek", len(groups[d]), start, end, "multiplier_table", {
                             "param1_name": "factor", "param1_value": factor}, np.nan, p,
                         note + "; p = Kruskal-Wallis across weekdays"))
    return rows


def promo_uplift_rows(panel: Panel, train_end: int, n_boot: int, seed: int, window: int = 28) -> list[dict]:
    """Log ratio of a promo day to the mean of ordinary same-weekday days within +/- `window` days (matched pairs)."""
    rng = np.random.default_rng(seed + 1)
    dow = panel.dow()
    start, end = str(panel.dates[0].date()), str(panel.dates[train_end].date())
    rows = []
    for s, store in enumerate(panel.stores):
        base = panel.observed[s] & ~panel.holiday[s]
        promo_days = np.flatnonzero(base[: train_end + 1] & panel.promo[s, : train_end + 1])
        ordinary = base & ~panel.promo[s]
        log_ratio = []
        for t in promo_days:
            lo, hi = max(0, t - window), min(train_end, t + window)
            ref = [u for u in range(lo, hi + 1) if ordinary[u] and dow[u] == dow[t]]
            if ref and panel.sales[s, t] > 0:
                log_ratio.append(np.log(panel.sales[s, t] / np.mean(panel.sales[s, ref])))
        x = np.asarray(log_ratio)
        if len(x) < 20:
            rows.append(_row(store, "promo_uplift", "store", "Sales (promo vs ordinary same weekday)", len(x), start,
                             end, "none", {}, np.nan, np.nan, "fewer than 20 matched promo days: no fit"))
            continue
        mu, sd = float(x.mean()), float(x.std(ddof=1))
        ks = stats.kstest(x, stats.norm.cdf, args=(mu, sd)).statistic
        p = lilliefors_p("normal", (mu, sd), ks, len(x), rng, n_boot)
        dist = "lognormal_ratio" if p > ALPHA else "empirical"
        rows.append(_row(store, "promo_uplift", "store", "Sales (promo vs ordinary same weekday)", len(x), start, end,
                         dist, {"param1_name": "mu_log_ratio", "param1_value": mu, "param2_name": "sigma_log_ratio",
                                "param2_value": sd, "param3_name": "mean_ratio",
                                "param3_value": float(np.exp(x).mean())}, ks, p,
                         "descriptive uplift under non-random promotion timing, not a causal effect"
                         + ("" if p > ALPHA else "; lognormal rejected: resample observed ratios")))
    return rows


def forecast_error_rows(bt: pd.DataFrame, models: dict[str, str], start: str, end: str) -> list[dict]:
    """Empirical forecast-error summary per store and promo/non-promo, plus Ljung-Box on the h1-7 daily residual series."""
    rows = []
    scored = bt[bt["scored"]]
    for store, g in scored.groupby("store"):
        series = g[g["h"] <= 7].sort_values("date")
        for input_name, col in models.items():
            err = g["actual"] - g[col]  # sign: actual minus forecast
            lb_stat = lb_p = np.nan
            resid = (series["actual"] - series[col]).to_numpy()
            if len(resid) >= 40 and np.std(resid) > 0:
                lb = acorr_ljungbox(resid, lags=[14], return_df=True)
                lb_stat, lb_p = float(lb["lb_stat"].iloc[0]), float(lb["lb_pvalue"].iloc[0])
            for seg, mask in (("all", np.ones(len(g), bool)), ("promo", g["promo"].to_numpy()),
                              ("non-promo", ~g["promo"].to_numpy())):
                e = err[mask]
                if len(e) == 0:
                    continue
                rows.append(_row(
                    store, input_name, seg, f"Sales - forecast ({col})", len(e), start, end, "empirical",
                    {"param1_name": "mean_error", "param1_value": float(e.mean()), "param2_name": "sd_error",
                     "param2_value": float(e.std(ddof=1)) if len(e) > 1 else np.nan, "param3_name": "mean_abs_error",
                     "param3_value": float(e.abs().mean())},
                    lb_stat if seg == "all" else np.nan, lb_p if seg == "all" else np.nan,
                    "empirical residuals are the default export; Ljung-Box (lag 14, h1-7 series) in the 'all' row, "
                    "p<0.05 means the sqrt(R+L) scaling of sd is optimistic" if seg == "all" else "empirical"))
    return rows


def closed_day_rule_row(panel: Panel, train_end: int) -> dict:
    return _row("ALL", "closed_day_rule", "all", "Open, StateHoliday, DayOfWeek", int((~panel.open).sum()),
                str(panel.dates[0].date()), str(panel.dates[train_end].date()), "deterministic_calendar", {},
                np.nan, np.nan, "calendar rule, not a fit: store is closed on regular closed weekdays and state "
                "holidays, and during long closures; open/closed is treated as known in advance (ASSUMPTION)")


def build_calibration_table(panel: Panel, bt: pd.DataFrame, train_end_idx: int, valid_start: str, valid_end: str,
                            error_models: dict[str, str], n_boot: int = 49, seed: int = 20261023) -> pd.DataFrame:
    rows = demand_and_weekday_rows(panel, train_end_idx, n_boot, seed)
    rows += promo_uplift_rows(panel, train_end_idx, n_boot, seed)
    rows += forecast_error_rows(bt, error_models, valid_start, valid_end)
    rows.append(closed_day_rule_row(panel, train_end_idx))
    return pd.DataFrame(rows, columns=COLUMNS)
