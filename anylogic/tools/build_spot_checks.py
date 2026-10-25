"""Native frontier checks in one Simulation, avoiding the stalled Parameter Variation.

Each embedded Store is the existing PML model with its own state and lead-time RNG.
An atomic completion counter stops the shared engine only after every store logs DONE.
No replica output is fed to AnyLogic. Four rules, two safety factors and two seeds.
"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import build_model as b

ROOT = Path(__file__).resolve().parents[1]
CASES = [(p, s, z, seed) for p, s in ((0, 0), (0, 1), (0, 2), (1, 0))
         for z in (0.0, 2.0) for seed in (1, 4)]


def build():
    name = "P2FrontierChecks"
    folder = ROOT / "tools/.build/native" / name
    out = ROOT / "results/native/frontier_checks"
    path = b.build(name, folder, b.DATA.as_posix(), out.as_posix())
    tree = ET.parse(path)
    model = tree.getroot().find("Model")
    classes = model.find("ActiveObjectClasses")
    store = classes.find("ActiveObjectClass")
    store.find("Name").text = "Store"
    for e in store.iter("ClassName"):
        if e.text == "Main":
            e.text = "Store"
    b.variable(store.find("Variables"), "completionCounter", "java.util.concurrent.atomic.AtomicInteger",
               "new java.util.concurrent.atomic.AtomicInteger(1)", True)
    for c in store.iter("Code"):
        if c.text and "P2_DONE," in c.text:
            c.text = c.text.replace("getEngine().setStopTime(time());",
                                    "if (completionCounter.decrementAndGet()==0) getEngine().setStopTime(time());")
    root = b.agent(classes, "Main")
    b.variable(b.tag(root, "Variables"), "counter", "java.util.concurrent.atomic.AtomicInteger",
               f"new java.util.concurrent.atomic.AtomicInteger({len(CASES)})")
    embedded = b.tag(root, "EmbeddedObjects")
    for i, (policy, source, z, seed) in enumerate(CASES):
        e = b.ident(b.tag(embedded, "EmbeddedObject"), f"store{i}", 60+i%4*220, 100+i//4*120)
        ref = b.tag(e, "ActiveObjectClass")
        b.tag(ref, "PackageName", b.PKG)
        b.tag(ref, "ClassName", "Store")
        ps = b.tag(e, "Parameters")
        for key, value in {"policy": policy, "forecastSource": source, "serviceZ": z,
                           "repSeed": seed, "completionCounter": "counter"}.items():
            par = b.tag(ps, "Parameter")
            b.tag(par, "Name", key)
            b.code(par, "Value", value)
        for key, value in (("ReplicationFlag", "false"), ("CollectionType", "ARRAY_LIST_BASED"),
                           ("InitialLocationType", "XYZ"), ("InitializationType", "SPECIFIED_NUMBER")):
            b.tag(e, key, value)
        b.code(e, "Replication", "1")
    exps = model.find("Experiments")
    for exp in list(exps)[1:]:
        exps.remove(exp)
    exp = exps[0]
    exp.set("ActiveObjectClassId", root.findtext("Id"))
    exp.find("Parameters").clear()
    model.find("RunConfiguration").set("ActiveObjectClassId", root.findtext("Id"))
    tree.write(path, encoding="utf-8", xml_declaration=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "cases.json").write_text(json.dumps(CASES), encoding="utf-8")
    print(path)
    return path


if __name__ == "__main__":
    build()
