-- 03_effects_aggregates.sql
-- Purpose : promotion / holiday / weekday effects and the aggregate tables the Power BI model reads.
-- Inputs  : clean_store_day, store_segment, params (train_end)
-- Outputs : promo_effect_store, weekday_profile_store, holiday_effect, agg_month_segment
-- Scope   : effects use training-period days that are open, not a long closure and not a state holiday,
--           so a promotion is compared with ordinary non-promotion days of the same store.
-- Caveat  : a promo-vs-non-promo ratio is descriptive. Rossmann promotions are not randomised, so this
--           is an uplift estimate under that selection, not a causal effect.

DROP TABLE IF EXISTS promo_effect_store;
CREATE TABLE promo_effect_store AS
SELECT
    c.store,
    SUM(c.promo = 1)                                                 AS n_promo_days,
    SUM(c.promo = 0)                                                 AS n_nonpromo_days,
    AVG(CASE WHEN c.promo = 1 THEN c.sales END)                      AS mean_sales_promo,
    AVG(CASE WHEN c.promo = 0 THEN c.sales END)                      AS mean_sales_nonpromo,
    AVG(CASE WHEN c.promo = 1 THEN c.sales END)
      / NULLIF(AVG(CASE WHEN c.promo = 0 THEN c.sales END), 0)       AS promo_uplift_ratio
FROM clean_store_day AS c
WHERE c.open = 1 AND c.long_closure = 0 AND c.holiday = 0
  AND c.date <= (SELECT value FROM params WHERE key = 'train_end')
GROUP BY c.store;

DROP TABLE IF EXISTS weekday_profile_store;
CREATE TABLE weekday_profile_store AS
WITH base AS (
    SELECT c.store, c.dow, c.sales
    FROM clean_store_day AS c
    WHERE c.open = 1 AND c.long_closure = 0 AND c.holiday = 0 AND c.promo = 0
      AND c.date <= (SELECT value FROM params WHERE key = 'train_end')
),
store_mean AS (SELECT store, AVG(sales) AS store_mean FROM base GROUP BY store)
SELECT
    b.store,
    b.dow,
    COUNT(*)                                                         AS n_days,
    AVG(b.sales)                                                     AS mean_sales,
    AVG(b.sales) / NULLIF(m.store_mean, 0)                           AS weekday_index
FROM base AS b
JOIN store_mean AS m ON m.store = b.store
GROUP BY b.store, b.dow;

DROP TABLE IF EXISTS holiday_effect;
CREATE TABLE holiday_effect AS
SELECT
    'school_holiday' AS effect,
    AVG(CASE WHEN c.school_holiday = 1 THEN c.sales END)
      / NULLIF(AVG(CASE WHEN c.school_holiday = 0 THEN c.sales END), 0) AS ratio_vs_reference,
    SUM(c.school_holiday = 1) AS n_days
FROM clean_store_day AS c
WHERE c.open = 1 AND c.long_closure = 0 AND c.holiday = 0 AND c.promo = 0
  AND c.date <= (SELECT value FROM params WHERE key = 'train_end')
UNION ALL
SELECT
    'state_holiday_closed_share',
    AVG(CASE WHEN c.open = 0 THEN 1.0 ELSE 0.0 END),
    COUNT(*)
FROM clean_store_day AS c
WHERE c.holiday = 1 AND c.long_closure = 0
  AND c.date <= (SELECT value FROM params WHERE key = 'train_end');

DROP TABLE IF EXISTS agg_month_segment;
CREATE TABLE agg_month_segment AS
SELECT
    strftime('%Y-%m', c.date)                                        AS month,
    g.store_type,
    g.assortment,
    g.volume_tercile,
    COUNT(DISTINCT c.store)                                          AS n_stores,
    SUM(c.open)                                                      AS open_store_days,
    SUM(c.sales)                                                     AS sales_total,
    SUM(CASE WHEN c.promo = 1 AND c.open = 1 THEN c.sales ELSE 0 END) AS sales_promo_days,
    SUM(CASE WHEN c.promo = 1 AND c.open = 1 THEN 1 ELSE 0 END)      AS promo_open_days
FROM clean_store_day AS c
JOIN store_segment AS g ON g.store = c.store
WHERE c.long_closure = 0
GROUP BY month, g.store_type, g.assortment, g.volume_tercile;
