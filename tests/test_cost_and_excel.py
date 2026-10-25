"""Cost model limit cases, a hand-computed value, and the Excel-recalc-versus-Python parity check."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from analysis.cost_model import (Assumptions, BASE, bootstrap_mean_ci, extra_cost, finding_per_store, k_factor,
                                 loss_function, tornado)


def test_zero_error_gives_zero_extra_cost():
    assert extra_cost(0.0) == 0.0
    assert finding_per_store(np.zeros(3), np.zeros(3)).sum() == 0.0


@pytest.mark.parametrize("sigma", [1.0, 37.5, 4000.0])
def test_equal_errors_give_zero_finding(sigma):
    assert finding_per_store(np.array([sigma]), np.array([sigma]))[0] == pytest.approx(0.0, abs=1e-9)


def test_extra_cost_is_increasing_in_sigma():
    for s in (1.0, 10.0, 250.0):
        assert extra_cost(2 * s) > extra_cost(s)


def test_k_factor_matches_a_hand_computation():
    a = Assumptions(lead_time_days=5, review_period_days=7, holding_rate=0.25, margin=0.30, unit_price=1.0,
                    service_level=0.95)
    z = 1.6448536269514722
    lz = norm.pdf(z) - z * (1 - norm.cdf(z))
    expected = np.sqrt(12) * (z * 0.7 * 0.25 + (365 / 7) * lz * 0.30)
    assert k_factor(a) == pytest.approx(expected, rel=1e-12)
    assert loss_function(0.0) == pytest.approx(1 / np.sqrt(2 * np.pi))


def test_order_cost_does_not_enter_the_finding_and_lead_time_does():
    t = tornado(20.0).set_index("parameter")
    assert t.loc["order_cost", "swing"] == 0.0
    assert t.loc["lead_time_days", "swing"] > 0.0


def test_bootstrap_ci_is_reproducible_and_brackets_the_mean():
    v = np.random.default_rng(0).normal(5, 2, 60)
    assert bootstrap_mean_ci(v, seed=42) == bootstrap_mean_ci(v, seed=42)
    m, lo, hi = bootstrap_mean_ci(v, seed=42)
    assert lo <= m <= hi


def _fake_inputs(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.uniform(300, 900, n)
    return pd.DataFrame({"store": np.arange(1, n + 1), "rmse_promo": base * rng.uniform(1.1, 1.5, n),
                         "rmse_nonpromo": base, "n_promo": 90, "n_nonpromo": 140,
                         "mean_daily_sales": base * 8})


def test_excel_recalc_matches_python(tmp_path):
    pytest.importorskip("win32com.client")
    from analysis.excel_build import build_workbook
    from analysis.excel_verify import verify

    ml, sn = _fake_inputs(30, 1), _fake_inputs(30, 2)
    findings = finding_per_store(ml["rmse_promo"].to_numpy(), ml["rmse_nonpromo"].to_numpy())
    path = build_workbook(tmp_path / "t.xlsx", ml, sn, bootstrap_mean_ci(findings), is_demo=True)
    try:
        result = verify(path)
    except Exception as err:  # noqa: BLE001 - Excel not installed / not startable: skip, never pass silently
        pytest.skip(f"Excel COM unavailable: {err}")
    bad = {k: v for k, v in result["comparisons"].items() if not v["ok"]}
    assert not bad, bad
    assert result["excel_error_cells"] == []
    assert result["checks_cell"] == "ALL CHECKS PASS"


def test_changing_an_assumption_changes_the_python_finding():
    delta = np.array([100.0])
    more_lead = Assumptions(**{**BASE.__dict__, "lead_time_days": 10.0})
    assert finding_per_store(delta, np.zeros(1), more_lead)[0] > finding_per_store(delta, np.zeros(1))[0]
