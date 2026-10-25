"""Generate the P2 AnyLogic model (tier B: agent-produced under Taim's direction, educational, PLE).

One store, one daily replenishment loop built from Process Modeling Library blocks:
  dayTick (Source, 1 per day)  -> daySink          daily demand, review, ordering logic runs in dayTick.onExit
  orderSource (Source, MANUAL) -> leadDelay -> orderSink   one Order agent per purchase order, delayed by the lead time
Demand and forecasts are READ AT RUN TIME from the P1 CSV files (dataDirectory); no Rossmann data is stored in the .alp.
Inventory parameters (lead time, costs, service level, review period) are ASSUMPTIONS, labelled in the model.
Schema conventions follow the P3 generator, which loaded and ran in AnyLogic 8.9.10 PLE.

Usage: python build_model.py [--name P2_Rossmann_Replenishment] [--out DIR] [--data-dir DIR] [--output-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "outputs" if (ROOT.parent / "run_pipeline.py").exists() else ROOT.parents[2] / "retail-demand-digital-twin/outputs"
PML = "com.anylogic.libraries.processmodeling"
serial = 1900000000000
PKG = "p2_rossmann_replenishment"
blocks: dict = {}
links: list = []


def tag(parent, name, value=None, **attrs):
    e = ET.SubElement(parent, name, attrs)
    if value is not None:
        e.text = str(value)
    return e


def ident(e, name=None, x=None, y=None):
    global serial
    serial += 1
    tag(e, "Id", serial)
    if name is not None:
        tag(e, "Name", name)
    if x is not None:
        tag(e, "X", x)
        tag(e, "Y", y)
        l = tag(e, "Label")
        tag(l, "X", 0)
        tag(l, "Y", -20)
        for k, v in [("PublicFlag", "false"), ("PresentationFlag", "true"), ("ShowLabel", "true")]:
            tag(e, k, v)
    return e


def code(parent, name, value, unit=None, classname=None):
    e = tag(parent, name, Class=classname or ("CodeUnitValue" if unit else "CodeValue"))
    tag(e, "Code", value)
    if unit:
        tag(e, "Unit", unit, Class="TimeUnits")
    return e


def variable(parent, name, typ, initial, parameter=False):
    e = ident(tag(parent, "Variable", Class="Parameter" if parameter else "PlainVariable"), name, 30, 500)
    e.find("PresentationFlag").text = "false"
    if parameter:
        p = tag(e, "Properties", SaveInSnapshot="true", ModificatorType="STATIC")
        tag(p, "Type", typ)
        tag(p, "UnitType", "NONE")
        tag(p, "SdArray", "false")
        code(p, "DefaultValue", initial)
        editor = ident(tag(p, "ParameterEditor"))
        tag(editor, "EditorContolType", "TEXT_BOX")
        tag(editor, "MinSliderValue", 0)
        tag(editor, "MaxSliderValue", 100)
        tag(editor, "DelimeterType", "NO_DELIMETER")
    else:
        p = tag(e, "Properties", SaveInSnapshot="true", Constant="false", AccessType="public", StaticVariable="false")
        tag(p, "Type", typ)
        code(p, "InitialValue", initial)
    return e


def agent(parent, name):
    e = ident(tag(parent, "ActiveObjectClass"), name)
    tag(e, "Generic", "false")
    generic = ident(tag(e, "GenericParameter"), "T")
    code(generic, "GenericParameterValue", "T extends Agent")
    tag(generic, "GenericParameterLabel", "Generic parameter:")
    tag(e, "FlowChartsUsage", "ENTITY")
    tag(e, "SamplesToKeep", 100)
    tag(e, "LimitNumberOfArrayElements", "false")
    tag(e, "ElementsLimitValue", 100)
    tag(e, "MakeDefaultViewArea", "true")
    for k, v in [("SceneGridColor", None), ("SceneBackgroundColor", -4144960), ("EnvironmentResourceRef", None),
                 ("EnvironmentType", "NONE"), ("EnvironmentRotationX", 0), ("EnvironmentRotationY", 0),
                 ("EnvironmentRotationZ", 0), ("EnvironmentIntensity", 1)]:
        tag(e, k, v)
    props = tag(e, "AgentProperties")
    tag(props, "EnvironmentDefinesInitialLocation", "true")
    tag(props, "RotateAnimationTowardsMovement", "false")
    tag(props, "RotateAnimationVertically", "false")
    code(props, "VelocityCode", "10", "MPS").find("Unit").set("Class", "SpeedUnits")
    tag(props, "MessageType", "Object")
    for n in ["PhysicalLength", "PhysicalWidth", "PhysicalHeight"]:
        code(props, n, "1", "METER").find("Unit").set("Class", "LengthUnits")
    env = tag(e, "EnvironmentProperties")
    tag(env, "EnableSteps", "false")
    code(env, "StepDurationCode", "1.0", "HOUR")
    tag(env, "SpaceType", "CONTINUOUS")
    tag(env, "WidthCode", 1200)
    tag(env, "HeightCode", 600)
    for k, v in [("ZHeightCode", 0), ("ColumnsCountCode", 100), ("RowsCountCode", 100), ("NeigborhoodType", "MOORE"),
                 ("LayoutType", "RANDOM"), ("NetworkType", "USER_DEF"), ("ConnectionsPerAgentCode", 2),
                 ("ConnectionsRangeCode", 50), ("NeighborLinkFractionCode", 0.95), ("MCode", 10),
                 ("LineStyle", "SOLID"), ("LineWidth", 1), ("LineColor", -16777216), ("LineZOrder", "UNDER_AGENTS"),
                 ("LineArrow", "NONE"), ("LineArrowPosition", "END")]:
        tag(env, k, v)
    datasets = tag(e, "DatasetsCreationProperties")
    tag(datasets, "AutoCreate", "true")
    ident(datasets)
    tag(datasets, "OccurrenceAtTime", "true")
    tag(datasets, "OccurrenceDate", 1772409600000)
    code(datasets, "OccurrenceTime", "0", "HOUR")
    code(datasets, "RecurrenceCode", "1", "HOUR")
    ruler = ident(tag(e, "ScaleRuler"), "scale", 0, -150)
    for k, v in [("DrawMode", "SHAPE_DRAW_2D3D"), ("Length", 100), ("Rotation", 0), ("ScaleType", "BASED_ON_LENGTH"),
                 ("ModelLength", 10), ("LengthUnits", "METER"), ("Scale", 10), ("InheritedFromParentAgentType", "true")]:
        tag(ruler, k, v)
    presentation = tag(e, "Presentation")
    level = ident(tag(presentation, "Level"), "level", 0, 0)
    for k, v in [("DrawMode", "SHAPE_DRAW_2D3D"), ("Z", 0), ("LevelVisibility", "DIM_NON_CURRENT")]:
        tag(level, k, v)
    tag(level, "Presentation")
    tag(e, "CurrentLevel", level.findtext("Id"))
    agent_links = tag(e, "AgentLinks")
    link = ident(tag(agent_links, "AgentLink"), "connections", 50, -50)
    tag(e, "ConnectionsId", link.findtext("Id"))
    for k, v in [("HandleReceiveInConnections", "false"), ("AgentLinkType", "COLLECTION_OF_LINKS"),
                 ("AgentLinkBidirectional", "true"), ("MessageType", "Object"), ("LineStyle", "SOLID"),
                 ("LineWidth", 1), ("LineColor", -16777216), ("LineZOrder", "UNDER_AGENTS"), ("LineArrow", "NONE"),
                 ("LineArrowPosition", "END")]:
        tag(link, k, v)
    return e


def block(parent, name, typ, x, y, settings):
    e = ident(tag(parent, "EmbeddedObject"), name, x, y)
    a = tag(e, "ActiveObjectClass")
    tag(a, "PackageName", PML)
    tag(a, "ClassName", typ)
    ps = tag(e, "Parameters")
    for n, value in settings.items():
        p = tag(ps, "Parameter")
        tag(p, "Name", n)
        if isinstance(value, tuple):
            code(p, "Value", value[0], value[1])
        else:
            code(p, "Value", value)
    tag(e, "ReplicationFlag", "false")
    code(e, "Replication", "100")
    tag(e, "CollectionType", "ARRAY_LIST_BASED")
    tag(e, "InitialLocationType", "XYZ")
    code(e, "ColumnCode", "0")
    code(e, "RowCode", "0")
    code(e, "LocationNameCode", '""')
    tag(e, "InitializationType", "SPECIFIED_NUMBER")
    blocks[name] = (typ, x, y)
    return e


def entity_value(block_el, agent_name):
    ps = block_el.find("Parameters")
    p = tag(ps, "Parameter")
    tag(p, "Name", "newEntity")
    v = tag(p, "Value", Class="EntityCodeValue")
    tag(v, "IsAgentEntity", "true")
    entity = ident(tag(v, "EntityEmbeddedObject"))
    a = tag(entity, "ActiveObjectClass")
    tag(a, "PackageName", PKG)
    tag(a, "ClassName", agent_name)
    tag(entity, "Parameters")
    tag(entity, "ReplicationFlag", "true")
    code(entity, "Replication", "100")
    tag(entity, "CollectionType", "ARRAY_LIST_BASED")
    tag(entity, "InitialLocationType", "XYZ")
    tag(entity, "InitializationType", "SPECIFIED_NUMBER")


def write_connection(parent, source, target):
    e = ident(tag(parent, "Connector"), f"link{len(parent)}", 0, 0)
    for prefix, name, port in [("Source", source, "out"), ("Target", target, "in")]:
        ref = tag(e, prefix + "EmbeddedObjectReference")
        for k, v in [("PackageName", PKG), ("ClassName", "Main"), ("ItemName", name)]:
            tag(ref, k, v)
        ref = tag(e, prefix + "ConnectableItemReference")
        for k, v in [("PackageName", PML), ("ClassName", blocks[name][0]), ("ItemName", port)]:
            tag(ref, k, v)
    pts = tag(e, "Points")
    for name in [source, target]:
        p = tag(pts, "Point")
        tag(p, "X", blocks[name][1])
        tag(p, "Y", blocks[name][2])


# --------------------------------------------------------------------------- Java snippets

from inventory_code import N_DAYS, LOADER, TICK, FINISH, RECEIVE


def guard(snippet: str, label: str) -> str:
    """Run-time errors in headless runs are otherwise invisible: trap them into a file, then rethrow."""
    return ("try { " + snippet + " } catch (Throwable t_) { java.io.StringWriter sw_ = new java.io.StringWriter(); "
            "t_.printStackTrace(new java.io.PrintWriter(sw_)); try { java.nio.file.Files.createDirectories("
            "java.nio.file.Paths.get(outputDirectory)); java.nio.file.Files.writeString(java.nio.file.Paths.get("
            "outputDirectory, \"p2-error-" + label + ".log\"), sw_.toString()); } catch (Exception e2_) { } "
            "throw new RuntimeException(t_); }")


def build(name: str, out_dir: Path, data_dir: str, output_dir: str, overrides: dict | None = None) -> Path:
    global PKG, serial
    PKG = re.sub(r"[^a-z0-9_]", "_", name.lower())
    serial = 1900000000000
    blocks.clear()
    ws = ET.Element("AnyLogicWorkspace", WorkspaceVersion="1.9", AnyLogicVersion="8.9.10.202609231424", AlpVersion="8.9.10")
    model = ident(tag(ws, "Model"), name)
    tag(model, "EngineVersion", 6)
    tag(model, "JavaPackageName", PKG)
    tag(model, "ModelTimeUnit", "Day")
    tag(model, "Folders")
    classes = tag(model, "ActiveObjectClasses")
    m = agent(classes, "Main")
    mid = m.findtext("Id")
    vars_ = tag(m, "Variables")
    params = [("storeId", "int", "164"), ("forecastSource", "int", "0"), ("repSeed", "int", "1"),
              ("leadTimeDays", "double", "5.0"), ("reviewDays", "int", "7"), ("holdingRate", "double", "0.25"),
              ("margin", "double", "0.30"), ("orderCost", "double", "50.0"), ("unitPrice", "double", "1.0"),
              ("serviceZ", "double", "1.6448536269514722"), ("errHorizonMin", "int", "5"), ("errHorizonMax", "int", "11"),
              ("policy", "int", "0"), ("visualOn", "boolean", "false"), ("firstDate", "String", '"2015-01-05"'), ("lastDate", "String", '"2015-06-24"'),
              ("trainStart", "String", '"2013-01-01"'), ("trainEnd", "String", '"2014-12-31"'),
              ("dataDirectory", "String", json.dumps(data_dir)), ("outputDirectory", "String", json.dumps(output_dir))]
    overrides = overrides or {}
    unknown = set(overrides) - {n for n, _, _ in params}
    assert not unknown, f"unknown parameters {unknown}"
    params = [(n, t, overrides.get(n, v)) for n, t, v in params]
    pid = {}
    for n, t, v in params:
        pid[n] = variable(vars_, n, t, v, True).findtext("Id")
    fields = [("staticMean", "double", "0"), ("staticSd", "double", "0"), ("demand", "double[]", "new double[0]"), ("fc", "double[][]", "new double[3][0]"), ("nDays", "int", "0"),
              ("firstDay", "java.time.LocalDate", "null"), ("sigma", "double", "0"), ("onHand", "double", "0"),
              ("onOrder", "double", "0"), ("onHandStart", "double", "0"), ("dayCount", "int", "0"),
              ("leadRng", "java.util.Random", "new java.util.Random(20000L)"), ("pendingQty", "double", "0"),
              ("pendingLead", "int", "1"), ("pendingDay", "int", "0"), ("kpiDays", "int", "0"), ("orders", "int", "0"),
              ("deliveries", "int", "0"), ("drawsLogged", "int", "0"), ("stockoutDays", "int", "0"),
              ("sumDemand", "double", "0"), ("sumSold", "double", "0"), ("sumLost", "double", "0"),
              ("sumOnHand", "double", "0"), ("holdCost", "double", "0"), ("shortCost", "double", "0"),
              ("ordCost", "double", "0"), ("nativeLog", "StringBuilder", "new StringBuilder()")]
    for n, t, v in fields:
        variable(vars_, n, t, v)
    connectors = tag(m, "Connectors")
    embedded = tag(m, "EmbeddedObjects")
    first = ("((java.util.function.DoubleSupplier)()->{" + guard(LOADER, "load") + " return 0.5;}).getAsDouble()", "DAY")
    tick = block(embedded, "dayTick", "Source", 60, 1100, {
        "arrivalType": "self.INTERARRIVAL_TIME", "firstArrivalMode": "self.AT_TIME", "firstArrivalTime": first,
        "interarrivalTime": ("1.0", "DAY"), "limitArrivals": "true", "maxArrivals": N_DAYS,
        "locationType": "self.LOCATION_NOT_SPECIFIED", "onExit": guard(TICK, "tick")})
    entity_value(tick, "DayToken")
    block(embedded, "daySink", "Sink", 260, 1100, {"onEnter": guard(FINISH, "finish")})
    osrc = block(embedded, "orderSource", "Source", 60, 1300, {
        "arrivalType": "self.MANUAL", "locationType": "self.LOCATION_NOT_SPECIFIED",
        "onExit": "Order o=(Order)agent; o.qty=pendingQty; o.leadDays=pendingLead; o.placedDay=pendingDay;"})
    entity_value(osrc, "Order")
    block(embedded, "leadDelay", "Delay", 260, 1300, {
        "maximumCapacity": "true", "delayTime": ("((Order)agent).leadDays-0.5", "DAY")})
    block(embedded, "orderSink", "Sink", 460, 1300, {"onEnter": guard(RECEIVE, "receive")})
    for a, b in [("dayTick", "daySink"), ("orderSource", "leadDelay"), ("leadDelay", "orderSink")]:
        write_connection(connectors, a, b)
    presentation = m.find("Presentation/Level/Presentation")
    text = ident(tag(presentation, "Text"), "label", 30, 20)
    for k, v in [("DrawMode", "SHAPE_DRAW_2D"),
                 ("Text", "P2 | agent-built educational model (AnyLogic PLE) | inventory parameters are ASSUMPTIONS"),
                 ("Color", -13421773)]:
        tag(text, k, v)
    font = tag(text, "Font")
    tag(font, "Name", "SansSerif")
    tag(font, "Size", 14)
    tag(font, "Style", 1)
    tag(text, "Alignment", "LEFT")
    for cname, fs in (("DayToken", []), ("Order", [("qty", "double", "0"), ("leadDays", "int", "1"), ("placedDay", "int", "0")])):
        a = agent(classes, cname)
        av = tag(a, "Variables")
        for n, t, v in fs:
            variable(av, n, t, v)
    for k, v in [("DifferentialEquationsMethod", "EULER"), ("AbsoluteAccuracy", "1.0E-5"), ("FixedTimeStep", "0.01"),
                 ("RelativeAccuracy", "1.0E-5"), ("TimeAccuracy", "1.0E-5")]:
        tag(model, k, v)
    frame = ident(tag(model, "Frame"))
    tag(frame, "Width", 1300)
    tag(frame, "Height", 600)
    exps = tag(model, "Experiments")
    exp = ident(tag(exps, "SimulationExperiment", ActiveObjectClassId=mid), "Simulation")
    for k, v in [("MaximumMemory", 512), ("RandomNumberGenerationType", "fixedSeed"),
                 ("CustomGeneratorCode", "new java.util.Random()"), ("SeedValue", 1),
                 ("SelectionModeForSimultaneousEvents", "FIFO"), ("LoadRootFromSnapshot", "false")]:
        tag(exp, k, v)
    tag(exp, "Presentation")
    eps = tag(exp, "Parameters")
    for n, _, _ in params:
        p = tag(eps, "Parameter")
        tag(p, "ParameterName", n)
    pp = tag(exp, "PresentationProperties")
    for k, v in [("EnableZoomAndPanning", "true"), ("ExecutionMode", "virtualTime"),
                 ("Title", "P2 single store replenishment (agent-built, educational)"),
                 ("EnableDeveloperPanel", "true"), ("ShowDeveloperPanelOnStart", "true")]:
        tag(pp, k, v)
    mt = tag(exp, "ModelTimeProperties")
    for k, v in [("StopOption", "Never"), ("InitialDate", 1772409600000), ("InitialTime", 0),
                 ("FinalDate", 1835481600000), ("FinalTime", 100000000)]:
        tag(mt, k, v)
    tag(exp, "BypassInitialScreen", "true")
    specs = [  # name, title, {parameter: (from, to, step)}, number of runs
        ("SourceComparison", "P2 forecast source comparison: oracle, naive, ML (common random numbers)",
         {"forecastSource": ("0", "2", "1"), "repSeed": ("1", "10", "1")}, 30),
        ("PolicySweep", "P2 service-versus-stock sweep: policy x source x safety factor x seed",
         {"policy": ("0", "1", "1"), "forecastSource": ("0", "2", "1"), "serviceZ": ("0.0", "2.5", "0.5"),
          "repSeed": ("1", "5", "1")}, 180),
        ("LeadTimeSensitivity", "P2 lead-time sensitivity at safety factor 1.0: policy x source x lead time x seed",
         {"policy": ("0", "1", "1"), "forecastSource": ("0", "2", "1"), "leadTimeDays": ("3", "9", "2"),
          "repSeed": ("1", "5", "1")}, 120),
    ]
    fixed_override = {"LeadTimeSensitivity": {"serviceZ": "1.0"}}
    for ename, etitle, ranges, nruns in specs:
        pv = ident(tag(exps, "ParamVariationExperiment", ActiveObjectClassId=mid), ename)
        for k, v in [("CommandLineArguments", None), ("MaximumMemory", 512), ("RandomNumberGenerationType", "fixedSeed"),
                     ("CustomGeneratorCode", "new java.util.Random()"), ("SeedValue", 1),
                     ("SelectionModeForSimultaneousEvents", "FIFO"), ("VmArgs", None), ("LoadRootFromSnapshot", "false")]:
            tag(pv, k, v)
        tag(pv, "Presentation")
        tag(pv, "BypassInitialScreen", "true")
        for k, v in [("AllowParallelEvaluations", "false"), ("UseFreeformParameters", "false"), ("NumberOfRuns", nruns)]:
            tag(pv, k, v)
        for n, _, default in params:
            free = tag(pv, "FreeformParamValue")
            tag(free, "Id", pid[n])
            fixed = tag(pv, "RangeVariationParamValue")
            tag(fixed, "Id", pid[n])
            if n in ranges:
                lo, hi, step = ranges[n]
                tag(fixed, "Type", "RANGE")
                code(fixed, "From", lo)
                code(fixed, "To", hi)
                code(fixed, "Step", step)
            else:
                tag(fixed, "Type", "FIXED")
                code(fixed, "Expression", fixed_override.get(ename, {}).get(n, default))
        pt = tag(pv, "ModelTimeProperties")
        for k, v in [("StopOption", "Never"), ("InitialDate", 1772409600000), ("InitialTime", 0),
                     ("FinalDate", 1835481600000), ("FinalTime", 100000000)]:
            tag(pt, k, v)
        pp = tag(pv, "PresentationProperties")
        for k, v in [("EnableZoomAndPanning", "true"), ("Title", etitle), ("EnableDeveloperPanel", "true"),
                     ("ShowDeveloperPanelOnStart", "true")]:
            tag(pp, k, v)
        reps = tag(pv, "ReplicationsProperties")
        for k, v in [("UseReplication", "false"), ("FixedReplicationsNumber", "true"), ("ReplicationPerIteration", 1),
                     ("MinimumReplication", 1), ("MaximumReplication", 1), ("ConfidenceLevel", "LEVEL_95"),
                     ("ErrorPercent", 0.05), ("ExpressionForConfidenceComputation", 0)]:
            tag(reps, k, v)
    from animation_scene import install, configure_experiment
    install(__import__(__name__), m)
    configure_experiment(__import__(__name__), model)
    db = ident(tag(model, "Database"))
    for k, v in [("Logging", "false"), ("AutoExport", "false"), ("ShutdownCompact", "false")]:
        tag(db, k, v)
    tag(db, "ImportSettings")
    tag(db, "ExportSettings")
    run = ident(tag(model, "RunConfiguration", ActiveObjectClassId=mid), "RunConfiguration")
    tag(run, "MaximumMemory", 512)
    rt = tag(run, "ModelTimeProperties")
    for k, v in [("StopOption", "Never"), ("InitialDate", 1772409600000), ("InitialTime", 0),
                 ("FinalDate", 1835481600000), ("FinalTime", 100000000)]:
        tag(rt, k, v)
    animation = tag(run, "AnimationProperties")
    for k, v in [("StopNever", "true"), ("ExecutionMode", "virtualTime"), ("RealTimeScale", 1.0),
                 ("EnableZoomAndPanning", "true"), ("EnableDeveloperPanel", "true"), ("ShowDeveloperPanelOnStart", "true")]:
        tag(animation, k, v)
    tag(run, "Inputs")
    tag(run, "Outputs")
    lib = tag(model, "RequiredLibraryReference")
    for k, v in [("LibraryName", PML), ("VersionMajor", 8), ("VersionMinor", 0), ("VersionBuild", 5)]:
        tag(lib, k, v)
    markup = tag(model, "RequiredLibraryReference")
    for k, v in [("LibraryName", "com.anylogic.libraries.modules.markup_descriptors"), ("VersionMajor", 1),
                 ("VersionMinor", 0), ("VersionBuild", 0)]:
        tag(markup, k, v)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.alp"
    ET.ElementTree(ws).write(target, encoding="utf-8", xml_declaration=True)
    return target


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("--name", default="P2_Rossmann_Replenishment")
    cli.add_argument("--out", type=Path, default=ROOT / "model")
    cli.add_argument("--data-dir", default=DATA.as_posix())
    cli.add_argument("--output-dir", default=(ROOT / "results" / "native").as_posix())
    args = cli.parse_args()
    path = build(args.name, args.out, args.data_dir, args.output_dir)
    print(path)


if __name__ == "__main__":
    main()
