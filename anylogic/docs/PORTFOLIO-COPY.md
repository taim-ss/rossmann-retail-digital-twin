# Portfolio wording — drafts for Taim's review

Prepared for the combined P1/P2 project. The CV wording is ready to copy; the LinkedIn text remains an optional draft. Taim's actual CV and LinkedIn account have not been changed. Authorship remains tier B: an AI agent team produced the implementation under Taim Salimoun's direction; his personal rebuild is not yet complete.

## CV bullet

**Retail Forecasting & Replenishment — SQL, Python, Excel, AnyLogic:** Directed AI-assisted development of a forecasting pipeline for 1,115 stores and an animated inventory model; achieved 9.62% forecast WAPE versus 18.08% for a seasonal baseline, with 46 native AnyLogic runs independently verified in Python.

Shorter version when space is tight:

Directed an AI agent team to build a SQL/Python-to-AnyLogic replenishment study; verified 46 baseline/spot-check native runs against a Python replica and compared stock/service trade-offs for one Rossmann store under assumed lead times and costs.

The 46 refers to the original 30 plus the new 16-run check set. One earlier static-policy check exists separately. Do not call these 46 native grid runs, claim personal editor authorship, or describe assumption-driven cost differences as realised savings.

## GitHub description

Educational Rossmann forecasting and single-store replenishment study: SQL, Python, Excel and AnyLogic, with native/replica checks and service–stock comparisons. Built by an AI agent team under Taim Salimoun's direction.

Suggested repository title: **Forecast-informed retail replenishment**

Suggested README opening:

How much inventory does a forecast-informed ordering rule need to serve the same demand as a simpler rule? This educational project connects a SQL/Python forecasting pipeline, an Excel assumptions workbook and an AnyLogic replenishment model for one Rossmann store. A separately implemented Python replica checks native runs and supports clearly labelled exploratory sweeps. Costs and supplier behaviour are assumptions because the dataset contains sales, not inventory operations.

Implementation was produced by Claude/Codex AI agents under Taim Salimoun's direction. The AnyLogic component uses Personal Learning Edition. Power BI CSV inputs, DAX and a build guide are prepared; a completed Power BI dashboard is not included. Taim's independent rebuild remains a separate next step.

## LinkedIn draft

I wanted to understand a practical question: does a better demand forecast help an inventory decision, or does it only improve an accuracy score?

I directed a Claude/Codex AI agent team to connect a Rossmann data pipeline to a replenishment model for one store. The workflow spans SQL cleaning, Python forecasting, an Excel assumptions workbook and AnyLogic ordering and delivery logic. An independent Python replica checks the simulation and makes larger exploratory comparisons affordable.

The native 2D store view has also been visually checked running and authentically recorded: aisles, stock bars, customers, checkout lanes and a live inventory panel. A separate complete animated run preserved all 171 daily records, delivery records and lead-time random draws exactly against the native ML baseline, with zero summary difference. Customer paths and cashier activity are illustrative, not a staffing or queueing study.

One useful result: at the same average closing stock of 22,000 turnover-based units, ML served 99.81% of promotion-day demand versus 95.87% for a static rule. The paired improvement was 3.94 percentage points, with a 95% interval of 2.97–4.92 points across ten lead-time seeds.

That result comes from an interpolated Python-replica experiment, not a full native AnyLogic sweep. The original 30 native runs and 16 further spot checks agree with the replica to within 1.82 × 10⁻¹¹. Numerical agreement checks implementation; it does not make the operating assumptions real.

The limitations matter: one store, one January–June window, assumed supplier behaviour and costs, error calibration and policy tuning on the evaluation period, and sales used as a demand proxy. This is an educational study, not a claim of realised savings or commercial deployment.

I directed and reviewed the agent-built work. My next personal step is to rebuild the baseline and inventory loop myself and explain the decisions without relying on generated code.

## Evidence to keep beside any public claim

| Claim | Local evidence / qualification |
|---|---|
| Native/replica agreement | `results/analysis/analysis.json` and `native_spotchecks.json`; original 30 + new 16 checks, full grid not native |
| Promotion-day +3.94 points at 22,000 stock | `results/analysis/frontier/fair_comparison.json`; per-seed interpolation, replica, lead-time-only CI |
| About 15% more static stock at 99% fill | `stock_needed_for_service.csv`; mean-curve interpolation, 25,555 static vs 22,237 ML; assumed five-day lead time |
| P1 forecast accuracy | P1 `outputs/run_summary.json`; ML WAPE 9.62%, four-week same-weekday baseline 18.08%; these are pooled-store figures and this baseline differs from P2's last-weekday naive |
| Animation | Native 2D view visually verified and authentically recorded: [store capture](../model/store-view.png), [animation GIF](../model/store-animation.gif), [MP4](../model/store-animation.mp4). Separate complete 171-record animated regression exactly matches the native ML baseline; `results/analysis/animation_verification.json` records zero summary difference. Customer/cashier activity is illustrative |
| Dashboard | Say “Power BI data, DAX and build guide”; no `.pbix` is claimed |

Before publishing, replace any project link with the actual reviewed repository URL, check that raw and per-store-day derived data are excluded, and confirm that each claimed visual or personal rebuild has actually been completed. No public URL is invented here.

Additional review artifacts: [PDF model description](../model/model-description.pdf) and [flow schematic](../model/model-flow.png). The flow image is an explanatory schematic, not an editor-canvas screenshot. The native visual acceptance is 2D; no 3D walkthrough is claimed.
