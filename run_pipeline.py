"""One command for the whole pipeline.

    python run_pipeline.py            # real run: needs data/raw/train.csv and store.csv (see data/README.md)
    python run_pipeline.py --demo     # synthetic data, output under outputs/demo, excel/demo, powerbi/demo
    python run_pipeline.py --final-test   # July 2015 hold-out, ONCE (refuses to run twice)

Steps: load + SQL clean > rolling-origin backtest > accuracy tables > calibration table > cost-of-error workbook
(recalculated and checked in Excel when available) > P2 contract files > Power BI inputs > run_summary.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", str(min(2, os.cpu_count() or 1)))  # avoid thread oversubscription

import pandas as pd  # noqa: E402

import make_demo_data  # noqa: E402
from analysis.accuracy import accuracy_table, best_model_summary  # noqa: E402
from analysis.backtest import final_test_origins, run_backtest, validation_origins  # noqa: E402
from analysis.calibration import build_calibration_table  # noqa: E402
from analysis.config import ROOT, TRAIN_END, VALID_END, VALID_START, make_mode  # noqa: E402
from analysis.contract import build_contract, write_contract_md  # noqa: E402
from analysis.cost_model import (BASE, bootstrap_mean_ci, finding_per_store, k_factor, store_error_inputs,  # noqa: E402
                                 tornado)
from analysis.excel_build import build_workbook  # noqa: E402
from analysis.load import MissingRawDataError, build_database, read_table  # noqa: E402
from analysis.panel import build_panel  # noqa: E402
from analysis.powerbi_export import export_powerbi  # noqa: E402

log = logging.getLogger("pipeline")
ERROR_MODELS = {"forecast_error_oracle": "oracle", "forecast_error_naive": "snaive1", "forecast_error_ml": "ml"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run_final_test(panel, out_dir: Path) -> None:
    """Score the frozen models on July 2015 once. A second run is refused so the hold-out stays a hold-out."""
    result = out_dir / "final_test_result.csv"
    if result.exists():
        sys.exit(f"{result} already exists: the July hold-out was used once and must not be re-scored.")
    bt = run_backtest(panel, final_test_origins(panel.dates[-1]))
    table = accuracy_table(bt, panel, n_boot=2000)
    table[(table["segment_dim"] == "all") & (table["horizon_band"] == "pooled_h1-14")].to_csv(result, index=False)
    log.info("final test written to %s", result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo", action="store_true", help="synthetic data, separate output folders")
    parser.add_argument("--final-test", action="store_true", help="score the July 2015 hold-out once")
    parser.add_argument("--n-boot-fit", type=int, default=49, help="bootstrap draws for goodness-of-fit p-values")
    parser.add_argument("--skip-excel-check", action="store_true")
    parser.add_argument("--reuse-backtest", action="store_true",
                        help="development only: reuse outputs/_work/validation_backtest.pkl (stale if code changed)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    mode = make_mode(args.demo)
    if args.demo and not (mode.raw_dir / "train.csv").exists():
        train, stores = make_demo_data.generate()
        mode.raw_dir.mkdir(parents=True, exist_ok=True)
        train.to_csv(mode.raw_dir / "train.csv", index=False)
        stores.to_csv(mode.raw_dir / "store.csv", index=False)
    sub = "demo" if args.demo else ""
    excel_dir, bi_dir = ROOT / "excel" / sub, ROOT / "powerbi" / sub
    out_dir = mode.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    try:
        con = build_database(mode.raw_dir, mode.db_path)
    except MissingRawDataError as err:
        sys.exit(str(err))
    panel = build_panel(con)
    qa = read_table(con, "qa_log")
    log.info("data: %d stores, %s to %s\n%s", panel.n_stores, panel.dates[0].date(), panel.dates[-1].date(),
             qa.to_string(index=False))
    if args.final_test:
        run_final_test(panel, out_dir)
        return

    work = out_dir / "_work"
    work.mkdir(exist_ok=True)
    cached = work / "validation_backtest.pkl"
    if args.reuse_backtest and cached.exists():
        log.warning("reusing cached backtest %s", cached)
        bt = pd.read_pickle(cached)
    else:
        bt = run_backtest(panel, validation_origins())
        bt.to_pickle(cached)

    acc = accuracy_table(bt, panel)
    acc.to_csv(out_dir / "accuracy_by_segment.csv", index=False)
    ranking = best_model_summary(acc)
    log.info("pooled WAPE (h1-14, open days, validation 2015-01-01..06-24):\n%s", ranking.round(4).to_string(index=False))

    calib = build_calibration_table(panel, bt, panel.index_of(TRAIN_END), VALID_START, VALID_END, ERROR_MODELS,
                                    n_boot=args.n_boot_fit)
    calib.to_csv(out_dir / "calibration_table.csv", index=False)

    ml_in, sn_in = store_error_inputs(bt, "ml"), store_error_inputs(bt, "snaive1")
    findings = finding_per_store(ml_in["rmse_promo"].to_numpy(), ml_in["rmse_nonpromo"].to_numpy())
    boot = bootstrap_mean_ci(findings)
    xlsx = build_workbook(excel_dir / "assumptions_and_sensitivity.xlsx", ml_in, sn_in, boot, args.demo)
    excel_check = {"status": "skipped"}
    if not args.skip_excel_check:
        try:
            from analysis.excel_verify import verify
            excel_check = verify(xlsx)
            excel_check = {"status": "ok" if excel_check["all_ok"] else "MISMATCH", "checks_cell": excel_check["checks_cell"],
                           "comparisons": len(excel_check["comparisons"])}
        except ImportError:
            excel_check = {"status": "skipped: pywin32/Excel not available"}
    log.info("excel check: %s", excel_check)

    info = build_contract(panel, bt, out_dir)
    write_contract_md(out_dir, info, args.demo)
    delta_mean = float((ml_in["rmse_promo"] - ml_in["rmse_nonpromo"]).mean())
    tor = tornado(delta_mean)
    bi = export_powerbi(con, acc, tor, float(findings.mean()), bi_dir)

    summary = {
        "mode": mode.name, "stores": int(panel.n_stores), "qa": dict(zip(qa["rule"], qa["n"].astype(int))),
        "pooled_wape": ranking.round(5).to_dict(orient="records"),
        "finding_eur_per_store_year": {"mean": boot[0], "ci95_store_bootstrap": [boot[1], boot[2]],
                                       "k_factor": k_factor(BASE), "assumptions": BASE.__dict__},
        "calibration_rows": int(len(calib)),
        "calibration_demand_fit_accepted_share": float((calib.loc[calib["input_name"] == "daily_demand_level",
                                                                "fitted_distribution"] != "empirical").mean()),
        "excel_check": excel_check, "contract": info, "powerbi": bi,
        "raw_sha256": {n: sha256(mode.raw_dir / n) for n in ("train.csv", "store.csv")},
        "seconds": round(time.time() - started, 1),
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("done in %.0f s; summary in %s", summary["seconds"], out_dir / "run_summary.json")


if __name__ == "__main__":
    main()
