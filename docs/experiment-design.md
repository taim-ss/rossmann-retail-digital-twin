# P1 Experiment & Calibration Design — Retail Demand Digital Twin (Rossmann)

Author: experiment-designer (AnyLogic/PMS team), for the P1 pipeline Director. This is a design
document only — no code, no data touched. The Director/implementer builds against these exact
values; anything marked **[SIGN-OFF]** needs Taim's or the Director's explicit confirmation before
being built, because it resolves an ambiguity the P1/P2 prompts leave open.

Data facts used throughout: 1,115 stores, daily rows, 2013-01-01 to 2015-07-31 inclusive (912
days). Rossmann provides no stock, no orders, no lead times, no costs, no physical "units" — only
`Sales` (EUR), `Customers` (count), `Open`, `Promo`, `StateHoliday`, `SchoolHoliday`, and
`store.csv` attributes (`StoreType`, `Assortment`, `CompetitionDistance`, `Promo2`, ...).

## 0. Cross-cutting assumptions (resolve before building)

| # | Issue | Decision used below | Why it matters |
|---|---|---|---|
| 0.1 **[SIGN-OFF]** | P1 CONTRACT step 7 names the P2 demand column `actual_sales_units`, but Rossmann has no units-sold field, only `Sales` in EUR. | Treat demand as **EUR of daily sales**, not physical units. Rename the contract column to `actual_sales_eur` (or keep `actual_sales_units` as a label but document "unit = 1 EUR of sales" inline in `CONTRACT.md`). All inventory formulas in Section C use "unit = €1 of sales" as a normalization, not an estimate. | P2's order-up-to policy is written in "units"; if this isn't settled before P2 starts, its inventory levels are undefined. |
| 0.2 | Is `Open` (and therefore which days a store trades) known in advance for forecasting? | **Yes, by assumption** — treat the historical `Open`/`StateHoliday`/`SchoolHoliday` calendar as a known schedule input at any forecast origin, the same way a retailer knows its own holiday closure calendar ahead of time. Only `Sales` and `Customers` are the unknown target/leak columns. | Needed to define what counts as "leakage" in Section A — `Open` on the forecast date is a feature, not a leak. |
| 0.3 | `SchoolHoliday` — known in advance? | **Yes** — German school-holiday calendars are published terms ahead; treat as a known future feature. | Same reasoning as 0.2. |
| 0.4 | Store 622's missing `Open` values (known Rossmann data quirk). | Impute `Open = 1` unless `Sales == 0`, matching the standard community fix; document as a cleaning rule, test it (Section E.3). | Otherwise silently drops/corrupts one store's history. |

---

## A. Forecast backtest protocol

### A.1 Time split

| Segment | Date range | Role | Touch policy |
|---|---|---|---|
| Train | 2013-01-01 – 2014-12-31 | Model fitting (expanding window per fold, see A.2) | Reused every fold |
| Validation | 2015-01-01 – 2015-06-30 (181 days) | Model selection, hyperparameters, all metrics in A.5 | Iterate freely |
| **Locked final test** | 2015-07-01 – 2015-07-31 (31 days) | One confirmatory score, no tuning | **Touch exactly once.** Freeze every model config on validation results first; score July once; report the number even if it is worse than validation. No re-fitting after seeing it. |

### A.2 Rolling-origin folds

- **Forecast origins:** every 7 days starting 2015-01-01 up to the last origin whose 14-day horizon still lands inside the validation window.
  - Formula: `origins = {2015-01-01 + 7k : k = 0..23}` → last origin = **2015-06-11**, last forecasted date = 2015-06-25 (≤ 2015-06-30, never touches July).
  - **24 origins total.**
- **Horizons:** `h = 1..14` days ahead from each origin (covers the lead-time + review-period range P2 needs, roughly L+R ≤ 14).
  - Report both pooled (h1–14) and banded: **short** h1–3 (next review decision), **mid** h4–7, **long** h8–14.
- **Train window per fold:** expanding — all rows from 2013-01-01 to `origin − 1 day` inclusive. No fold ever sees data at or after its own origin.

### A.3 Models

