"""Analyse the policy sweep and the lead-time sensitivity of the P2 model, with a replica check of every AnyLogic run.

Question: at equal service, how much stock does each ordering rule need? (Forecast-driven order-up-to with oracle / naive /
ML forecasts versus a static rule sized once from the 2013-2014 average and spread.) Fill rate and mean on-hand stock come from
the native AnyLogic logs; the replica re-implements the same logic in Python and must agree with every log.

Usage: python p2_sweeps.py --logs results/native/pol01 --out results/analysis/sweep
       python p2_sweeps.py --logs results/native/lt01 --out results/analysis/leadtime --mode leadtime
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from p2_analysis import JavaRandom, load_inputs
from project_paths import DATA_DIR

COLS = ["seed", "source", "kpi_days", "demand", "sold", "lost", "fill", "stockout_days", "mean_on_hand", "orders", "hold_cost",
        "short_cost", "order_cost", "total_cost", "sigma", "on_hand_start", "end_time", "policy", "z", "L"]
ARM = {(1, 0): "static", (1, 1): "static", (1, 2): "static", (0, 0): "oracle", (0, 1): "naive", (0, 2): "ml"}


def read_runs(log_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(log_dir.glob("p2-store*-pol*-src*-z*-L*-seed*.log")):
        done = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("P2_DONE,")]
        if len(done) != 1:
            raise ValueError(f"{path.name}: expected one P2_DONE marker, found {len(done)}")
        rows.append(dict(zip(COLS, (float(v) for v in done[0].split(",")[1:]))) | {"file": path.name})
    df = pd.DataFrame(rows)
    for c in ("seed", "source", "policy", "kpi_days", "orders", "stockout_days"):
        df[c] = df[c].astype(int)
    df["arm"] = [ARM[(p, s)] for p, s in zip(df["policy"], df["source"])]
    # a static run does not depend on the forecast source: keep one copy per (z, L, seed)
    df = df[(df["policy"] == 0) | (df["source"] == 0)].reset_index(drop=True)
    return df


def static_stats(data_dir: Path, store: int, start="2013-01-01", end="2014-12-31") -> tuple[float, float]:
    d = pd.read_csv(data_dir / "store_day_demand.csv")
    d = d[(d["store"] == store) & d["date"].between(start, end)]["actual_sales_units"].to_numpy(float)
    return float(d.mean()), float(math.sqrt(max(0.0, (d ** 2).mean() - d.mean() ** 2)))


def replica(n, demand, fc, err, sm, ssd, policy, source, seed, z, L, R=7, h=0.25, m=0.30, K=50.0, p=1.0, hmin=5, hmax=11,
            promo=None):
    if policy == 1 or source == 0:
        sigma = 0.0
    else:
        e = err[(err["model"] == ("naive" if source == 1 else "ml")) & err["horizon"].between(hmin, hmax)]["error"].to_numpy(float)
        sigma = math.sqrt(float((e ** 2).sum()) / max(1, len(e)))
    rng = JavaRandom(20000 + seed)
    warm = R + math.ceil(L)
    on_hand = float(demand[:warm].sum())
    on_order = 0.0
    pend: list[tuple[int, float]] = []
    kd = orders = so = 0
    sd = ss = sl = so_h = hold = short = ordc = 0.0
    promo_demand = promo_sold = nonpromo_demand = nonpromo_sold = 0.0
    for d in range(n):
        for day, q in [x for x in pend if x[0] == d]:
            on_hand += q
            on_order -= q
        pend = [x for x in pend if x[0] != d]
        dem = demand[d]
        sold = min(on_hand, dem)
        lost = dem - sold
        on_hand -= sold
        if d >= warm:
            kd += 1
            sd += dem
            ss += sold
            sl += lost
            so += lost > 1e-9
            so_h += on_hand
            hold += on_hand * p * (1 - m) * h / 365.0
            short += lost * m * p
        if d % R == 0:
            u = rng.next_double()
            lt = max(1, int(round(L)) + (-1 if u < 0.25 else (1 if u > 0.75 else 0)))
            if policy == 1:
                target = sm * warm + z * ssd * math.sqrt(R + L)
            else:
                target = fc[source][d + 1: d + warm + 1].sum() + z * sigma * math.sqrt(R + L)
            if d + lt < n:
                q = max(0.0, target - (on_hand + on_order))
                if q > 0:
                    on_order += q
                    pend.append((d + lt, q))
                    if d >= warm:
                        orders += 1
                        ordc += K
        if d >= warm and promo is not None:
            if promo[d]:
                promo_demand += dem
                promo_sold += sold
            else:
                nonpromo_demand += dem
                nonpromo_sold += sold
    result = {"demand": sd, "sold": ss, "lost": sl, "fill": ss / sd if sd else 1.0, "stockout_days": so,
            "mean_on_hand": so_h / max(kd, 1), "orders": orders, "hold_cost": hold, "short_cost": short, "order_cost": ordc,
            "total_cost": hold + short + ordc}
    if promo is not None:
        result.update(promo_fill=promo_sold/promo_demand if promo_demand else 1.0,
                      nonpromo_fill=nonpromo_sold/nonpromo_demand if nonpromo_demand else 1.0)
    return result


def interpolate_stock(g: pd.DataFrame, target: float) -> float:
    """Mean on-hand stock needed to reach `target` fill on this arm's z-grid (linear interpolation; NaN if not reached)."""
    g = g.sort_values("mean_on_hand")
    x, y = g["mean_on_hand"].to_numpy(), g["fill"].to_numpy()
    if y.max() < target:
        return float("nan")
    if y.min() >= target:
        return float(x.min())
    i = int(np.argmax(y >= target))
    return float(x[i - 1] + (target - y[i - 1]) * (x[i] - x[i - 1]) / (y[i] - y[i - 1]))


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--logs", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--mode", choices=["sweep", "leadtime"], default="sweep")
    cli.add_argument("--data-dir", type=Path, default=DATA_DIR)
    cli.add_argument("--store", type=int, default=164)
    args = cli.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    df = read_runs(args.logs)
    n, demand, fc, err = load_inputs(args.data_dir, args.store, "2015-01-05", "2015-06-24")
    sm, ssd = static_stats(args.data_dir, args.store)
    # --- cross-tool check of every run
    worst = 0.0
    bad = []
    for r in df.itertuples():
        rep = replica(n, demand, fc, err, sm, ssd, r.policy, r.source, r.seed, r.z, r.L)
        diff = max(abs(getattr(r, k) - v) for k, v in rep.items())
        worst = max(worst, diff)
        if diff > 1e-6:
            bad.append(r.file)
    info = {"runs": int(len(df)), "replica_max_abs_diff": worst, "replica_runs_over_1e-6": len(bad),
            "static_mean_per_day": sm, "static_sd_per_day": ssd, "end_times": sorted(set(df["end_time"]))}
    # --- summaries by arm and parameter
    keys = ["arm", "z"] if args.mode == "sweep" else ["arm", "L"]
    rows = []
    for k, g in df.groupby(keys):
        row = dict(zip(keys, k)) | {"n_seeds": len(g)}
        for mname in ("fill", "stockout_days", "mean_on_hand", "orders", "hold_cost", "short_cost", "total_cost"):
            v = g[mname].to_numpy(float)
            half = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / math.sqrt(len(v)) if len(v) > 1 else float("nan")
            row[mname], row[mname + "_ci95"] = v.mean(), half
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(args.out / "summary_by_arm.csv", index=False)
    if args.mode == "sweep":
        need = []
        for arm, g in summary.groupby("arm"):
            need.append({"arm": arm} | {f"stock_for_{int(t * 100)}pct_fill": interpolate_stock(g, t) for t in (0.90, 0.95, 0.99)})
        need_df = pd.DataFrame(need)
        need_df.to_csv(args.out / "stock_needed_for_service.csv", index=False)
        info["stock_needed"] = need_df.round(0).to_dict(orient="records")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7.5, 4.6))
        colors = {"static": "#b5452e", "oracle": "#7a8b99", "ml": "#2f6f9f", "naive": "#c98a3a"}
        for arm in ("static", "naive", "ml", "oracle"):
            g = summary[summary.arm == arm].sort_values("z")
            ax.plot(g["mean_on_hand"] / 1000, g["fill"] * 100, marker="o", label=arm, color=colors[arm])
        ax.set_xlabel("Mean stock on hand (thousand units; 1 unit = EUR 1 of turnover)")
        ax.set_ylabel("Fill rate, % of demand served")
        ax.set_title("P2, store 164: service versus stock by ordering rule (points = safety factor 0 to 2.5)", fontsize=9)
        ax.grid(alpha=0.3)
        ax.legend(title="rule / forecast", fontsize=8)
        fig.text(0.5, 0.005, "Native AnyLogic runs, 5 lead-time seeds per point. Agent-built educational model; costs and lead times are ASSUMPTIONS.",
                 ha="center", fontsize=6.5)
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        fig.savefig(args.out / "service_vs_stock.png", dpi=150)
    else:
        # margin sensitivity from the logs: holding cost scales with (1-m), lost-margin cost with m (exact recompute)
        mrows = []
        for r in df.itertuples():
            for mm in (0.15, 0.30, 0.50):
                hold = r.hold_cost * (1 - mm) / (1 - 0.30)
                short = r.lost * mm * 1.0
                mrows.append({"arm": r.arm, "L": r.L, "margin": mm, "seed": r.seed, "total_cost": hold + short + r.order_cost})
        pd.DataFrame(mrows).groupby(["arm", "L", "margin"], as_index=False)["total_cost"].mean().to_csv(
            args.out / "total_cost_by_margin.csv", index=False)
    (args.out / "analysis.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
    print(json.dumps(info, indent=2, default=str))
    pd.set_option("display.width", 220)
    print(summary[keys + ["fill", "stockout_days", "mean_on_hand", "total_cost"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
