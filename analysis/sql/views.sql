-- ============================================================================
-- FoodPulse — Power BI-facing views
-- Run against the `foodpulse` PostgreSQL database. These views are the
-- intended connection points for Power BI (rather than raw tables or the
-- ad-hoc queries in queries.sql).
-- ============================================================================


-- ============================================================================
-- VIEW 1: v_cohort_retention
-- Materializes the cohort retention matrix (see queries.sql QUERY 1) and adds:
--   cohort_size      - total customers acquired in that cohort_month
--   retention_index  - this cohort's retention_pct at a given tenure, relative
--                       to the average retention_pct of ALL cohorts at that
--                       same tenure (>1 = outperforming peers of the same age)
-- ============================================================================
CREATE OR REPLACE VIEW v_cohort_retention AS
WITH first_order AS (
    SELECT customer_id, MIN(order_date) AS first_order_date
    FROM orders
    GROUP BY customer_id
),
cohort AS (
    SELECT c.customer_id, c.cohort_month, fo.first_order_date
    FROM customers c
    JOIN first_order fo ON fo.customer_id = c.customer_id
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM cohort
    GROUP BY cohort_month
),
order_activity AS (
    SELECT o.customer_id, coh.cohort_month,
           (DATE_PART('year', o.order_date) - DATE_PART('year', coh.first_order_date)) * 12
           + (DATE_PART('month', o.order_date) - DATE_PART('month', coh.first_order_date)) AS months_since_first
    FROM orders o
    JOIN cohort coh ON coh.customer_id = o.customer_id
),
target_months AS (
    SELECT unnest(ARRAY[0, 1, 2, 3, 6, 9, 12]) AS months_since_first
),
retention AS (
    SELECT coh.cohort_month, tm.months_since_first,
           COUNT(DISTINCT oa.customer_id) AS customer_count
    FROM cohort coh
    CROSS JOIN target_months tm
    LEFT JOIN order_activity oa
           ON oa.customer_id = coh.customer_id
          AND oa.months_since_first = tm.months_since_first
    GROUP BY coh.cohort_month, tm.months_since_first
),
matrix AS (
    SELECT r.cohort_month,
           r.months_since_first,
           cs.cohort_size,
           r.customer_count,
           ROUND(100.0 * r.customer_count / cs.cohort_size, 2) AS retention_pct
    FROM retention r
    JOIN cohort_sizes cs ON cs.cohort_month = r.cohort_month
)
SELECT cohort_month,
       months_since_first,
       cohort_size,
       customer_count,
       retention_pct,
       ROUND(retention_pct / NULLIF(AVG(retention_pct) OVER (PARTITION BY months_since_first), 0), 3) AS retention_index
FROM matrix
ORDER BY cohort_month, months_since_first;