| Model | Spec | Library |
|---|---|---|
| Naive | `forecast_t = actual_{origin-1}` (persistence), held flat across all 14 horizons | pandas |
| Seasonal naive A | `forecast_t = actual_{t-7}` (same weekday, last week) | pandas |
| Seasonal naive B | `forecast_t = mean(actual_{t-7}, actual_{t-14}, actual_{t-21}, actual_{t-28})` | pandas |
| Holt-Winters / ETS | Per-store, additive trend + weekly seasonality (`seasonal_periods=7`), fit on Open=1 rows of the train window only | `statsmodels.tsa.holtwinters.ExponentialSmoothing` |
| ML (global) | One `HistGradientBoostingRegressor` across all stores, store id as a categorical feature | `sklearn.ensemble.HistGradientBoostingRegressor` |
| **Oracle** | Not a model — `forecast = actual_sales` for the same date. Zero-error reference row, used only in P2 to isolate the policy effect from the forecast-error effect. WAPE/bias = 0 by construction; include as the sanity-check row in A.5's table, not as a competing model. | — |

Do **not** add `lightgbm` or `duckdb`; the stack is pandas/numpy/scipy/statsmodels/scikit-learn/sqlite3 only, per the brief's tool constraint. If the HistGradientBoostingRegressor underperforms badly enough to justify LightGBM, stop and ask before installing.

### A.4 ML feature list

| Allowed (known at forecast origin) | Forbidden (leakage) |
|---|---|
| `Store` (categorical), `DayOfWeek`, `Day`, `Month`, `Year`, `WeekOfYear`, `IsMonthStart/End` | `Customers` — never a feature at any horizon (near-contemporaneous with `Sales`, not actually knowable in advance either) |
| `Promo` (calendar-known per 0.2), `Promo2` (store attribute), `Promo2SinceWeek/Year`, promo-streak length | `Sales` on or after the forecast date (the target itself) |
| `StateHoliday`, `SchoolHoliday`, `IsDayBeforeHoliday` (derived from the calendar, not from sales) | Any lag/rolling feature whose window extends to or past the forecast origin |
| `StoreType`, `Assortment`, `CompetitionDistance`, `CompetitionOpenSinceMonth/Year` | Global statistics (e.g. "mean sales across all data") computed from the full dataset instead of train-only-up-to-origin |
| `Open` (calendar-known per 0.2) | Rows with `Open=0` used as if they were demand signal (see A.5) |
| Lag features: `lag7`, `lag14`, `lag21`, `lag28` sales; rolling mean/std of trailing 28/91 days — **all computed using only rows dated before the fold's origin** | |

### A.5 Closed-day handling

`Open=0` ⇒ `Sales=0` by definition — this is not a forecasting outcome, it's a calendar fact (per assumption 0.2). Rule:
- **Training:** fit the level models (Holt-Winters, ML) on `Open=1` rows only; do not let closed days drag down the fitted mean.
- **Scoring:** compute WAPE/bias (A.6) over `Open=1` days only, so all models are compared on the same non-trivial subset. Report separately: `closed_day_forecast = 0` always (by construction, 100% correct, not a modeling achievement — exclude from the accuracy table, mention once as a footnote).

### A.6 Metrics and segments

