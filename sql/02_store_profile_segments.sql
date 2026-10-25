-- 02_store_profile_segments.sql
-- Purpose : one profile row per store and the segment keys used for every per-segment metric.
-- Inputs  : clean_store_day, raw_store, params (train_end)
-- Outputs : store_profile (training period only), store_segment
-- Leakage : every statistic here uses dates <= train_end only, so the volume tercile of a store
--           never depends on the validation months it is later scored on.

DROP TABLE IF EXISTS store_profile;
CREATE TABLE store_profile AS
SELECT
    c.store,
    COUNT(*)                                                         AS n_open_days_train,
    AVG(c.sales)                                                     AS mean_sales_open_train,
    AVG(CASE WHEN c.promo = 1 THEN 1.0 ELSE 0.0 END)                 AS promo_share_train,
    MIN(c.date)                                                      AS first_open_date,
    MAX(c.date)                                                      AS last_open_date
FROM clean_store_day AS c
WHERE c.open = 1
  AND c.long_closure = 0
  AND c.date <= (SELECT value FROM params WHERE key = 'train_end')
GROUP BY c.store;

DROP TABLE IF EXISTS store_segment;
CREATE TABLE store_segment AS
WITH ranked AS (
    SELECT
        p.store,
        p.mean_sales_open_train,
        NTILE(3) OVER (ORDER BY p.mean_sales_open_train, p.store)    AS vol_rank
    FROM store_profile AS p
)
SELECT
    ranked.store,
    COALESCE(s.StoreType, 'unknown')                                 AS store_type,
    COALESCE(s.Assortment, 'unknown')                                AS assortment,
    CASE ranked.vol_rank WHEN 1 THEN 'low' WHEN 2 THEN 'mid' ELSE 'high' END AS volume_tercile,
    ranked.mean_sales_open_train,
    s.CompetitionDistance                                            AS competition_distance,
    COALESCE(s.Promo2, 0)                                            AS promo2
FROM ranked
LEFT JOIN raw_store AS s ON s.Store = ranked.store;
