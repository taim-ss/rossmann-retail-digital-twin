"""Recalculate the workbook in Excel (COM), then recompute the finding independently in Python and compare.

Same pattern as the KPI case's verify_case.py: Excel computes the formulas and saves the cached values; Python reads
the INPUT cells, recomputes with scipy and checks the workbook's outputs. A mismatch means a formula is wrong.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy import stats

from .cost_model import Assumptions, finding_per_store, k_factor, tornado
from .excel_build import CHECK_CELL, FIRST_ROW, SUMMARY

TOL = 1e-6


def recalc_with_excel(path: Path) -> None:
    import win32com.client  # pywin32; only needed on a machine with Excel

    xl = win32com.client.DispatchEx("Excel.Application")  # own instance; never quit Taim's open workbooks
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Open(str(path.resolve()))
        xl.CalculateFull()
        wb.Worksheets("README").Activate()
        wb.Save()
        wb.Close(SaveChanges=False)
    finally:
        try:
            xl.Quit()
        except Exception:  # noqa: BLE001 - Excel may already be gone (RPC disconnected); values are already saved
            pass


def read_assumptions(path: Path) -> Assumptions:
    ws = load_workbook(path)["Assumptions"]
    return Assumptions(lead_time_days=ws["B4"].value, review_period_days=ws["B5"].value, holding_rate=ws["B6"].value,
                       margin=ws["B7"].value, order_cost=ws["B8"].value, unit_price=ws["B9"].value,
                       service_level=ws["B10"].value)


def verify(path: Path) -> dict:
    """Returns a dict of comparisons; raises nothing, the caller (pipeline / pytest) decides. Excel must be installed."""
    recalc_with_excel(path)
    formulas = load_workbook(path)
    values = load_workbook(path, data_only=True)
    a = read_assumptions(path)
    din = formulas["Data_inputs"]
    last = din.max_row
    sig_p = np.array([din.cell(row=r, column=2).value for r in range(FIRST_ROW, last + 1)], float)
    sig_n = np.array([din.cell(row=r, column=3).value for r in range(FIRST_ROW, last + 1)], float)
    py_findings = finding_per_store(sig_p, sig_n, a)
    n = len(py_findings)
    mean = float(py_findings.mean())
    sd = float(py_findings.std(ddof=1))
    t = stats.t.ppf(0.975, n - 1)
    fin = values["Finding"]
    errors = [(ws.title, c.coordinate) for ws in values for row in ws.iter_rows() for c in row
              if isinstance(c.value, str) and c.value.startswith("#")]
    pairs = {
        "k_factor": (values["Assumptions"]["B14"].value, k_factor(a)),
        "mean_finding": (fin[SUMMARY["mean"]].value, mean),
        "sd_finding": (fin[SUMMARY["sd"]].value, sd),
        "t_ci_low": (fin[SUMMARY["t_lo"]].value, mean - t * sd / np.sqrt(n)),
        "t_ci_high": (fin[SUMMARY["t_hi"]].value, mean + t * sd / np.sqrt(n)),
        "chain_equals_mean": (fin["K27"].value, mean),
    }
    tor = tornado(float((sig_p - sig_n).mean()), a).set_index("parameter")
    tws = values["Tornado"]
    for r, key in zip(range(4, 9), ("lead_time_days", "review_period_days", "holding_rate", "margin", "order_cost")):
        pairs[f"tornado_swing_{key}"] = (tws[f"F{r}"].value, tor.loc[key, "swing"])
    out = {"comparisons": {}, "excel_error_cells": errors, "checks_cell": values["Checks"][CHECK_CELL].value}
    for name, (excel_v, py_v) in pairs.items():
        ok = excel_v is not None and abs(float(excel_v) - float(py_v)) <= TOL * max(1.0, abs(float(py_v)))
        out["comparisons"][name] = {"excel": excel_v, "python": float(py_v), "ok": bool(ok)}
    out["all_ok"] = all(c["ok"] for c in out["comparisons"].values()) and not errors \
        and out["checks_cell"] == "ALL CHECKS PASS"
    path.with_suffix(".verification.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out
