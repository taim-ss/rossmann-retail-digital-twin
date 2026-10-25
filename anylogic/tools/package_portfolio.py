"""Build a local, data-excluding combined P1/P2 repository and zip. Never publishes."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
import shutil
import zipfile
import xml.etree.ElementTree as ET

P2=Path(__file__).resolve().parents[1]
P1=P2.parent if (P2.parent/"run_pipeline.py").exists() else P2.parents[2]/"retail-demand-digital-twin"

README="""# The forecast-driven store

**A retail decision model: SQL → Python → Excel → AnyLogic.**

Directed by Taim Salimoun; produced with AI assistance (Claude and Codex).
Educational work using AnyLogic Personal Learning Edition. Inventory and cost inputs
are labelled assumptions: the Rossmann dataset contains sales, but no stock or orders.

![Native store simulation](anylogic/model/store-view.png)

[Watch the native animation (GIF)](anylogic/model/store-animation.gif) ·
[MP4 recording](anylogic/model/store-animation.mp4)

| What a reviewer can inspect | Evidence |
|---|---|
| Real-data forecasting | 1,115 stores; ML WAPE 9.62% versus 18.08% for the four-week seasonal baseline |
| Replenishment | One store; static rule and oracle, seasonal-naive and ML order-up-to rules |
| Native verification | 30 initial runs plus 16 frontier checks; independent Python agreement within 2e-11 |
| Fair comparison | At 22k mean closing stock, ML fill 98.91% versus static 96.31%; paired difference +2.60 pp [1.69, 3.51] |
| Promotion days at that stock | ML versus static +3.94 pp [2.97, 4.92]; exploratory replica interpolation |
| Excel | Live assumptions/sensitivity workbook; 11 Excel/Python comparisons pass |
| Power BI | Aggregate inputs, DAX and build guide; no verified .pbix |

The confidence intervals for inventory cover **lead-time seeds only**. The policy grid
is Python-replica evidence checked at selected native points. The same January–June
2015 window supplies error calibration, tuning and evaluation. These are exploratory
simulation findings, not a measured operational saving or a real store floor plan.

## Read the project in five minutes

1. [Model report](anylogic/docs/report.md) explains the question, rules, results and limits.
2. [PDF model description](anylogic/model/model-description.pdf) shows the model and evidence.
3. [Pipeline methods](docs/PIPELINE.md) explains data cleaning, forecasts and calibration.
4. [AnyLogic README](anylogic/README.md) gives the native run and validation details.
5. [Power BI guide](powerbi/BUILD-GUIDE.md) describes the remaining manual dashboard build.

![Service versus stock](anylogic/results/analysis/frontier/service_vs_stock.png)

## Reproduce

Use Python 3.12 and the pinned dependencies in `requirements.txt`. On Windows,
Excel recalculation additionally needs Excel and pywin32; otherwise the pipeline
explicitly reports that the Excel parity check was skipped.

```
python -m pytest tests anylogic/tests -q
python run_pipeline.py --demo --skip-excel-check
```

For real data, accept the Kaggle competition rules and obtain your own `train.csv`
and `store.csv` following [data/README.md](data/README.md). No raw data, examples of
store-day data, forecast traces, native daily logs or private conversations are included.

```
python run_pipeline.py
python anylogic/tools/build_model.py --name P2_Rossmann_Replenishment --out anylogic/model/P2_Rossmann_Replenishment
```

Open the regenerated `.alp` in AnyLogic 8.9.10 PLE and choose **Animation**. Its Java
loader reads the five local contract CSVs produced by P1. The builder sets absolute
paths for your checkout. The packaged model is a source artifact; regenerate paths
before running on another machine. Use `--data-dir outputs/demo` for a synthetic demo.

The runner `anylogic/tools/native_runtime.py` uses a private workspace, a runtime
lease and fresh log directories. It closes only its own process tree. See the
AnyLogic README for exact commands. No standalone AnyLogic executable is exported.

## Repository map

`sql/` cleans and aggregates · `analysis/` forecasts/calibrates/builds Excel ·
`excel/` holds assumptions · `powerbi/` supplies DAX and aggregates · `outputs/`
contains shareable summaries · `anylogic/` contains the native model, independent
replica, evidence, animation, tests and report.

Taim's own-it exercises remain personal work: reimplement a small forecasting
baseline and rebuild/explain the core AnyLogic loop. Agent-built artifacts do not
establish hands-on authorship. [Prepared portfolio wording](anylogic/docs/PORTFOLIO-COPY.md)
is a local draft; nothing was pushed or posted.

## Kurzfassung

