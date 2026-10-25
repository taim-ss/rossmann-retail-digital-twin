"""Analyse the native AnyLogic logs of the P2 model and cross-check them against an independent Python replica.

Replica = the same daily order-up-to logic written again in Python from the P1 CSV files, with java.util.Random re-implemented
so the lead-time stream (the only random input) is reproduced without reading it from AnyLogic. If the replica and AnyLogic
agree to rounding on every run, the model logic and the common-random-number stream are verified for this store.

Usage: python p2_analysis.py --logs results/native/pv02 --data-dir <P1 outputs> --out results/analysis
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from project_paths import DATA_DIR

DONE_COLS = ["seed", "source", "kpi_days", "demand", "sold", "lost", "fill", "stockout_days", "mean_on_hand", "orders",
             "hold_cost", "short_cost", "order_cost", "total_cost", "sigma", "on_hand_start", "end_time"]
SOURCE = {0: "oracle", 1: "naive", 2: "ml"}


class JavaRandom:
    """java.util.Random (48-bit LCG), enough for nextDouble."""
    MASK = (1 << 48) - 1

    def __init__(self, seed: int):
        self.seed = (seed ^ 0x5DEECE66D) & self.MASK

    def _next(self, bits: int) -> int:
        self.seed = (self.seed * 0x5DEECE66D + 0xB) & self.MASK
        return self.seed >> (48 - bits)

    def next_double(self) -> float:
        return ((self._next(26) << 27) + self._next(27)) * (1.0 / (1 << 53))


def read_runs(log_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(log_dir.glob("p2-store*-src*-seed*.log")):
        text = path.read_text(encoding="utf-8")
        done = [ln for ln in text.splitlines() if ln.startswith("P2_DONE,")]
        if len(done) != 1:
            raise ValueError(f"{path.name}: expected one P2_DONE marker, found {len(done)}")
        vals = done[0].split(",")[1:]
        row = dict(zip(DONE_COLS, (float(v) for v in vals)))
        row["file"] = path.name
        row["cfg"] = next(ln for ln in text.splitlines() if ln.startswith("P2_CONFIG,"))
        rows.append(row)
    df = pd.DataFrame(rows)
    df["seed"], df["source"] = df["seed"].astype(int), df["source"].astype(int)
    return df


def load_inputs(data_dir: Path, store: int, first: str, last: str):
    days = pd.date_range(first, last)
    n = len(days)
    dem = pd.read_csv(data_dir / "store_day_demand.csv")
    dem = dem[dem["store"] == store].set_index("date")["actual_sales_units"]
    demand = dem.reindex(days.strftime("%Y-%m-%d")).to_numpy(float)
    fc = []
    for name in ("forecast_oracle.csv", "forecast_naive.csv", "forecast_ml.csv"):
        f = pd.read_csv(data_dir / name)
        f = f[f["store"] == store].set_index("date")["forecast_mean"]
        fc.append(f.reindex(days.strftime("%Y-%m-%d")).to_numpy(float))
    assert not np.isnan(demand).any() and not any(np.isnan(x).any() for x in fc)
    err = pd.read_csv(data_dir / "forecast_error_distribution.csv")
    return n, demand, np.vstack(fc), err[err["store"] == store]


def replica(n, demand, fc, err, source, seed, L=5.0, R=7, h=0.25, m=0.30, K=50.0, p=1.0, z=1.6448536269514722,
            hmin=5, hmax=11) -> dict:
    if source == 0:
        sigma = 0.0
    else:
        e = err[(err["model"] == ("naive" if source == 1 else "ml")) & err["horizon"].between(hmin, hmax)]["error"].to_numpy(float)
        sigma = math.sqrt(float((e ** 2).sum()) / max(1, len(e)))
    rng = JavaRandom(20000 + seed)
    warm = R + math.ceil(L)
    on_hand = float(demand[:warm].sum())
    start, on_order = on_hand, 0.0
    pending: list[tuple[int, float]] = []
    k_days = orders = stockout = 0
    s_dem = s_sold = s_lost = s_oh = hold = short = ordc = 0.0
    draws = []
    for d in range(n):
        for arr_day, qty in [x for x in pending if x[0] == d]:
            on_hand += qty
            on_order -= qty
        pending = [x for x in pending if x[0] != d]
        dem = demand[d]
        sold = min(on_hand, dem)
        lost = dem - sold
        on_hand -= sold
        if d >= warm:
            k_days += 1
            s_dem += dem
            s_sold += sold
            s_lost += lost
            stockout += lost > 1e-9
            s_oh += on_hand
            hold += on_hand * p * (1 - m) * h / 365.0
            short += lost * m * p
        if d % R == 0:
            u = rng.next_double()
            lt = max(1, int(round(L)) + (-1 if u < 0.25 else (1 if u > 0.75 else 0)))
            draws.append((u, lt))
            target = fc[source][d + 1: d + warm + 1].sum() + z * sigma * math.sqrt(R + L)
            if d + lt < n:
                qty = max(0.0, target - (on_hand + on_order))
                if qty > 0:
                    on_order += qty
                    pending.append((d + lt, qty))
                    if d >= warm:
                        orders += 1
                        ordc += K
    fill = s_sold / s_dem if s_dem > 0 else 1.0
    total = hold + short + ordc
    return {"kpi_days": k_days, "demand": s_dem, "sold": s_sold, "lost": s_lost, "fill": fill, "stockout_days": stockout,
            "mean_on_hand": s_oh / max(k_days, 1), "orders": orders, "hold_cost": hold, "short_cost": short,
            "order_cost": ordc, "total_cost": total, "sigma": sigma, "on_hand_start": start, "first_draws": draws[:5]}


def paired(df: pd.DataFrame, metric: str, a: int, b: int) -> dict:
    x = df[df.source == a].set_index("seed")[metric]
    y = df[df.source == b].set_index("seed")[metric]
    d = (x - y).dropna()
    n = len(d)
    mean = float(d.mean())
    sd = float(d.std(ddof=1)) if n > 1 else float("nan")
    half = float(stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n)) if n > 1 else float("nan")
    return {"metric": metric, "a": SOURCE[a], "b": SOURCE[b], "n_pairs": n, "mean_diff": mean, "ci95_low": mean - half,
            "ci95_high": mean + half, "rel_half_width": half / abs(mean) if mean else float("nan")}


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--logs", type=Path, required=True)
    cli.add_argument("--data-dir", type=Path, default=DATA_DIR)
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--store", type=int, default=164)
    args = cli.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    df = read_runs(args.logs)
    n, demand, fc, err = load_inputs(args.data_dir, args.store, "2015-01-05", "2015-06-24")
    metrics = ["fill", "stockout_days", "mean_on_hand", "orders", "hold_cost", "short_cost", "order_cost", "total_cost"]
    # --- cross-tool check: replica vs AnyLogic, every run
    checks = []
    for r in df.itertuples():
        rep = replica(n, demand, fc, err, r.source, r.seed)
        diffs = {k: abs(getattr(r, k) - rep[k]) for k in ("demand", "sold", "lost", "fill", "mean_on_hand", "hold_cost", "short_cost",
                                                          "order_cost", "total_cost", "sigma", "on_hand_start")}
        diffs |= {"orders": abs(r.orders - rep["orders"]), "stockout_days": abs(r.stockout_days - rep["stockout_days"])}
        checks.append({"file": r.file, "max_abs_diff": max(diffs.values()), "worst": max(diffs, key=diffs.get)})
    chk = pd.DataFrame(checks)
    # first-5 lead-time draws logged by AnyLogic vs the replica, per seed (CRN: identical across sources)
    crn_ok = True
    for path in sorted(args.logs.glob("p2-store*-src*-seed*.log")):
        lines = [ln.split(",") for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("P2_CRN,")]
        seed = int(lines[0][1])
        rep_draws = replica(n, demand, fc, err, int(lines[0][2]), seed)["first_draws"]
        crn_ok &= all(abs(float(a[4]) - b[0]) < 1e-15 and int(a[5]) == b[1] for a, b in zip(lines, rep_draws))
    by_seed = df.groupby("seed")["file"].count()
    # --- summaries and paired differences
    rows = []
    for src, g in df.groupby("source"):
        for mname in metrics:
            v = g[mname].to_numpy(float)
            half = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / math.sqrt(len(v)) if len(v) > 1 else float("nan")
            rows.append({"source": SOURCE[src], "metric": mname, "n": len(v), "mean": v.mean(), "ci95_half_width": half})
    summary = pd.DataFrame(rows)
    pairs = pd.DataFrame([paired(df, mname, a, b) for mname in metrics for a, b in ((2, 1), (2, 0), (1, 0))])
    summary.to_csv(args.out / "summary_by_source.csv", index=False)
    pairs.to_csv(args.out / "paired_differences.csv", index=False)
    chk.to_csv(args.out / "replica_check.csv", index=False)
    info = {"runs": int(len(df)), "runs_per_seed_min": int(by_seed.min()), "end_time_days_unique": sorted(set(df["end_time"])),
            "replica_max_abs_diff": float(chk["max_abs_diff"].max()), "replica_runs_over_1e-6": int((chk["max_abs_diff"] > 1e-6).sum()),
            "crn_first5_draws_match_java_random": bool(crn_ok)}
    (args.out / "analysis.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))
    pd.set_option("display.width", 200)
    print(summary.pivot(index="metric", columns="source", values="mean").round(3).to_string())
    print(pairs[["metric", "a", "b", "mean_diff", "ci95_low", "ci95_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
