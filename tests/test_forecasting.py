"""Leakage, fold layout and forecast sanity. The decisive test poisons the future and checks nothing moves."""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from analysis.backtest import final_test_origins, run_backtest, validation_origins
from analysis.forecasters import (FORBIDDEN_FEATURES, HoltWintersBank, ML_FEATURES, baseline_forecasts, ml_features,
                                  training_frame)
from analysis.panel import build_panel


@pytest.fixture(scope="module")
def panel(demo_con):
    return build_panel(demo_con)


def poisoned(panel, c: int):
    """Same panel, but every sales value after day c is absurd. A leak-free forecaster cannot notice."""
    sales = panel.sales.copy()
    sales[:, c + 1:] = 9.9e6
    return dataclasses.replace(panel, sales=sales)


@pytest.mark.parametrize("c_date", ["2014-12-31", "2015-03-14"])
def test_baselines_do_not_read_sales_after_the_cutoff(panel, c_date):
    c = panel.index_of(c_date)
    clean, bad = baseline_forecasts(panel, c), baseline_forecasts(poisoned(panel, c), c)
    for name in clean:
        np.testing.assert_array_equal(clean[name], bad[name], err_msg=name)


def test_ml_features_do_not_read_sales_after_the_cutoff(panel):
    c = panel.index_of("2015-02-10")
    pd.testing.assert_frame_equal(ml_features(panel, c), ml_features(poisoned(panel, c), c))


def test_holt_winters_does_not_read_sales_after_the_cutoff(panel):
    small = dataclasses.replace(
        panel, stores=panel.stores[:4], sales=panel.sales[:4], open=panel.open[:4], promo=panel.promo[:4],
        holiday=panel.holiday[:4], school=panel.school[:4], long_closure=panel.long_closure[:4],
        attrs=panel.attrs.iloc[:4])
    c = small.index_of("2015-01-31")
    bank = HoltWintersBank(small, fit_cutoff=small.index_of("2014-12-31"))
    fb = baseline_forecasts(small, c)["snaive4"]
    first = bank.forecast(c, 14, fb)
    bank_bad = HoltWintersBank(poisoned(small, c), fit_cutoff=small.index_of("2014-12-31"))
    np.testing.assert_allclose(first, bank_bad.forecast(c, 14, baseline_forecasts(poisoned(small, c), c)["snaive4"]))


def test_ml_features_exclude_customers_and_target_sales():
    assert set(FORBIDDEN_FEATURES).isdisjoint(ML_FEATURES)
    assert "customers" not in {f.lower() for f in ML_FEATURES}


def test_ml_training_rows_end_before_the_refit_point(panel):
    refit = panel.index_of("2015-01-01")
    x, y = training_frame(panel, first_origin=91, refit_idx=refit)
    assert x["t_idx"].max() < refit
    assert len(x) == len(y) > 0
    assert np.isfinite(y).all()


def test_validation_origins_layout():
    origins = validation_origins()
    assert len(origins) == 24
    assert origins[0] == pd.Timestamp("2015-01-01") and origins[-1] == pd.Timestamp("2015-06-11")
    assert all((origins[i + 1] - origins[i]).days == 7 for i in range(23))
    assert origins[-1] + pd.Timedelta(days=13) <= pd.Timestamp("2015-06-30")


def test_final_test_origins_start_in_july_and_stay_in_data():
    origins = final_test_origins(pd.Timestamp("2015-07-31"))
    assert origins[0] == pd.Timestamp("2015-07-01") and origins[-1] <= pd.Timestamp("2015-07-31")


@pytest.fixture(scope="module")
def small_bt(panel):
    return run_backtest(panel, validation_origins()[:2], models=("naive", "snaive1", "snaive4", "ml"))


def test_backtest_targets_sit_inside_the_validation_window(small_bt):
    assert small_bt["date"].min() >= pd.Timestamp("2015-01-01")
    assert small_bt["date"].max() <= pd.Timestamp("2015-06-30")
    assert small_bt["h"].between(1, 14).all()
    assert (small_bt["date"] == small_bt["origin"] + pd.to_timedelta(small_bt["h"] - 1, unit="D")).all()


def test_oracle_is_exactly_the_actual_and_closed_days_forecast_zero(small_bt):
    assert (small_bt["oracle"] == small_bt["actual"]).all()
    closed = small_bt[~small_bt["scored"] & (small_bt["actual"] == 0)]
    assert not closed.empty and (closed[["naive", "snaive1", "snaive4", "ml"]] == 0).all().all()


def test_ml_beats_persistence_on_planted_signal(small_bt):
    s = small_bt[small_bt["scored"]]
    err = lambda col: (s[col] - s["actual"]).abs().sum() / s["actual"].sum()  # noqa: E731
    assert err("ml") < err("naive")