Dieses Lernprojekt verbindet SQL, Python, Excel und AnyLogic für die Bestandsplanung
einer Filiale. Die Prognosen basieren auf Rossmann-Umsatzdaten; Bestände, Lieferzeiten,
Kosten und Ladenlayout sind Modellannahmen. Native Läufe werden unabhängig mit Python
geprüft. Der Vergleich bei gleichem Bestand ist explorativ und kein Nachweis realer
Einsparungen. Die Umsetzung entstand durch KI-Agenten unter Taim Salimouns Leitung.
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package():
    required=[P2/"model/store-view.png",P2/"model/store-animation.gif",P2/"model/store-animation.mp4",P2/"model/model-description.pdf",
              P2/"docs/report.md",P2/"docs/PORTFOLIO-COPY.md",P2/"results/analysis/animation_verification.json"]
    missing=[str(p.relative_to(P2)) for p in required if not p.exists()]
    if missing:
        raise ValueError(f"Finish required evidence before packaging: {missing}")
    stamp=datetime.now().strftime("%Y%m%d-%H%M%S")
    target=P1/"dist"/f"rossmann-retail-digital-twin-{stamp}"
    target.mkdir(parents=True,exist_ok=False)

    def copy(source,rel):
        dest=target/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,dest)

    for name in ("run_pipeline.py","make_demo_data.py","requirements.txt",".gitignore"):
        copy(P1/name,name)
    for folder in ("analysis","sql","tests","docs","data"):
        for source in (P1/folder).glob("*"):
            if source.is_file() and source.suffix in (".py",".sql",".md"):
                copy(source,source.relative_to(P1))
    copy(P1/"README.md","docs/PIPELINE.md")
    for name in ("accuracy_by_segment.csv","calibration_table.csv","selected_stores.csv","run_summary.json","CONTRACT.md"):
        copy(P1/"outputs"/name,"outputs/"+name)
    for source in (P1/"excel").glob("assumptions_and_sensitivity.*"):
        copy(source,"excel/"+source.name)
    for source in (P1/"powerbi").rglob("*"):
        if source.is_file() and "demo" not in source.relative_to(P1/"powerbi").parts:
            copy(source,source.relative_to(P1))
    for folder in ("tools","analysis","tests","docs","model"):
        for source in (P2/folder).rglob("*"):
            rel=source.relative_to(P2)
            if not source.is_file() or any(p.startswith(".") or p=="__pycache__" for p in rel.parts):
                continue
            if source.suffix in (".py",".ps1",".md",".alp",".png",".gif",".mp4",".pdf",".json"):
                if source.name.startswith("_patch") or source.name in {
                    "CODEX-RESUME-2026-10-24.md","research-animation.md","store-setup-design.md"}:
                    continue
                copy(source,Path("anylogic")/rel)
    copy(P2/"README.md","anylogic/README.md")
    copy(P2/".gitignore","anylogic/.gitignore")
    for source in (P2/"results/analysis").rglob("*"):
        if source.is_file() and source.suffix in (".csv",".json",".png"):
            copy(source,Path("anylogic")/source.relative_to(P2))
    # No personal-machine paths in the packaged ALP; regenerate for a runnable checkout.
    for source in (target/"anylogic/model").rglob("*.alp"):
        tree=ET.parse(source)
        path_parameters={}
        for v in tree.getroot().iter("Variable"):
            if v.findtext("Name") in ("dataDirectory","outputDirectory"):
                val="outputs" if v.findtext("Name")=="dataDirectory" else "anylogic/results/native/local"
                v.find("Properties/DefaultValue/Code").text=json.dumps(val)
                path_parameters[v.findtext("Id")]=json.dumps(val)
        for v in tree.getroot().iter("RangeVariationParamValue"):
            if v.findtext("Id") in path_parameters:
                v.find("Expression/Code").text=path_parameters[v.findtext("Id")]
        tree.write(source,encoding="utf-8",xml_declaration=True)
    (target/"README.md").write_text(README,encoding="utf-8")
    with (target/".gitignore").open("a",encoding="utf-8") as f:
        f.write("\n# Combined-package local artifacts\nanylogic/results/native/\nanylogic/tools/.build/\n*.log\n*.zip\ndist/\n")
    forbidden={"train.csv","store.csv","test.csv","store_day_demand.csv","forecast_oracle.csv",
               "forecast_naive.csv","forecast_ml.csv","forecast_error_distribution.csv"}
    files=[p for p in target.rglob("*") if p.is_file()]
    bad=[str(p.relative_to(target)) for p in files if p.name in forbidden or p.suffix in (".log",".sqlite",".db",".jsonl")
         or p.name.startswith(".env") or "claude-resume" in str(p)]
    if bad:
        raise ValueError(f"Package contains excluded material: {bad}")
    manifest={"authorship":"Agent-built under Taim Salimoun's direction (Claude and Codex)",
              "raw_or_daily_data_included":False,"file_count":len(files),
              "files":{p.relative_to(target).as_posix():digest(p) for p in sorted(files)}}
    (target/"PACKAGE-MANIFEST.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    archive=target.with_suffix(".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for source in target.rglob("*"):
            if source.is_file():
                z.write(source,Path(target.name)/source.relative_to(target))
    info={"directory":str(target),"zip":str(archive),"files":len(files)+1,"sha256":digest(archive)}
    (P1/"dist/latest-package.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    print(json.dumps(info,indent=2))
    return target


if __name__=="__main__":
    package()
