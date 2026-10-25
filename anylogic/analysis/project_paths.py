"""Resolve P1 beside the original portfolio or at the combined repository root."""
from pathlib import Path

P2_ROOT=Path(__file__).resolve().parents[1]
P1_ROOT=P2_ROOT.parent if (P2_ROOT.parent/"run_pipeline.py").exists() else P2_ROOT.parents[2]/"retail-demand-digital-twin"
DATA_DIR=P1_ROOT/"outputs"
