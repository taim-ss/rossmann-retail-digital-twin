"""Cleaning rules in sql/01_clean.sql, checked on synthetic data with planted problems."""
from __future__ import annotations

import pandas as pd
import pytest

from analysis.load import MissingRawDataError, build_database, read_table


@pytest.fixture(scope="module")
def clean(demo_con) -> pd.DataFrame:
    return read_table(demo_con, "clean_store_day")


def test_grid_is_complete_store_by_day(clean: pd.DataFrame):
    n_days = clean["date"].nunique()
    assert len(clean) == clean["store"].nunique() * n_days
    assert not clean.duplicated(["store", "date"]).any()


def test_closed_days_have_zero_sales(clean: pd.DataFrame):
    assert (clean.loc[clean["open"] == 0, "sales"] == 0).all()


def test_closed_with_positive_raw_sales_is_counted_not_hidden(demo_con):
    qa = read_table(demo_con, "qa_log").set_index("rule")["n"]
    assert qa["closed_with_positive_sales_zeroed (R4)"] == 8  # planted by make_demo_data
    assert qa["open_with_zero_sales_kept (R5)"] == 5


def test_missing_open_is_resolved_from_sales_never_left_null(clean: pd.DataFrame):
    assert clean["open"].isin([0, 1]).all()
    imputed = clean[clean["open_imputed"] == 1]
    assert len(imputed) == 7
    # rule R3: positive sales means open, zero sales means closed (one planted day is a Sunday)
    assert (imputed["open"] == (imputed["sales"] > 0).astype(int)).all()
    assert (imputed["open"] == 1).sum() == 6 and (imputed["open"] == 0).sum() == 1


def test_state_holiday_codes_are_normalised(clean: pd.DataFrame):
    assert set(clean["state_holiday"].unique()) <= {"0", "a", "b", "c"}
    assert (clean["holiday"] == (clean["state_holiday"] != "0").astype(int)).all()


def test_long_closure_found_and_short_closures_are_not(clean: pd.DataFrame):
    by_store = clean.groupby("store")["long_closure"].sum()
    assert (by_store > 0).sum() == 3  # three refurbished stores planted
    assert (by_store[by_store > 0] >= 14).all()
    ordinary_closed = clean[(clean["open"] == 0) & (clean["long_closure"] == 0)]
    assert not ordinary_closed.empty  # Sundays and holidays stay ordinary closures


def test_rows_absent_from_raw_become_closed_days(demo_dir, tmp_path):
    raw = pd.read_csv(demo_dir / "train.csv", low_memory=False)
    dropped = raw[(raw["Store"] == 1) & (raw["Date"].between("2014-05-01", "2014-05-20"))]
    trimmed = raw.drop(dropped.index)
    folder = tmp_path / "raw"
    folder.mkdir()
    trimmed.to_csv(folder / "train.csv", index=False)
    pd.read_csv(demo_dir / "store.csv").to_csv(folder / "store.csv", index=False)
    con = build_database(folder, tmp_path / "t.sqlite")
    out = read_table(con, "clean_store_day")
    gap = out[(out["store"] == 1) & (out["date"].between("2014-05-01", "2014-05-20"))]
    assert len(gap) == 20 and (gap["row_missing"] == 1).all() and (gap["open"] == 0).all()
    assert (gap["long_closure"] == 1).all()  # 20 consecutive closed days
    con.close()


def test_missing_raw_files_fail_loudly_with_instructions(tmp_path):
    with pytest.raises(MissingRawDataError, match="data/README.md"):
        build_database(tmp_path, tmp_path / "x.sqlite")


def test_segments_use_training_period_only(demo_con):
    seg = read_table(demo_con, "store_segment")
    prof = read_table(demo_con, "store_profile")
    assert prof["last_open_date"].max() <= "2014-12-31"
    assert set(seg["volume_tercile"]) == {"low", "mid", "high"}
    counts = seg["volume_tercile"].value_counts()
    assert counts.max() - counts.min() <= 1
