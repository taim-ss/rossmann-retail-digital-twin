"""Service-versus-stock frontier and sensitivities, computed with the Python replica of the P2 model.

The replica reproduces every native AnyLogic run it was compared with to 1e-11 (30 runs of the forecast-source comparison plus the
spot checks listed in results/native-spotchecks). The sweep itself is NOT run in AnyLogic: a 180-run Parameter Variation experiment hung
in the headless launch, so the grid below is replica output, confirmed natively at a few points (see compare_spotchecks.py).

Outputs (results/analysis/frontier): frontier_by_arm.csv, stock_needed_for_service.csv, leadtime_sensitivity.csv,
margin_sensitivity.csv, service_vs_stock.png, stock_needed_vs_leadtime.png.
Usage: python p2_frontier.py [--data-dir <P1 outputs>]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from p2_analysis import load_inputs
from p2_sweeps import interpolate_stock, replica, static_stats
from project_paths import DATA_DIR

ARMS = {"static": (1, 0), "naive": (0, 1), "ml": (0, 2), "oracle": (0, 0)}
Z_GRID = [round(z, 2) for z in np.arange(-2.0, 3.01, 0.25)]
SEEDS = range(1, 11)
TARGETS = (0.90, 0.95, 0.99)


def run_grid(inputs, L: float, zs, seeds):
    n, demand, fc, err, sm, ssd = inputs
    rows = []
    for arm, (policy, source) in ARMS.items():
        for z in zs:
            for seed in seeds:
                r = replica(n, demand, fc, err, sm, ssd, policy, source, seed, z, L)
                rows.append({"arm": arm, "z": z, "L": L, "seed": seed, **r})
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["arm", "z", "L"]
    g = df.groupby(keys, as_index=False).agg(fill=("fill", "mean"), stockout_days=("stockout_days", "mean"),
                                             mean_on_hand=("mean_on_hand", "mean"), total_cost=("total_cost", "mean"),
                                             hold_cost=("hold_cost", "mean"), short_cost=("short_cost", "mean"),
                                             fill_sd=("fill", "std"))
    return g


def stock_needed(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (arm, L), g in summary.groupby(["arm", "L"]):
        rows.append({"arm": arm, "L": L} | {f"stock_for_{int(t * 100)}pct_fill": interpolate_stock(g, t) for t in TARGETS})
    return pd.DataFrame(rows)


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--data-dir", type=Path, default=DATA_DIR)
    cli.add_argument("--store", type=int, default=164)
    args = cli.parse_args()
    out = Path(__file__).resolve().parents[1] / "results" / "analysis" / "frontier"
    out.mkdir(parents=True, exist_ok=True)
    n, demand, fc, err = load_inputs(args.data_dir, args.store, "2015-01-05", "2015-06-24")
    sm, ssd = static_stats(args.data_dir, args.store)
    inputs = (n, demand, fc, err, sm, ssd)
    base = run_grid(inputs, 5.0, Z_GRID, SEEDS)
    summ = summarise(base)
    summ.to_csv(out / "frontier_by_arm.csv", index=False)
    need = stock_needed(summ)
    need.to_csv(out / "stock_needed_for_service.csv", index=False)
    # lead-time sensitivity: stock needed for target service for each L
    all_need = [need]
    lt_rows = []
    for L in (3.0, 7.0, 9.0):
        s = summarise(run_grid(inputs, L, Z_GRID, SEEDS))
        all_need.append(stock_needed(s))
        lt_rows.append(s)
    lt = pd.concat([summ] + lt_rows, ignore_index=True)
    lt.to_csv(out / "frontier_all_leadtimes.csv", index=False)
    need_lt = pd.concat(all_need, ignore_index=True)
    need_lt.to_csv(out / "leadtime_sensitivity.csv", index=False)
    # margin sensitivity at a fixed safety factor 1.0, L = 5: holding scales with (1-m), lost margin with m
    marg = []
    for r in base[(base.z == 1.0)].itertuples():
        for mm in (0.15, 0.30, 0.50):
            total = r.hold_cost * (1 - mm) / (1 - 0.30) + r.lost * mm + r.order_cost
            marg.append({"arm": r.arm, "margin": mm, "total_cost": total})
    pd.DataFrame(marg).groupby(["arm", "margin"], as_index=False)["total_cost"].mean().to_csv(out / "margin_sensitivity.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"static": "#b5452e", "oracle": "#7a8b99", "ml": "#2f6f9f", "naive": "#c98a3a"}
    fig, ax = plt.subplots(figsize=(7.8, 4.7))
    for arm in ("static", "naive", "ml", "oracle"):
        g = summ[summ.arm == arm].sort_values("z")
        ax.plot(g["mean_on_hand"] / 1000, g["fill"] * 100, marker="o", ms=3.5, label=arm, color=colors[arm])
    ax.set_xlabel("Mean stock on hand (thousand units; 1 unit = EUR 1 of turnover)")
    ax.set_ylabel("Fill rate (% of demand served)")
    ax.set_xlim(0, None)
    ax.set_ylim(60, 101)
    ax.set_title("Store 164: service versus stock by ordering rule (each point = a safety factor, -2 to 3)", fontsize=9)
    ax.grid(alpha=0.3)
    ax.legend(title="rule / forecast", fontsize=8, loc="lower right")
    fig.text(0.5, 0.005, "Python replica of the AnyLogic model (matches native runs to 1e-11); 10 lead-time seeds per point. "
             "Assumed lead time 5 days; agent-built, educational.", ha="center", fontsize=6.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "service_vs_stock.png", dpi=150)

    fig2, ax2 = plt.subplots(figsize=(6.6, 4.0))
    for arm in ("static", "naive", "ml", "oracle"):
        g = need_lt[need_lt.arm == arm].sort_values("L")
        ax2.plot(g["L"], g["stock_for_99pct_fill"] / 1000, marker="o", label=arm, color=colors[arm])
    ax2.set_xlabel("Assumed supplier lead time (days)")
    ax2.set_ylabel("Mean stock needed for 99% fill (thousand units)")
    ax2.set_title("Lead-time sensitivity of the stock needed for 99% service", fontsize=9)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)
    fig2.tight_layout()
    fig2.savefig(out / "stock_needed_vs_leadtime.png", dpi=150)

    pd.set_option("display.width", 200)
    print(f"static rule: mean {sm:,.0f}/day, sd {ssd:,.0f}/day (2013-2014, all calendar days)")
    print(need.round(0).to_string(index=False))
    print(need_lt.round(0).pivot(index="L", columns="arm", values="stock_for_99pct_fill").to_string())


if __name__ == "__main__":
    main()
