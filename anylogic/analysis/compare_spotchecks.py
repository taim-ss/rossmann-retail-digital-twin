"""Fail closed on incomplete native coverage, replica disagreement or broken CRN."""
import json
import math
from pathlib import Path

from p2_analysis import JavaRandom, load_inputs
from p2_sweeps import read_runs, replica, static_stats
from project_paths import DATA_DIR

ROOT = Path(__file__).resolve().parents[1]


def main():
    data=DATA_DIR
    logs=ROOT/"results/native/frontier_checks"
    expected={tuple(c) for c in json.loads((logs/"cases.json").read_text())}
    runs=read_runs(logs)
    actual={(r.policy,r.source,r.z,r.seed) for r in runs.itertuples()}
    if actual!=expected:
        raise ValueError(f"Coverage mismatch: missing {expected-actual}, unexpected {actual-expected}")
    n,demand,fc,err=load_inputs(data,164,"2015-01-05","2015-06-24")
    sm,ssd=static_stats(data,164)
    checks=[]
    for r in runs.itertuples():
        if r.L!=5 or r.kpi_days!=159 or r.end_time!=170.5:
            raise ValueError(f"Unexpected horizon or lead time: {r.file}")
        rep=replica(n,demand,fc,err,sm,ssd,r.policy,r.source,r.seed,r.z,r.L)
        worst=max(abs(getattr(r,k)-v) for k,v in rep.items())
        lines=(logs/r.file).read_text(encoding="utf-8").splitlines()
        draws=[ln.split(",") for ln in lines if ln.startswith("P2_CRN,")]
        rng=JavaRandom(20000+r.seed)
        crn=len(draws)==5 and all(abs(float(d[4])-rng.next_double())<1e-15 for d in draws)
        daily=[ln.split(",")[1:] for ln in lines if ln.startswith("P2_DAY,")]
        conservation=len(daily)==n and [int(row[0]) for row in daily]==list(range(n))
        for ln in lines:
            if ln.startswith("P2_DAY,"):
                row=[float(v) for v in ln.split(",")[1:]]
                conservation &= abs(row[1]-row[3]-row[4])<1e-8 and row[5]>=-1e-8 and row[6]>=-1e-8
        checks.append({"policy":r.policy,"source":r.source,"z":r.z,"seed":r.seed,
                       "max_abs_diff":worst,"crn_ok":crn,"daily_sales_balance_ok":conservation})
    status={"native_runs":len(checks),"max_abs_diff":max(c["max_abs_diff"] for c in checks),
            "all_pass":all(c["max_abs_diff"]<1e-6 and c["crn_ok"] and c["daily_sales_balance_ok"] for c in checks),
            "checks":checks,"coverage":"four rules x two safety offsets x two lead-time seeds",
            "native_grid_sweep":False}
    out=ROOT/"results/analysis/native_spotchecks.json"
    out.write_text(json.dumps(status,indent=2),encoding="utf-8")
    print(json.dumps(status,indent=2))
    if not status["all_pass"]:
        raise ValueError("Native verification failed")


if __name__=="__main__":
    main()