-- ============================================================================
-- VIEW 2: v_customer_segments
-- One row per customer: lifecycle attributes, RFM segment, discount
-- dependency group, and a 90-day churn flag. The primary customer-grain
-- dimension table for Power BI.
-- ============================================================================
CREATE OR REPLACE VIEW v_customer_segments AS
WITH snapshot AS (
    SELECT MAX(order_date) AS snapshot_date FROM orders
),
customer_orders AS (
    SELECT o.customer_id,
           COUNT(*) AS total_orders,
           SUM(o.net_order_value) AS total_spend,
           AVG(o.net_order_value) AS avg_order_value,
           MIN(o.order_date) AS first_order_date,
           MAX(o.order_date) AS last_order_date
    FROM orders o
    GROUP BY o.customer_id
),
customer_delay AS (
    SELECT o.customer_id, AVG(de.delivery_delay_min) AS avg_delivery_delay
    FROM orders o
    JOIN delivery_events de ON de.order_id = o.order_id
    GROUP BY o.customer_id
),
customer_discounts AS (
    SELECT o.customer_id, COUNT(DISTINCT d.order_id) AS discounted_orders
    FROM orders o
    LEFT JOIN discounts d ON d.order_id = o.order_id
    GROUP BY o.customer_id
),
rfm AS (
    SELECT co.customer_id,
           (SELECT snapshot_date FROM snapshot) - co.last_order_date AS recency_days,
           co.total_orders AS frequency,
           co.total_spend AS monetary,
           -- customer_id appended as a deterministic tie-breaker: total_orders and
           -- total_spend both have large tie clusters (e.g. one-time buyers all
           -- share total_orders=1), and NTILE() has no guaranteed behavior for tied
           -- rows without one -- without this, bucket boundaries (and therefore
           -- rfm_segment/Champion counts) could drift between query executions.
           NTILE(4) OVER (ORDER BY (SELECT snapshot_date FROM snapshot) - co.last_order_date DESC, co.customer_id) AS r_score,
           NTILE(4) OVER (ORDER BY co.total_orders ASC, co.customer_id) AS f_score,
           NTILE(4) OVER (ORDER BY co.total_spend ASC, co.customer_id) AS m_score
    FROM customer_orders co
),
profile AS (
    SELECT c.customer_id, c.city, c.acquisition_channel, c.cohort_month, c.signup_date,
           co.total_orders, co.total_spend, co.avg_order_value,
           co.first_order_date, co.last_order_date,
           (SELECT snapshot_date FROM snapshot) - co.last_order_date AS days_since_last_order,
           cd.avg_delivery_delay,
           100.0 * cdisc.discounted_orders / co.total_orders AS discount_pct_of_orders,
           r.r_score, r.f_score, r.m_score
    FROM customers c
    JOIN customer_orders co ON co.customer_id = c.customer_id
    JOIN customer_delay cd ON cd.customer_id = c.customer_id
    JOIN customer_discounts cdisc ON cdisc.customer_id = c.customer_id
    JOIN rfm r ON r.customer_id = c.customer_id
)
SELECT customer_id, city, acquisition_channel, cohort_month, signup_date,
       total_orders, total_spend, avg_order_value,
       first_order_date, last_order_date, days_since_last_order,
       avg_delivery_delay,
       ROUND(discount_pct_of_orders, 2) AS discount_pct_of_orders,
       CASE
           WHEN discount_pct_of_orders = 0 THEN 'Never'
           WHEN discount_pct_of_orders <= 30 THEN 'Light'
           WHEN discount_pct_of_orders <= 60 THEN 'Moderate'
           ELSE 'Heavy'
       END AS discount_group,
       CASE
           WHEN r_score = 4 AND f_score >= 3 THEN 'Champion'
           WHEN r_score >= 3 AND f_score >= 2 THEN 'Loyal'
           WHEN r_score = 2 THEN 'At Risk'
           WHEN r_score = 1 AND f_score >= 2 THEN 'About to Lapse'
           ELSE 'Lost'
       END AS rfm_segment,
       CASE WHEN days_since_last_order > 90 THEN 1 ELSE 0 END AS is_churned
FROM profile;


-- ============================================================================
-- VIEW 3: v_monthly_kpis
-- One row per calendar month: acquisition, volume, GMV, discounting, and
-- delivery-performance KPIs. Feeds the Power BI trend/KPI page.
-- ============================================================================
CREATE OR REPLACE VIEW v_monthly_kpis AS
WITH new_customers AS (
    SELECT cohort_month AS order_month, COUNT(*) AS new_customers
    FROM customers
    GROUP BY cohort_month
),
order_stats AS (
    SELECT o.order_month,
           COUNT(*) AS total_orders,
           SUM(o.net_order_value) AS total_gmv,
           AVG(o.net_order_value) AS avg_order_value,
           100.0 * COUNT(DISTINCT d.order_id) / COUNT(*) AS discount_rate_pct
    FROM orders o
    LEFT JOIN discounts d ON d.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
    GROUP BY o.order_month
),
delivery_stats AS (
    SELECT o.order_month,
           AVG(de.delivery_delay_min) AS avg_delivery_delay,
           100.0 * SUM(CASE WHEN de.delivery_delay_min < 20 THEN 1 ELSE 0 END) / COUNT(*) AS on_time_delivery_pct
    FROM orders o
    JOIN delivery_events de ON de.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
    GROUP BY o.order_month
)
SELECT os.order_month,
       COALESCE(nc.new_customers, 0) AS new_customers,
       os.total_orders,
       ROUND(os.total_gmv, 2) AS total_gmv,
       ROUND(os.avg_order_value, 2) AS avg_order_value,
       ROUND(os.discount_rate_pct, 2) AS discount_rate_pct,
       ROUND(ds.avg_delivery_delay, 2) AS avg_delivery_delay,
       ROUND(ds.on_time_delivery_pct, 2) AS on_time_delivery_pct
FROM order_stats os
LEFT JOIN new_customers nc ON nc.order_month = os.order_month
LEFT JOIN delivery_stats ds ON ds.order_month = os.order_month
ORDER BY os.order_month;
