"""Paths and fixed constants shared by every pipeline step.

Dates follow the P1 spec: train up to 2014-12-31, validate 2015-01-01..2015-06-30.
Nothing here depends on the Rossmann data itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRAIN_END = "2014-12-31"
VALID_START = "2015-01-01"
VALID_END = "2015-06-30"
FINAL_TEST_START = "2015-07-01"  # touched once, for the final report only (see docs/experiment-design.md)

EXPECTED_RAW_FILES = ("train.csv", "store.csv")


@dataclass(frozen=True)
class Mode:
    """Where a run reads its input and writes its output.

    real: data/raw (Kaggle files, never committed) -> outputs/
    demo: data/demo (synthetic)                     -> outputs/demo/
    """

    name: str
    raw_dir: Path
    out_dir: Path
    db_path: Path

    @property
    def is_demo(self) -> bool:
        return self.name == "demo"


def make_mode(demo: bool, root: Path = ROOT) -> Mode:
    if demo:
        return Mode("demo", root / "data" / "demo", root / "outputs" / "demo", root / "data" / "cache" / "demo.sqlite")
    return Mode("real", root / "data" / "raw", root / "outputs", root / "data" / "cache" / "rossmann.sqlite")
