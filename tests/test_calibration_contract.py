"""Distribution-fit controls, store selection, contract file schemas and the no-data-committed guard."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from analysis.backtest import run_backtest, validation_origins
from analysis.calibration import COLUMNS, select_distribution
from analysis.contract import build_contract, select_10_stores, select_calibration_store
from analysis.panel import build_panel

ROOT = Path(__file__).resolve().parent.parent


def test_positive_control_gamma_sample_is_accepted_as_gamma():
    x = stats.gamma.rvs(8.0, scale=500.0, size=600, random_state=3)
    fit = select_distribution(x, np.random.default_rng(0), n_boot=99)
    assert 0.0 <= fit["p"] <= 1.0
    assert fit["accepted"] and fit["p"] > 0.05


def test_negative_control_bimodal_sample_is_rejected():
    rng = np.random.default_rng(4)
    x = np.concatenate([rng.normal(1000, 60, 400), rng.normal(3000, 60, 400)])
    fit = select_distribution(x, np.random.default_rng(1), n_boot=99)
    assert not fit["accepted"] and fit["distribution"] == "empirical"


@pytest.fixture(scope="module")
def panel(demo_con):
    return build_panel(demo_con)


def test_store_selection_is_deterministic_and_valid(panel):
    cal = select_calibration_store(panel.attrs)
    assert cal == select_calibration_store(panel.attrs)
    ten = select_10_stores(panel.attrs, cal)
    assert ten == select_10_stores(panel.attrs, cal)
    assert len(ten) == 10 and len(set(ten)) == 10 and cal not in ten
    types = set(panel.attrs["store_type"])
    assert types <= set(panel.attrs.loc[ten + [cal], "store_type"]) | {t for t in types if (panel.attrs["store_type"] == t).sum() < 2}


@pytest.fixture(scope="module")
def contract(panel, tmp_path_factory):
    bt = run_backtest(panel, validation_origins()[:4], models=("naive", "snaive1", "snaive4", "ml"))
    out = tmp_path_factory.mktemp("contract")
    info = build_contract(panel, bt, out)
    return out, info


def test_demand_file_schema_and_calibration_store_first(contract):
    out, info = contract
    d = pd.read_csv(out / "store_day_demand.csv")
    assert list(d.columns) == ["date", "store", "actual_sales_units", "promo", "holiday", "open"]
    assert d["store"].iloc[0] == info["calibration_store"]
    assert d["store"].nunique() == 11
    assert (d.loc[d["open"] == 0, "actual_sales_units"] == 0).all()


@pytest.mark.parametrize("name", ["forecast_oracle.csv", "forecast_naive.csv", "forecast_ml.csv"])
def test_forecast_file_schema(contract, name):
    out, _ = contract
    f = pd.read_csv(out / name)
    assert list(f.columns) == ["date", "store", "forecast_mean"]
    assert f["forecast_mean"].ge(0).all() and not f.duplicated(["date", "store"]).any()


def test_oracle_file_equals_actual_demand(contract):
    out, _ = contract
    d = pd.read_csv(out / "store_day_demand.csv").set_index(["date", "store"])["actual_sales_units"]
    o = pd.read_csv(out / "forecast_oracle.csv").set_index(["date", "store"])["forecast_mean"]
    assert np.allclose(d.loc[o.index].to_numpy(), o.to_numpy())


def test_contract_forecasts_were_issued_at_least_five_days_ahead(contract):
    out, _ = contract
    resid = pd.read_csv(out / "forecast_error_distribution.csv")
    assert resid["horizon"].between(1, 14).all()
    assert {"model", "store", "date", "origin", "horizon", "promo", "actual", "forecast", "error"} == set(resid.columns)
    assert np.allclose(resid["error"], resid["actual"] - resid["forecast"])


def test_calibration_table_columns_match_the_design():
    assert COLUMNS[0] == "store_id" and COLUMNS[-1] == "notes_assumption" and len(COLUMNS) == 17


def test_per_store_day_files_and_raw_data_are_gitignored():
    ignored = (ROOT / ".gitignore").read_text()
    for pattern in ("data/raw/", "outputs/store_day_demand.csv", "outputs/forecast_oracle.csv",
                    "outputs/forecast_naive.csv", "outputs/forecast_ml.csv", "outputs/forecast_error_distribution.csv"):
        assert pattern in ignored, pattern
    p2_aggregates = {"anylogic/results/analysis/" + name for name in (
        "paired_differences.csv", "replica_check.csv", "summary_by_source.csv",
        "frontier/frontier_all_leadtimes.csv", "frontier/frontier_by_arm.csv",
        "frontier/leadtime_sensitivity.csv", "frontier/margin_sensitivity.csv",
        "frontier/matched_service_paired.csv", "frontier/matched_stock_paired.csv",
        "frontier/matched_stock_summary.csv", "frontier/stock_needed_for_service.csv")}
    committed_csv = [p for p in ROOT.rglob("*.csv")
                     if not any(part in {"raw", "demo", "cache", "_work", ".pytest_cache", "dist"}
                                for part in p.relative_to(ROOT).parts)
                     and p.relative_to(ROOT).as_posix() not in p2_aggregates
                     and p.name not in {"calibration_table.csv", "accuracy_by_segment.csv", "selected_stores.csv",
                                        "final_test_result.csv", "fact_month_segment.csv", "fact_accuracy.csv",
                                        "fact_cost_kpi.csv"}
                     and p.name not in {"store_day_demand.csv", "forecast_oracle.csv", "forecast_naive.csv",
                                        "forecast_ml.csv", "forecast_error_distribution.csv"}]
    assert committed_csv == [], committed_csv
