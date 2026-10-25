"""WAPE, bias and the store-level bootstrap, against hand-computed values."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.metrics import bias, store_bootstrap_ci, wape


def test_wape_hand_computed():
    actual = np.array([100.0, 200.0, 0.0, 100.0])
    forecast = np.array([110.0, 180.0, 5.0, 100.0])
    assert wape(actual, forecast) == pytest.approx((10 + 20 + 5 + 0) / 400)


def test_bias_sign_and_value():
    actual = np.array([100.0, 100.0])
    assert bias(actual, np.array([110.0, 110.0])) == pytest.approx(0.10)
    assert bias(actual, np.array([90.0, 90.0])) == pytest.approx(-0.10)


def test_perfect_forecast_is_zero_error():
    a = np.array([5.0, 7.0, 9.0])
    assert wape(a, a) == 0.0 and bias(a, a) == 0.0


def test_undefined_when_actuals_sum_to_zero():
    assert np.isnan(wape(np.zeros(3), np.ones(3)))


def test_zero_sales_rows_do_not_explode():
    actual = np.array([0.0, 0.0, 100.0])
    forecast = np.array([3.0, 0.0, 100.0])
    assert wape(actual, forecast) == pytest.approx(0.03)


def test_bootstrap_point_matches_direct_and_interval_brackets_it():
    rng = np.random.default_rng(1)
    rows = []
    for store in range(1, 31):
        actual = rng.gamma(20, 300, size=40)
        rows.append(pd.DataFrame({"store": store, "actual": actual, "forecast": actual * rng.normal(1.05, 0.15, 40)}))
    frame = pd.concat(rows, ignore_index=True)
    for metric in (wape, bias):
        point, lo, hi = store_bootstrap_ci(frame, metric, n_boot=500, seed=3)
        assert point == pytest.approx(metric(frame["actual"], frame["forecast"]))
        assert lo <= point <= hi
        assert hi - lo < 0.2


def test_bootstrap_resamples_stores_not_days():
    """Two stores with opposite errors: resampling stores must give a much wider interval than days would."""
    frame = pd.concat([
        pd.DataFrame({"store": 1, "actual": [100.0] * 50, "forecast": [150.0] * 50}),
        pd.DataFrame({"store": 2, "actual": [100.0] * 50, "forecast": [50.0] * 50}),
    ], ignore_index=True)
    _, lo, hi = store_bootstrap_ci(frame, bias, n_boot=400, seed=0)
    assert lo == pytest.approx(-0.5) and hi == pytest.approx(0.5)
