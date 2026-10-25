"""Load the two CSV files into SQLite and run the numbered SQL scripts in sql/.

Raw columns are stored as-is (strings kept as strings) so that the cleaning rules in sql/01_clean.sql
are the single place where data are interpreted.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import EXPECTED_RAW_FILES, ROOT, TRAIN_END

SQL_DIR = ROOT / "sql"


class MissingRawDataError(FileNotFoundError):
    """Raised when the Kaggle files are not where data/README.md says they should be."""


def check_raw_files(raw_dir: Path) -> None:
    missing = [name for name in EXPECTED_RAW_FILES if not (raw_dir / name).is_file()]
    if missing:
        raise MissingRawDataError(
            f"Missing {', '.join(missing)} in {raw_dir}. Accept the Kaggle competition rules and download "
            "the files as described in data/README.md (or run with --demo for synthetic data)."
        )


def build_database(raw_dir: Path, db_path: Path, train_end: str = TRAIN_END) -> sqlite3.Connection:
    """(Re)build the SQLite database from the raw CSVs and run every sql/NN_*.sql script in order."""
    check_raw_files(raw_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    train = pd.read_csv(raw_dir / "train.csv", dtype={"StateHoliday": "string"}, low_memory=False)
    store = pd.read_csv(raw_dir / "store.csv")
    _validate_columns(train, store)

    con = sqlite3.connect(db_path)
    train.to_sql("raw_train", con, index=False)
    store.to_sql("raw_store", con, index=False)
    min_date, max_date = str(train["Date"].min()), str(train["Date"].max())
    con.execute("CREATE TABLE params (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany(
        "INSERT INTO params VALUES (?, ?)",
        [("min_date", min_date), ("max_date", max_date), ("train_end", train_end)],
    )
    for script in sorted(SQL_DIR.glob("[0-9][0-9]_*.sql")):
        con.executescript(script.read_text(encoding="utf-8"))
    con.commit()
    return con


def _validate_columns(train: pd.DataFrame, store: pd.DataFrame) -> None:
    need_train = {"Store", "DayOfWeek", "Date", "Sales", "Customers", "Open", "Promo", "StateHoliday", "SchoolHoliday"}
    need_store = {"Store", "StoreType", "Assortment", "CompetitionDistance", "Promo2"}
    if not need_train <= set(train.columns):
        raise ValueError(f"train.csv lacks columns: {sorted(need_train - set(train.columns))}")
    if not need_store <= set(store.columns):
        raise ValueError(f"store.csv lacks columns: {sorted(need_store - set(store.columns))}")
    if train["Date"].isna().any():
        raise ValueError("train.csv has rows without a Date")
    if train.duplicated(["Store", "Date"]).any():
        raise ValueError("train.csv has duplicate (Store, Date) rows")


def read_table(con: sqlite3.Connection, name: str) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {name}", con)
