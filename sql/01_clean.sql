-- 01_clean.sql
-- Purpose : raw_train (as loaded from train.csv) -> clean_store_day, one row per store and calendar day,
--           plus qa_log with the count of every data-quality rule that fired.
-- Inputs  : raw_train, params (min_date, max_date)
-- Outputs : calendar, clean_store_day, qa_log
-- Rules   : (R1) the grid is store x every calendar day; days missing from train.csv become closed days
--               (row_missing = 1), which catches the long refurbishment gaps.
--           (R2) StateHoliday is normalised to '0' or a/b/c (the raw column mixes 0 and '0').
--           (R3) Open missing: Sales > 0 means open; otherwise closed (demand unobservable, never guessed as open).
--           (R4) Open = 0 forces Sales = 0 (closed_with_sales counts how often the raw file disagreed).
--           (R5) Open = 1 with Sales = 0 is kept as an observed zero and flagged (open_zero_sales).
--           (R6) a closed run of 14 or more consecutive days is a long closure (long_closure = 1); such days
--               are not demand and are excluded from calibration and scoring downstream.

DROP TABLE IF EXISTS calendar;
CREATE TABLE calendar AS
WITH RECURSIVE days(d) AS (
    SELECT (SELECT value FROM params WHERE key = 'min_date')
    UNION ALL
    SELECT date(d, '+1 day') FROM days WHERE d < (SELECT value FROM params WHERE key = 'max_date')
)
SELECT s.store AS store, days.d AS date
FROM (SELECT DISTINCT Store AS store FROM raw_train) AS s
CROSS JOIN days;

DROP TABLE IF EXISTS clean_store_day;
CREATE TABLE clean_store_day AS
WITH joined AS (
    SELECT
        c.store,
        c.date,
        CAST(strftime('%w', c.date) AS INTEGER)                      AS dow_sun0,
        r.Store IS NULL                                              AS row_missing,
        CASE WHEN r.Sales IS NULL OR TRIM(CAST(r.Sales AS TEXT)) = '' THEN 0.0
             ELSE CAST(r.Sales AS REAL) END                          AS sales_raw,
        CAST(r.Customers AS REAL)                                    AS customers_raw,
        CASE WHEN r.Open IS NULL OR TRIM(CAST(r.Open AS TEXT)) = '' THEN NULL
             ELSE CAST(CAST(r.Open AS REAL) AS INTEGER) END          AS open_raw,
        COALESCE(CAST(r.Promo AS INTEGER), 0)                        AS promo,
        CASE WHEN LOWER(TRIM(CAST(r.StateHoliday AS TEXT))) IN ('a', 'b', 'c')
             THEN LOWER(TRIM(CAST(r.StateHoliday AS TEXT))) ELSE '0' END AS state_holiday,
        COALESCE(CAST(r.SchoolHoliday AS INTEGER), 0)                AS school_holiday
    FROM calendar AS c
    LEFT JOIN raw_train AS r ON r.Store = c.store AND date(r.Date) = c.date
),
resolved AS (
    SELECT
        *,
        CASE WHEN row_missing = 1 THEN 0
             WHEN open_raw IS NOT NULL THEN open_raw
             WHEN sales_raw > 0 THEN 1
             ELSE 0 END                                              AS open,
        CASE WHEN row_missing = 0 AND open_raw IS NULL THEN 1 ELSE 0 END AS open_imputed
    FROM joined
),
ordered AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY store ORDER BY date) AS rn,
        ROW_NUMBER() OVER (PARTITION BY store, open ORDER BY date) AS rn_state
    FROM resolved
),
runs AS (
    SELECT
        *,
        COUNT(*) OVER (PARTITION BY store, open, rn - rn_state) AS run_len
    FROM ordered
)
SELECT
    store,
    date,
    CASE WHEN dow_sun0 = 0 THEN 7 ELSE dow_sun0 END                  AS dow,
    CASE WHEN open = 1 THEN sales_raw ELSE 0.0 END                   AS sales,
    customers_raw                                                    AS customers,
    open,
    promo,
    state_holiday,
    CASE WHEN state_holiday <> '0' THEN 1 ELSE 0 END                 AS holiday,
    school_holiday,
    row_missing,
    open_imputed,
    CASE WHEN open = 0 AND row_missing = 0 AND sales_raw > 0 THEN 1 ELSE 0 END AS closed_with_sales,
    CASE WHEN open = 1 AND sales_raw = 0 THEN 1 ELSE 0 END           AS open_zero_sales,
    CASE WHEN open = 0 AND run_len >= 14 THEN 1 ELSE 0 END           AS long_closure
FROM runs;

CREATE INDEX idx_clean_store_date ON clean_store_day (store, date);

DROP TABLE IF EXISTS qa_log;
CREATE TABLE qa_log AS
SELECT 'store_days_in_grid'                          AS rule, COUNT(*)                       AS n FROM clean_store_day
UNION ALL SELECT 'rows_missing_from_raw (R1)',                SUM(row_missing)               FROM clean_store_day
UNION ALL SELECT 'open_value_imputed (R3)',                   SUM(open_imputed)              FROM clean_store_day
UNION ALL SELECT 'closed_days_total',                         SUM(1 - open)                  FROM clean_store_day
UNION ALL SELECT 'closed_with_positive_sales_zeroed (R4)',    SUM(closed_with_sales)         FROM clean_store_day
UNION ALL SELECT 'open_with_zero_sales_kept (R5)',            SUM(open_zero_sales)           FROM clean_store_day
UNION ALL SELECT 'long_closure_days (R6)',                    SUM(long_closure)              FROM clean_store_day
UNION ALL SELECT 'stores_with_a_long_closure (R6)',           COUNT(DISTINCT CASE WHEN long_closure = 1 THEN store END) FROM clean_store_day
UNION ALL SELECT 'state_holiday_days (R2)',                   SUM(holiday)                   FROM clean_store_day;