- **WAPE** = `Σ|actual − forecast| / Σ|actual|` over the set in question.
- **Bias** = `Σ(forecast − actual) / Σactual` (signed; positive = over-forecast).
- Both computed **per segment**, for every combination of: `StoreType` (a/b/c/d), `Assortment` (a/b/c), promo vs non-promo, weekday (Mon–Sun), sales-volume tercile (store's own mean `Sales` over the train window, split into 3 equal-count bins across the 1,115 stores). Report pooled h1–14 plus the three horizon bands (A.2).

**Bootstrap CI:** resample at the **store** level (not the day level — days within a store share serially correlated demand/noise, so day-level resampling would understate variance). For a given segment:
1. Compute each store's WAPE (and bias) aggregated over all its days/horizons in that segment.
2. Resample the resulting per-store vector with replacement, **B = 2,000** times (standard for a stable 95% percentile CI; cheap here since it resamples an already-aggregated ~1,115-length vector, not raw rows).
3. Recompute the segment's sales-weighted mean WAPE/bias on each resample.
4. Report the 2.5th/97.5th percentiles as the 95% CI.

### A.7 July 2015 lock protocol

1. Choose and freeze all model configs (HW parameters, GBM hyperparameters, feature set) using only the 24-fold validation results above.
2. Run every frozen model once on the 31-day locked test window (2015-07-01 to 2015-07-31).
3. Report WAPE/bias/CI exactly as computed, with no further tuning — even if the test number disagrees with validation. State the discrepancy as a finding, not a bug to fix by re-fitting.

---

## B. Calibration plan

| Model input | Source column(s) | Candidate distributions | GoF diagnostic | Acceptance rule |
|---|---|---|---|---|
| Daily demand level (per store, Open=1 days, train window) | `Sales` | Gamma, Lognormal, Normal (reference) | KS test vs each candidate's fitted CDF (MLE fit via `scipy.stats`); AIC across candidates; QQ-plot saved to `outputs/figures/` | Lowest AIC **and** KS p-value > 0.05; else fall back to **Empirical** (resampling), which is an allowed terminal choice |
| Promo uplift | `Sales` ratio: promo-day vs same-store same-weekday non-promo days (matched pairs) | Lognormal (on the ratio), Normal (on log-ratio) | KS test on log-ratio; AIC | Same rule as above; promo uplift is expected to pass Lognormal in most stores (multiplicative effect) |
| Weekday pattern | `Sales` grouped by `DayOfWeek`, store mean-normalized | Not a distribution — a 7-value multiplier table per store (or per `StoreType` cluster if a store's own history is too short) | Kruskal-Wallis test across weekdays (confirms the pattern is statistically real, not noise) | Report the factor table regardless; GoF is just the significance test, p < 0.05 required to keep store-level (vs falling back to StoreType-pooled) factors |
| Forecast-error distribution | Residuals = `actual − forecast` from the validation folds (A.2–A.6), pooled by store **and** by promo/non-promo | Empirical (primary/default — retail residuals are known fat-tailed around promos), Normal, Student-t (secondary/diagnostic) | Ljung-Box test for residual autocorrelation (must pass — i.i.d. assumption needed before scaling σ by √(R+L) in Section C); KS test if a parametric fit is attempted | Empirical is the default export; only replace with Normal/Student-t if KS p > 0.05 **and** Ljung-Box confirms no significant autocorrelation at lag ≤ 14 |
| Closed-day / holiday pattern | `Open`, `StateHoliday`, `SchoolHoliday` | Not a distribution — deterministic lookup/calendar rule (per assumption 0.2) | None (it's a rule, not a fit) — validate instead that predicted-closed days match `Open=0` with 100% accuracy (trivially true by construction; test in Section E) | N/A |

**`outputs/calibration_table.csv` exact columns:**

`store_id, input_name, segment, source_column, n_obs, fit_window_start, fit_window_end, fitted_distribution, param1_name, param1_value, param2_name, param2_value, param3_name, param3_value, goodness_of_fit_stat, goodness_of_fit_pvalue, notes_assumption`

- `input_name` ∈ {`daily_demand_level`, `promo_uplift`, `weekday_factor_mon`…`weekday_factor_sun`, `forecast_error_oracle`, `forecast_error_naive`, `forecast_error_ml`, `closed_day_rule`}.
- `segment`: the `StoreType`/`Assortment` pool used when a single store's history is too short to fit individually (document the minimum-n threshold, e.g. n < 180 open-days falls back to StoreType pooling).
- `fit_window_start/end`: always within the train window (≤ 2014-12-31) for the demand/promo/weekday rows; the forecast-error row's window is the validation folds (2015-01-01–2015-06-30), since errors only exist where there's a forecast to compare against.
- `notes_assumption`: free text flag, e.g. "pooled by StoreType due to n<180" or "Empirical fallback, Normal failed KS".

---

## C. Cost-of-error sensitivity grid

### C.1 Assumption cells (all labelled `ASSUMPTION` in the workbook)

| Cell | Base value | One-line justification | Low | High |
|---|---|---|---|---|
| Lead time `L` | 5 days | Mid-range of typical DC→store replenishment lead times for grocery/drugstore retail; Rossmann gives no data, this is a labelled guess | 2 | 10 |
| Review period `R` | 7 days | Weekly periodic-review cycle is the standard retail store-ordering cadence | 1 | 14 |
| Holding cost rate `h` (annual, % of unit value) | 25%/yr | Standard textbook retail inventory carrying-cost range (20–30%/yr, Chopra & Meindl) | 15% | 35% |
| Shortage cost / margin `m` | 30% | Typical drugstore gross margin; used as the foregone-margin proxy for the cost of one lost sale | 15% | 50% |
| Order cost `K` (fixed, per replenishment) | €50/order | Small-store fixed admin/handling cost estimate for placing one order | €10 | €150 |
| Unit price `p` | €1 (normalization) | **Not an independent estimate** — Rossmann has no unit price, so 1 "unit" is defined as €1 of `Sales` (ties to assumption 0.1). Scaling `p` uniformly doesn't change any cost *ratio* in the formulas below, so it is held fixed rather than swept. | — | — |

### C.2 One-way tornado

Sweep each of `L`, `R`, `h`, `m`, `K` across [low, high] one at a time, holding the others at base; rank by `|ΔExtraCost|` on the quantified finding (C.4). Expected ranking (to be confirmed once computed, not asserted here): `L` and `m` likely dominate because both enter the safety-stock/shortage term, which scales with `√(R+L)` and with the per-unit shortage cost; `K` likely has the smallest effect because the one quantified finding (C.4) isolates the SS/shortage cost term, not the ordering-cost term.

### C.3 Two-way table

Default pairing: **`L × m`** (lead time × shortage-cost ratio), since both drive the safety-stock/shortage term multiplicatively. **[SIGN-OFF]** — this is a design default; once the one-way tornado is actually computed, swap in whichever two levers show the largest one-way effect if different from `L`/`m`.

### C.4 The one quantified finding

**"Extra expected cost per store-year caused by forecast error on promotion days versus non-promotion days, under an order-up-to policy with safety stock from the empirical forecast-error distribution."**

Setup — order-up-to policy, periodic review `R`, lead time `L`:

```
SS(σ) = z · σ · sqrt(R + L)                         # safety stock, z = service-level factor
Q      = R · d̄                                       # avg order quantity, d̄ = forecast mean daily demand
avg_inventory(σ) = Q/2 + SS(σ)
HoldingCost(σ)   = SS(σ) · p · h                      # annual holding cost attributable to safety stock
                                                       # (the Q/2 cycle-stock term is error-independent — excluded from "extra cost")
L_loss(z) = φ(z) − z·(1 − Φ(z))                       # standard normal loss function
E_shortage_per_cycle(σ) = σ · sqrt(R+L) · L_loss(z)
ShortageCost(σ) = (365 / R) · E_shortage_per_cycle(σ) · (m · p)
ExtraCost(σ) = HoldingCost(σ) + ShortageCost(σ)        # EUR per store-year, as a function of forecast-error σ

Finding = ExtraCost(σ_promo) − ExtraCost(σ_nonpromo)
```

- `σ_promo`, `σ_nonpromo`: forecast-error std (empirical, per Section B) split by promo-day vs non-promo-day, per store, scaled to the R+L window as above (only valid if Ljung-Box in B passed — no significant autocorrelation).
- `z`: service-level assumption, base = 1.645 (95% target fill rate) — **ASSUMPTION**, add as its own labelled cell, not swept in the tornado (it's a policy choice, not a cost uncertainty) but worth a footnote sensitivity run if time allows.
- Units: EUR per store-year. Report per-store, then averaged (with CI, bootstrap over stores as in A.6) across the calibration set (Section D).
- **Excel implementation:** every symbol above (`z, σ_promo, σ_nonpromo, R, L, h, m, p`) is a named cell; `φ`/`Φ` via `NORM.S.DIST`; the formula chain is literally these 6 lines as live cell formulas, final cell = `Finding`.
- **Python recompute:** same formula using `scipy.stats.norm.pdf`/`.cdf`; Section E.9 asserts the two match.

**Sanity limit cases:**
| Condition | Expected result |
|---|---|
| `σ_promo = σ_nonpromo = 0` | `Finding = 0` exactly (zero error ⇒ zero extra cost) |
| `σ_promo = σ_nonpromo` (any value) | `Finding = 0` (no promo/non-promo *difference* even if error itself is nonzero) |
| `σ → ∞` (holding `R,L,h,m,p,z` fixed) | `ExtraCost(σ)` strictly increasing in `σ` (monotonicity, tested in E.11) |
| `R → 0` or `L → 0` | `SS → 0`, both cost terms shrink toward the error-independent baseline |

---

## D. P2 hand-off matrix

| Item | Rule |
|---|---|
| **Calibration store (1)** | Deterministic: filter to `StoreType='a'` (most common type, ~55% of stores) and `Assortment='a'`; within that set, pick the store whose train-window mean `Sales` is closest to the StoreType-a median; tie-break by lowest `Store` id. Pure function of the data — no RNG (tested in E.13). |
| **10 stores** | Stratify by `StoreType` present in the data (at least 1 store per type, proportional to population where possible) and, within each stratum, by sales-volume tercile (Section A.6); for each (StoreType, tercile) cell pick the store closest to that cell's median mean-`Sales`, tie-break by lowest `Store` id. Deterministic, reproducible, no duplicates. |
| **Forecast sources passed to P2** | Three contract files: `forecast_oracle.csv` (actuals), `forecast_naive.csv` = **seasonal-naive-lag7** (A.3's "Seasonal naive A" — expected to beat plain persistence; document this choice since the brief only asks for one "naive" file), `forecast_ml.csv` (HistGBM). Plain naive and the avg-of-4 variant stay as backtest-only baselines (Section A), not exported to P2. |
| **CRN scheme** | Parameter `repSeed` (integer, 0-based). One `java.util.Random(base_k + repSeed)` per stochastic source, fixed base offsets so the *same* `repSeed` draws identically regardless of which forecast source or policy is active: `base_demandNoise = 10_000`, `base_leadTimeVariation = 20_000`, `base_reserved = 30_000` (future use). Parameter Variation experiment sweeps `repSeed` × forecast source × policy parameters. Analyse **paired** differences per `repSeed`, never independent-sample comparisons. |
| **CRN verification** | Log the first 5 draws of each stream for `repSeed=0` under at least two different policy/forecast-source settings; assert the 5 draws are identical across settings (proves the stream is decoupled from the policy, i.e. true CRN and not just "a fixed seed"). |
| **Replications** | Pilot `n0 = 10` per (store × forecast-source × policy) cell. Compute 95% CI half-width / mean on total cost; if relative half-width > 5%, add in batches of 10 until under threshold or a cap of 100 reps is hit — report to the Director if the cap is hit without convergence. |
| **Warm-up / initial stock** | Terminating run (one per calendar horizon, not steady-state). Initial stock = the order-up-to level `S` computed from the first `R+L` days of **actual** historical demand (primes the system instead of a cold empty start). Discard the first `R+L` simulated days from all KPI accumulation. |
| **Paired comparison metrics** | For each store, each pair of forecast sources (ML–naive, ML–oracle, naive–oracle), same `repSeed`: per-replication paired `Δ` on total cost, fill rate, stock-out days, time-weighted mean on-hand. Aggregate with a paired t-test/Wilcoxon signed-rank + 95% CI on the mean paired difference, at **two levels**: within-store (across `repSeed`) and across the 10-store set (treating per-store mean Δ as the unit, to avoid pseudo-replication from pooling all reps across stores as if independent). |

**[SIGN-OFF] Scale flag for the Director:** 10 stores × 3 forecast sources × ≥1 policy variant × up to 100 replications × multiple `repSeed` values is on the order of several thousand runs. Per-run agent counts stay far under the 50,000-agent PLE cap (a handful of order/shipment agents per simulated day over ~900 days), so the cap itself isn't the risk — **wall-clock time to execute thousands of Parameter Variation runs in PLE is.** Confirm with Taim whether to cap total reps lower (e.g. 30 instead of 100) or reduce the store count for the full sweep before Taim starts building in AnyLogic.

---

## E. pytest checklist (exact assertions)

| # | Check | Exact assertion |
|---|---|---|
| 1 | No leak columns in ML features | `assert 'Sales' not in feature_columns and 'Customers' not in feature_columns` |
| 2 | No lag feature reaches into or past the origin | `assert feature_df.groupby('origin')['lag7_sales'].apply(lambda s: s.index.get_level_values('date').max()) .lt(feature_df['origin']).all()` (every lag-feature source date < its row's origin) |
| 3 | Train/validation/test date boundaries | `assert train_df['Date'].max() <= pd.Timestamp('2014-12-31')`; `assert validation_df['Date'].between('2015-01-01','2015-06-30').all()`; `assert test_df['Date'].between('2015-07-01','2015-07-31').all()`; `assert set(train_df.index).isdisjoint(validation_df.index)` |
| 4 | Closed-day cleaning | `assert (cleaned_df.loc[cleaned_df.Open==0, 'Sales'] == 0).all()` |
| 5 | Store 622 Open imputation | `assert cleaned_df.loc[cleaned_df.Store==622, 'Open'].isna().sum() == 0` |
| 6 | WAPE formula, zero-error case | `assert wape(actual, actual) == 0` |
| 7 | WAPE formula, known scalar case | `assert abs(wape(actual, 1.1*actual) - 0.1) < 1e-9` |
| 8 | Bias formula, known scalar case | `assert abs(bias(actual, 1.2*actual) - 0.2) < 1e-9` |
| 9 | Rolling-origin fold count and spacing | `assert len(origins) == 24`; `assert all((origins[i+1]-origins[i]).days == 7 for i in range(23))`; `assert origins[-1] + pd.Timedelta(days=14) <= pd.Timestamp('2015-06-30')` |
| 10 | Bootstrap CI reproducibility | `assert bootstrap_ci(values, seed=42) == bootstrap_ci(values, seed=42)` |
| 11 | Bootstrap CI contains point estimate | `assert ci_low <= point_estimate <= ci_high` |
| 12 | Distribution-fit GoF stat is a valid p-value | `assert 0.0 <= ks_pvalue <= 1.0` |
| 13 | Positive control for distribution fitting | fit Gamma to a synthetic `scipy.stats.gamma.rvs` sample → `assert ks_pvalue > 0.05` |
| 14 | Excel-vs-Python recompute parity (the one quantified finding) | `assert abs(python_extra_cost - excel_cell_value) <= 1e-6 * max(1.0, abs(excel_cell_value))` |
| 15 | Sanity limit: zero error ⇒ zero extra cost | `assert extra_cost(sigma_promo=0, sigma_nonpromo=0) == 0` |
| 16 | Sanity limit: equal errors ⇒ zero finding | `assert extra_cost(sigma, sigma) == 0` for any `sigma > 0` within float tolerance |
| 17 | Monotonicity in σ | `assert extra_cost(sigma=2*s) >= extra_cost(sigma=s)` for several sampled `s > 0` |
| 18 | CRN determinism (design-validation reference RNG, not the AnyLogic Java RNG) | `assert first_5_draws(base_k, rep_seed=0) == first_5_draws(base_k, rep_seed=0)` called twice |
| 19 | CRN decoupling from policy | `assert first_5_draws(base_k, rep_seed=0, policy='oracle') == first_5_draws(base_k, rep_seed=0, policy='ml')` |
| 20 | Calibration store selection determinism | `assert select_calibration_store(df) == select_calibration_store(df)` (pure function, called twice) |
| 21 | 10-store selection: count and no duplicates | `assert len(select_10_stores(df)) == 10 and len(set(select_10_stores(df))) == 10` |
| 22 | Contract file schema — demand file | `assert {'date','store','actual_sales_eur','promo','holiday','open'}.issubset(set(store_day_demand.columns))` (column name per assumption 0.1) |
| 23 | Contract file schema — forecast files | `assert list(forecast_ml.columns) == ['date','store','forecast_mean']` (same check repeated for `forecast_naive.csv`, `forecast_oracle.csv`) |
| 24 | No raw/redistributed data committed | `assert not any('raw' in path and path.endswith('.csv') for path in tracked_files)` (guards playbook rule: Rossmann CSVs/derived DBs never committed) |

---

## Open items for the Director / Taim

1. **[SIGN-OFF 0.1]** Rename or re-document the P1↔P2 contract column `actual_sales_units` → demand is modeled in EUR, not physical units (no unit-price data exists in Rossmann).
2. **[SIGN-OFF C.3]** Two-way sensitivity pairing defaults to `L × m`; confirm or swap after the one-way tornado is actually computed.
3. **[SIGN-OFF D]** Total P2 run count (store × forecast-source × policy × repSeed × replications) is in the low thousands; confirm the replication cap (100 vs lower) before Taim starts building the Parameter Variation experiment in AnyLogic PLE — this is a wall-clock risk, not a 50,000-agent-cap risk.
