# Rossmann retail demand pipeline: forecasts, calibration and assumed cost of forecast error (P1)

Built with AI assistance (Claude) under Taim Salimoun's direction. Educational/portfolio project, not client work.

## 1. The question — and the data gap, stated first

This project asks how good different forecasting methods are at predicting daily store demand for the
Rossmann drugstore chain, and what forecast error would cost under an assumed inventory-replenishment policy.
It is a data-and-calibration pipeline (SQL cleaning, Python backtesting, an Excel cost model, Power BI
dashboard inputs) built to feed a separate AnyLogic replenishment simulation (project P2, now built and checked natively) —
it is not itself a simulation.

**The data gap, up front, because it limits every number this pipeline can produce:** the Rossmann Kaggle
dataset has no stock levels, no purchase orders, no lead times and no cost data of any kind. `Sales` is daily
store turnover, not units sold. Whether that turnover is in EUR is the standard community reading of the
dataset (Rossmann is a German chain), not something confirmed on an official Kaggle page — treat "EUR" as an
assumption, not a fact. Every inventory, cost and currency figure that follows is a labelled assumption or a
normalization, never a measurement.

## 2. What is built, and what state it is in

| Step | Tool | Output | Status |
|---|---|---|---|
| Download Rossmann data | Kaggle (manual, by Taim) | `data/raw/train.csv`, `data/raw/store.csv` | Done 2026-10-24 by Taim's signed-in Kaggle account after joining the competition; SHA-256 values in `data/README.md` |
| Generate synthetic test data | `make_demo_data.py` | `data/demo/train.csv`, `data/demo/store.csv` | Built and run |
| SQL cleaning | `sql/01_clean.sql`, `02_store_profile_segments.sql`, `03_effects_aggregates.sql` (run via `analysis/load.py` into SQLite) | `clean_store_day`, `qa_log`, `store_profile`, segment/effect tables | Built; run on synthetic and real data (2026-10-24) |
| Panel build | `analysis/panel.py` | in-memory dense store x day arrays | Built; run on synthetic and real data (2026-10-24) |
| Rolling-origin backtest | `analysis/backtest.py`, `analysis/forecasters.py` | cached backtest under `outputs/<mode>/_work/` (gitignored) | Built; run on synthetic and real data (2026-10-24) |
| Accuracy tables | `analysis/accuracy.py`, `analysis/metrics.py` | `outputs/accuracy_by_segment.csv` | Built; run on synthetic and real data (2026-10-24) |
| Calibration table | `analysis/calibration.py` | `outputs/calibration_table.csv` | Built; run on synthetic and real data (2026-10-24) |
| Cost-of-error workbook | `analysis/cost_model.py`, `excel_build.py`, `excel_verify.py` | `excel/assumptions_and_sensitivity.xlsx` | Built; run on synthetic and real data (2026-10-24); Excel-vs-Python parity checked on both |
| P2 hand-off files | `analysis/contract.py` | `outputs/store_day_demand.csv`, `forecast_oracle/naive/ml.csv`, `selected_stores.csv`, `CONTRACT.md` | Built; run on synthetic and real data (2026-10-24) |
| Power BI data + measures | `analysis/powerbi_export.py` | `powerbi/data/*.csv`, `powerbi/measures.dax`, `BUILD-GUIDE.md` | Built; run on synthetic and real data (2026-10-24) |
| Power BI dashboard (.pbix) | Power BI Desktop | — | **Not built** — CSV data, DAX and guides are prepared; Taim builds the real-data dashboard from `powerbi/BUILD-GUIDE.md` (`powerbi/demo/BUILD-GUIDE.md` is the synthetic version) |
| July-2015 hold-out score | `python run_pipeline.py --final-test` | `outputs/<mode>/final_test_result.csv` | Built, not run — needs real data; the flag is written to refuse a second run so the hold-out stays a hold-out |
| AnyLogic replenishment model (P2) | AnyLogic PLE | Separate single-store model, native 2D animation and report | Complete single-store version: 30 baseline + 16 native spot checks match a Python replica (max difference 1.82e-11); static/replica service-stock experiments added. Native animation visually verified and recorded; one separate 171-record animated regression exactly matches the native ML baseline with zero summary difference |
| Own-it baseline exercise | `own_it/my_baseline.py` (Taim writes it) | — | **Own-it step: for Taim to do** (`docs/OWN-IT-guide.md`) |

The pipeline runs end to end from raw files with one command. On the real data (1,115 stores) the full run took
1,805 s (about 30 minutes) on the build machine; the 60-store synthetic demo takes about a minute with a cached backtest
(8 minutes without it on a machine under heavy load).

