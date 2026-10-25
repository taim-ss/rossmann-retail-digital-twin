"""Synthetic limit cases and native-presentation non-interference checks."""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"analysis"))
import build_model
from p2_sweeps import replica
from fair_comparison import interpolate
from native_runtime import validate_generated_classes


@pytest.mark.parametrize("policy,source",[(0,0),(0,1),(0,2),(1,0)])
def test_zero_demand_never_creates_stock_orders_or_cost(policy,source):
    err=pd.DataFrame({"model":["naive","ml"],"horizon":[7,7],"error":[0.,0.]})
    result=replica(60,np.zeros(60),np.zeros((3,60)),err,0,0,policy,source,1,0,5)
    assert result["fill"]==1
    assert result["orders"]==result["mean_on_hand"]==result["total_cost"]==result["lost"]==0


def test_promotion_metrics_partition_without_changing_inventory():
    demand=np.full(60,100.)
    err=pd.DataFrame({"model":["naive","ml"],"horizon":[7,7],"error":[10.,10.]})
    args=(60,demand,np.full((3,60),100.),err,100,20,0,2,4,-1,5)
    base=replica(*args)
    decorated=replica(*args,promo=np.arange(60)%2==0)
    assert {k:decorated[k] for k in base}==base
    assert 0<=decorated["promo_fill"]<=1
    assert 0<=decorated["nonpromo_fill"]<=1
    assert base["sold"]+base["lost"]==pytest.approx(base["demand"])


def test_matched_stock_refuses_extrapolation():
    g=pd.DataFrame({"stock":[10.,20.],"fill":[.8,1.]})
    assert interpolate(g,"stock","fill",15)==pytest.approx(.9)
    assert np.isnan(interpolate(g,"stock","fill",30))


def test_compiler_error_stubs_cannot_count_as_native_execution(tmp_path):
    (tmp_path/"Main.class").write_bytes(b"fake class: Unresolved compilation problems: duplicate field")
    with pytest.raises(RuntimeError,match="compiler error stubs"):
        validate_generated_classes(tmp_path)


def test_generated_scene_has_unique_ids_and_no_inventory_mutations(tmp_path):
    path=build_model.build("P2Test",tmp_path,"input","output")
    root=ET.parse(path).getroot()
    references={"FreeformParamValue","RangeVariationParamValue"}
    ids=[e.findtext("Id") for e in root.iter() if e.tag not in references and e.find("Id") is not None]
    assert len(ids)==len(set(ids))
    main=root.find("Model/ActiveObjectClasses/ActiveObjectClass")
    scene=main.find("Presentation/Level/Presentation")
    variable_names={e.findtext("Name") for e in main.findall("Variables/Variable")}
    scene_names={e.findtext("Name") for e in scene.iter() if e.find("Name") is not None}
    assert not variable_names.intersection(scene_names)
    assert len(list(scene.iter("Group")))>=37
    assert len(root.findall("Model/Experiments/SimulationExperiment"))==2
    dynamic=[e.text for e in scene.iter() if e.tag.endswith("Code") and e.text]
    assert any("onHand" in code for code in dynamic)
    assert not any(token in code for code in dynamic for token in
                   ("onHand=","onHand =","onOrder=","inject(","nextDouble(","setStopTime(","setSeed("))
    for block in main.findall("EmbeddedObjects/EmbeddedObject"):
        assert float(block.findtext("Y"))>850
