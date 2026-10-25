"""Shared fixtures: a small synthetic dataset built once per test session (never Rossmann data)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import make_demo_data  # noqa: E402
from analysis.load import build_database  # noqa: E402


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo_raw")
    train, stores = make_demo_data.generate(n_stores=24, seed=7)
    train.to_csv(out / "train.csv", index=False)
    stores.to_csv(out / "store.csv", index=False)
    return out


@pytest.fixture(scope="session")
def demo_con(demo_dir: Path, tmp_path_factory: pytest.TempPathFactory):
    db = tmp_path_factory.mktemp("db") / "demo.sqlite"
    con = build_database(demo_dir, db)
    yield con
    con.close()