## 3. What is validated, and what is not

**Validated (methodology, on synthetic data and by direct check):**
- No-leakage tests: the ML feature set excludes `Sales` and `Customers`, and a "poison the future" test sets every
  sales value after a forecast cutoff to an absurd number and checks that the baselines, the ML features and the
  Holt-Winters forecasts do not change. ML training rows are asserted to end before each refit point.
- Store-level bootstrap confidence intervals on WAPE and bias (resampling whole stores, not store-days, because
  a store's own days are serially correlated).
- Excel-vs-Python parity on the cost-of-error formula: the workbook is recalculated in Excel (COM) and the
  same formula is recomputed independently in Python; in this session the two agreed on 11 comparisons.
- Parametric-bootstrap (Lilliefors-style) goodness-of-fit p-values for the demand and forecast-error
  distribution fits — used instead of a textbook KS table, which overstates the fit when parameters are
  estimated from the same sample being tested.
- Data-cleaning rules (closed-day handling, the Store-622-style `Open` imputation, `StateHoliday` coding) and
  the WAPE/bias formulas against known scalar cases.
- Limit cases of the cost-of-error formula: zero forecast error gives zero extra cost, equal promo/non-promo
  error gives zero finding, and extra cost increases monotonically with error.
- The full suite (`pytest tests`) gave 48 passed on 23 Oct 2026 on the build machine, all on synthetic data
  (about 1.5 to 2 minutes under load); the Excel parity test needs Excel and pywin32 and skips without them.
  Run it yourself to reproduce.

**NOT validated:**
- Anything beyond one 6-month validation window (2015-01-01 to 2015-06-24): the July 2015 hold-out (`--final-test`)
  has NOT been run, and no result has been checked on a second period or against a second dataset.
- The assumption that open days, promotions and holidays are known in advance. The ML model uses them as inputs; a
  real planner would know promotions and holidays, but store closures such as refurbishments are not always known.
- Any causal promotion effect — the promo-vs-non-promo comparison in the data is descriptive (Rossmann
  promotions are not randomized), not a causal estimate.
- The `sqrt(R + L)` independence assumption used to scale forecast-error variance into safety stock. This
  assumes forecast errors are uncorrelated day to day; `calibration_table.csv` reports a Ljung-Box statistic
  so the reader can see where that assumption looks shaky, but it is not confirmed to hold.
- The cost-model assumptions themselves — lead time, review period, holding rate, margin, order cost — are
  labelled `ASSUMPTION` cells with a sensitivity sweep, not measured values.
- That `Sales` is denominated in EUR (community reading, not an official source).

**Results (real Rossmann data, run of 2026-10-24; validation window 2015-01-01 to 2015-06-24, open days only).**
Everything below is read from `outputs/run_summary.json`, `outputs/accuracy_by_segment.csv`,
`outputs/calibration_table.csv` and `powerbi/data/fact_cost_kpi.csv`. These are single-window results with calendar
inputs assumed known in advance; they are not a claim about other periods or chains.

*Data cleaning* (SQL, `qa_log`): the store x day grid has 1,050,330 rows; 33,121 are absent from `train.csv` and become
closed days; 54 open days have zero sales (kept, flagged); `Open` has no missing values in `train.csv` (the store-622 quirk
belongs to `test.csv`); 31,050 state-holiday store-days; 221 stores have at least one closed run of 14 or more days
(34,849 days, treated as long closures and never scored). The "about 180 stores" figure seen in some notes has no source;
221 is what the rule R6 counts in this file.

*Forecast accuracy* (WAPE, lower is better, 95% CI from resampling stores, horizons 1 to 14 pooled):

| Model | WAPE | 95% CI | Bias |
|---|---|---|---|
| Gradient boosting (one global model) | 9.6% | 9.5 to 9.8% | +0.6% |
| Seasonal naive, mean of last 4 same weekdays | 18.1% | 17.9 to 18.3% | +2.3% |
| Holt-Winters (parameters frozen at 2014-12-31) | 21.0% | 20.7 to 21.3% | +0.5% |
| Seasonal naive, last same weekday | 23.1% | 22.8 to 23.4% | +1.1% |
| Naive, last open day | 24.5% | 24.1 to 24.8% | -3.3% |

The boosted model's error does not grow with the horizon (9.7% at 1 to 3 days, 9.6% at 8 to 14), which is consistent with
its promo, holiday and weekday inputs being treated as known for the whole window. By promotion status the 4-week-average
baseline has WAPE 21.2% on non-promo days and 15.5% on promo days, with bias +15.8% and -9.1% (it mixes promo and ordinary
days); the boosted model has WAPE 9.0% and 10.1% with bias -0.7% and +1.7%. Holt-Winters ignores promotions and does worse than the
simple average here; I did not tune it, so this says little about the method in general.

*Calibration* (`calibration_table.csv`, 20,071 rows): a gamma, lognormal or normal family passes the bootstrap goodness-of-fit
test for the weekday-normalised daily demand of only 72 of 1,115 stores (6.5%); for the other 1,043 the table says
`empirical` (resample the observed values). Promotion uplift (promo day vs ordinary same-weekday days within 28 days) has a
median ratio of 1.41 per store (inter-quartile range 1.33 to 1.50); a lognormal passes for 668 stores, 447 are `empirical`.
Forecast errors are NOT independent across days: the Ljung-Box test at lag 14 rejects independence for 79% of stores for the
boosted model and for all stores for the seasonal naive, so the sqrt(R+L) scaling in the cost formula is optimistic.

*Assumed cost of forecast error* (`excel/assumptions_and_sensitivity.xlsx`, assumptions: lead time 5 days, review period 7
days, holding rate 25% a year, margin 30%, service level 95%, one unit = EUR 1 of turnover): a store whose daily error behaved
like its promotion days instead of its ordinary days would carry about EUR 977 more cost per store-year (95% store-bootstrap
CI 934 to 1,018). This is an assumption-driven comparison, not a measured saving. One-way sensitivity (EUR per store-year
at the low and high end): review period 1 to 14 days 2,895 to 903 (largest lever), margin 15 to 50% 815 to 1,193, holding rate
15 to 35% 794 to 1,160, lead time 2 to 10 days 846 to 1,163, order cost no effect by construction. The two-way table in the
workbook crosses lead time and margin, as the design had it; review period would have been the more informative pair.

*Not run:* the July 2015 hold-out and any model tuning. The 10 stores plus calibration store for P2 are listed in
`outputs/selected_stores.csv` (calibration store 164).

## 4. How to run

1. Download the data: follow `data/README.md` (Kaggle login, accept competition rules, download
   `train.csv` and `store.csv` into `data/raw/`).
2. Real run, once the data is downloaded:
   ```
   python run_pipeline.py
   ```
3. Demo run on synthetic data, no download needed:
   ```
   python run_pipeline.py --demo
   ```
4. July-2015 hold-out — **once only**, after every model is frozen on validation results:
   ```
   python run_pipeline.py --final-test
   ```
   This refuses to run a second time if `final_test_result.csv` already exists, so the hold-out cannot be
   scored, tuned against, and rescored.
5. Tests: `pytest tests` (see section 3 for the last recorded result).

## 5. Repository map

- `sql/` — numbered cleaning and aggregation SQL (`01_clean.sql`, `02_store_profile_segments.sql`,
  `03_effects_aggregates.sql`), run against SQLite.
- `analysis/` — the Python pipeline: loading, panel construction, forecasters, backtest, metrics, accuracy,
  calibration, cost model, Excel build/verify, P2 contract, Power BI export.
- `excel/` — the cost-of-error workbook with live formulas (`demo/` holds the synthetic-data version).
- `powerbi/` — CSV inputs, DAX measures and a build guide for a dashboard Taim builds himself in Power BI
  Desktop (`demo/` holds the synthetic-data version).
- `outputs/` — run outputs: accuracy tables, calibration table, run summary, and the P2 hand-off files
  (`demo/` holds the synthetic-data version; per-store-day files are gitignored on real data).
- `tests/` — pytest suite: cleaning, metrics, forecasting, calibration/contract, cost model and Excel parity.
- `docs/` — `experiment-design.md` (the full backtest/calibration/cost-model design and the pytest checklist
  it is built from) and `OWN-IT-guide.md` (linked in section 8 below).
- `data/` — `README.md` (download steps, Kaggle terms, the gitignored `raw/` folder) and `demo/` (synthetic
  CSVs with the same columns as Rossmann).
- `run_pipeline.py`, `make_demo_data.py` — the one-command entry points.

## 6. Files handed to P2 (the AnyLogic replenishment model)

The exact contract is documented in `outputs/demo/CONTRACT.md` (synthetic version; the same file shape is
produced for real data in `outputs/CONTRACT.md`). In short: a calibration store plus 10 stratified stores, a
per-store-day demand file, three forecast files (oracle, seasonal-naive, ML), and an empirical forecast-error
distribution file. Per-store-day files are **gitignored** and are regenerated by `python run_pipeline.py` —
they are never committed, because they are derived from data that cannot be redistributed. The demand column
is in "units" only by the normalization that 1 unit = EUR 1 of turnover (section 1); it is not a count of
physical items, and P2's inventory levels inherit that caveat.

## 7. Limits and honest wording

**What "digital twin" means here:** this repository is a data-cleaning, forecasting-backtest and
cost-calibration backbone — it is not a live, stateful twin of a store. The actual discrete-event simulation
(the thing that behaves like a twin, with inventory state evolving day to day) is project P2, a separate
AnyLogic model now built for store 164, with 30 baseline and 16 additional native checks against an independent
Python replica. Its native 2D animation is visually verified and authentically recorded, and a separate complete animated
regression exactly preserves the native ML baseline's 171 daily records, deliveries and random draws with zero summary difference. Calling this pipeline itself a "digital twin" without that
distinction would overstate what it does.

**Data licensing:** no Rossmann data is redistributed. `train.csv` and `store.csv` are not committed to this
repository, under no circumstances, because the Kaggle competition page requires accepting its rules before
downloading. Source: <https://www.kaggle.com/competitions/rossmann-store-sales>. The model and pipeline are
learned from and run against public Kaggle data for educational/portfolio use only.

**PLE / educational use:** any AnyLogic component built for this project set uses the free Personal Learning
Edition, which is licensed for learning, not commercial deployment — stated here so this is never read as
client work.

**Authorship (section 8 below) and own-it step (`docs/OWN-IT-guide.md`):** Taim should be able to explain
every sentence of this README and every design choice in `docs/experiment-design.md`, including the ones he
did not type himself.

## 8. Authorship

This pipeline was built with AI assistance (Claude) under Taim Salimoun's direction: an AI agent team produced the
SQL, Python, Excel and Power BI inputs, the design documents (`docs/experiment-design.md`,
`docs/research-p1-sources.md`) and this README. The Power BI dashboard itself is not built. The one piece meant to be
written by hand is described in `docs/OWN-IT-guide.md`: re-implementing the seasonal-naive baseline and its WAPE on
one store without AI help. Until that is done and checked, nothing here should be described as hand-built.

## 9. Kurzfassung (Deutsch)

Dieses Projekt untersucht, wie gut verschiedene Prognosemethoden die tägliche Filialnachfrage der
Rossmann-Drogeriekette vorhersagen, und was Prognosefehler unter einer angenommenen
Lagerbestands-Nachschubpolitik kosten würden. Die Rossmann-Daten aus dem Kaggle-Wettbewerb enthalten jedoch
keine Lagerbestände, Bestellungen, Lieferzeiten oder Kosten; die Spalte „Sales" ist der Tagesumsatz, nicht die
verkaufte Stückzahl, und ob dieser Umsatz in Euro angegeben ist, ist lediglich die übliche Annahme in der
Community, keine offizielle Angabe. Die Pipeline (SQL-Bereinigung, Python-Backtest, Excel-Kostenmodell,
Power-BI-Grundlagen) wurde sowohl mit synthetischen Testdaten als auch mit den echten Rossmann-Daten vollständig
durchlaufen (Validierungszeitraum Januar bis Juni 2015). Das Gradient-Boosting-Modell erreicht dort einen gewichteten
Prognosefehler (WAPE) von 9,6 % gegenüber 18,1 % beim einfachen saisonalen Vergleichsmodell; diese Werte gelten für einen
einzelnen Zeitraum und setzen voraus, dass Aktions- und Feiertagskalender im Voraus bekannt sind. Validiert
sind Methodik-Aspekte wie die Leckage-Tests, die Bootstrap-Konfidenzintervalle auf Filialebene und die
Übereinstimmung von Excel- und Python-Berechnung des Kostenmodells; nicht validiert sind der Hold-out-Zeitraum Juli 2015,
jeder kausale Promotion-Effekt, die Unabhängigkeit der Prognosefehler (sie ist bei den meisten Filialen verletzt) und die
Kostenannahmen selbst. Die eigentliche
Nachschub-Simulation in AnyLogic (Projekt P2) ist separat aufgebaut und anhand von 30 ursprünglichen und 16 zusätzlichen
nativen Läufen gegen eine Python-Nachbildung geprüft. Die native 2D-Ladenanimation ist visuell geprüft und authentisch aufgezeichnet;
ein zusätzlicher vollständiger animierter Lauf stimmt bei 171 Tagesdatensätzen, Lieferungen, Zufallszahlen und Abschlusswerten exakt mit dem nativen ML-Referenzlauf überein. Diese
Pipeline ist eine Daten- und Kalibrierungsgrundlage dafür, kein eigenständiger "digitaler Zwilling". Das
Projekt wurde mit KI-Unterstützung (Claude) unter der Leitung von Taim Salimoun erstellt und dient
ausschließlich Lern- und Portfoliozwecken.
