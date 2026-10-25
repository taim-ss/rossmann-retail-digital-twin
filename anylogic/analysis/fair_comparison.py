"""Matched inventory and paired uncertainty on the replica grid, including promo days.

Safety offsets are tuned/interpolated on the evaluation window: exploratory, not
out-of-sample policy validation. CIs reflect lead-time seeds only.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from p2_analysis import load_inputs
from p2_frontier import ARMS, Z_GRID, SEEDS
from p2_sweeps import replica, static_stats
from project_paths import DATA_DIR

ROOT = Path(__file__).resolve().parents[1]


def ci(values):
    values=np.asarray(values, float)
    half=stats.t.ppf(.975,len(values)-1)*values.std(ddof=1)/math.sqrt(len(values))
    return {"mean":float(values.mean()), "ci95_low":float(values.mean()-half),
            "ci95_high":float(values.mean()+half), "n_pairs":len(values)}


def interpolate(g, xcol, ycol, target):
    g=g.sort_values(xcol).drop_duplicates(xcol)
    x,y=g[xcol].to_numpy(),g[ycol].to_numpy()
    if target<x.min() or target>x.max():
        return float("nan")
    return float(np.interp(target,x,y))


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--data-dir",type=Path,default=DATA_DIR)
    args=cli.parse_args()
    n,demand,fc,err=load_inputs(args.data_dir,164,"2015-01-05","2015-06-24")
    sm,ssd=static_stats(args.data_dir,164)
    raw=pd.read_csv(args.data_dir/"store_day_demand.csv")
    promo=raw[(raw.store==164)&raw.date.between("2015-01-05","2015-06-24")].sort_values("date").promo.to_numpy(bool)
    rows=[]
    for arm,(policy,source) in ARMS.items():
        for z in Z_GRID:
            for seed in SEEDS:
                result=replica(n,demand,fc,err,sm,ssd,policy,source,seed,z,5,promo=promo)
                rows.append({"arm":arm,"z":z,"seed":seed,**result})
    grid=pd.DataFrame(rows)
    out=ROOT/"results/analysis/frontier"
    out.mkdir(parents=True,exist_ok=True)
    matched=[]
    for stock in (22000,25000):
        for arm in ("static","naive","ml"):
            for seed in SEEDS:
                g=grid[(grid.arm==arm)&(grid.seed==seed)]
                matched.append({"stock_target":stock,"arm":arm,"seed":seed,
                                **{m:interpolate(g,"mean_on_hand",m,stock)
                                   for m in ("fill","promo_fill","nonpromo_fill")}})
    matched=pd.DataFrame(matched)
    if matched.isna().any().any():
        raise ValueError("Matched-stock target outside a seed's grid; extrapolation forbidden")
    summaries=[]
    comparisons=[]
    for (stock,arm),g in matched.groupby(["stock_target","arm"]):
        for metric in ("fill","promo_fill","nonpromo_fill"):
            summaries.append({"stock_target":stock,"arm":arm,"metric":metric,**ci(g[metric])})
    for stock in (22000,25000):
        for other in ("static","naive"):
            for metric in ("fill","promo_fill","nonpromo_fill"):
                g=matched[matched.stock_target==stock].pivot(index="seed",columns="arm",values=metric)
                comparisons.append({"stock_target":stock,"a":"ml","b":other,"metric":metric,
                                    **ci(g.ml-g[other])})
    service=[]
    for arm in ("static","naive","ml"):
        for seed in SEEDS:
            g=grid[(grid.arm==arm)&(grid.seed==seed)]
            service.append({"arm":arm,"seed":seed,
                            "stock_for_99pct":interpolate(g,"fill","mean_on_hand",.99)})
    service=pd.DataFrame(service).pivot(index="seed",columns="arm",values="stock_for_99pct")
    service_diffs=[{"a":"ml","b":other,"metric":"stock_at_99pct_fill",**ci(service.ml-service[other])}
                   for other in ("static","naive")]
    pd.DataFrame(summaries).to_csv(out/"matched_stock_summary.csv",index=False)
    pd.DataFrame(comparisons).to_csv(out/"matched_stock_paired.csv",index=False)
    pd.DataFrame(service_diffs).to_csv(out/"matched_service_paired.csv",index=False)
    info={"evidence":"Python replica; native checks separate", "grid_runs":len(grid),
          "matching":"linear interpolation per seed; no extrapolation",
          "limitations":["Same period used for tuning and evaluation", "CI covers lead-time seeds only",
                         "Stock is mean closing daily stock, not continuous-time stock"],
          "matched_stock":summaries,"paired_fill":comparisons,"paired_stock":service_diffs}
    (out/"fair_comparison.json").write_text(json.dumps(info,indent=2,allow_nan=False),encoding="utf-8")
    print(pd.DataFrame(comparisons).round(4).to_string(index=False))
    print(pd.DataFrame(service_diffs).round(2).to_string(index=False))


if __name__=="__main__":
    main()
