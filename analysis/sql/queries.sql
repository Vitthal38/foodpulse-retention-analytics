-- ============================================================================
-- FoodPulse — Core SQL Analyses
-- Run against the `foodpulse` PostgreSQL database created by
-- pipeline/load_postgres.py. Executed automatically by analysis/run_queries.py
-- (results saved to analysis/results/*.csv).
-- ============================================================================


-- ============================================================================
-- QUERY 1 — Cohort retention matrix
-- Business question: Of the customers acquired in a given month (cohort_month),
-- what share are still ordering 0, 1, 2, 3, 6, 9, and 12 months after their
-- first order? Reveals how quickly each acquisition cohort decays.
-- Output: cohort_month, months_since_first, customer_count, retention_pct
-- ============================================================================
WITH first_order AS (
    SELECT customer_id, MIN(order_date) AS first_order_date
    FROM orders
    WHERE order_status = 'Delivered'
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
    WHERE o.order_status = 'Delivered'
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
)
SELECT r.cohort_month,
       r.months_since_first,
       r.customer_count,
       ROUND(100.0 * r.customer_count / cs.cohort_size, 2) AS retention_pct
FROM retention r
JOIN cohort_sizes cs ON cs.cohort_month = r.cohort_month
ORDER BY r.cohort_month, r.months_since_first;


-- ============================================================================
-- QUERY 2 — Delivery delay vs 90-day churn
-- Methodology: delivered orders only, bucketed by each customer's FIRST
-- delivered order's delay, retained = 2nd delivered order within 90 days of
-- the first. Matches the dashboard analysis on Page 2 (verified end-to-end
-- against independently-recomputed Python numbers).
-- Output: delay_bucket, customer_count, retained_count, retention_pct
-- ============================================================================
-- Query 2: 90-day retention by
-- first-order delivery delay
-- Methodology: delivered orders only,
-- bucketed by first order delay,
-- retained = 2nd delivered order
-- within 90 days of first order.
-- This matches the dashboard analysis
-- on Page 2.
WITH delivered_orders AS (
    SELECT o.customer_id, o.order_id, o.order_date, de.delivery_delay_min
    FROM orders o
    JOIN delivery_events de ON de.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
),
snapshot AS (
    SELECT MAX(order_date) AS snapshot_date FROM delivered_orders
),
order_seq AS (
    SELECT customer_id, order_date, delivery_delay_min,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date) AS rn
    FROM delivered_orders
),
first_order AS (
    SELECT customer_id, order_date AS first_order_date, delivery_delay_min AS first_order_delay
    FROM order_seq
    WHERE rn = 1
),
second_order AS (
    SELECT customer_id, order_date AS second_order_date
    FROM order_seq
    WHERE rn = 2
),
-- right-censoring fix: only keep customers whose 90-day outcome is actually
-- knowable -- they've already placed a 2nd order, or 90+ days have elapsed
-- since their 1st order so a non-reorder can be safely called "churned".
-- Customers acquired too recently to have had a full 90-day window yet are
-- excluded rather than counted as churned.
customer_retention AS (
    SELECT fo.customer_id, fo.first_order_delay,
           CASE
               WHEN so.second_order_date IS NOT NULL
                AND (so.second_order_date - fo.first_order_date) <= 90
               THEN 1 ELSE 0
           END AS retained_90d
    FROM first_order fo
    LEFT JOIN second_order so ON so.customer_id = fo.customer_id
    CROSS JOIN snapshot sn
    WHERE so.second_order_date IS NOT NULL
       OR (sn.snapshot_date - fo.first_order_date) >= 90
),
delay_bucket AS (
    SELECT customer_id, retained_90d,
           CASE
               WHEN first_order_delay < 10 THEN '0-10 min'
               WHEN first_order_delay < 20 THEN '10-20 min'
               WHEN first_order_delay < 35 THEN '20-35 min'
               WHEN first_order_delay < 50 THEN '35-50 min'
               ELSE '50+ min'
           END AS delay_bucket,
           CASE
               WHEN first_order_delay < 10 THEN 1
               WHEN first_order_delay < 20 THEN 2
               WHEN first_order_delay < 35 THEN 3
               WHEN first_order_delay < 50 THEN 4
               ELSE 5
           END AS bucket_order
    FROM customer_retention
)
SELECT delay_bucket,
       COUNT(*) AS customer_count,
       SUM(retained_90d) AS retained_count,
       ROUND(100.0 * SUM(retained_90d) / COUNT(*), 2) AS retention_pct
FROM delay_bucket
GROUP BY delay_bucket, bucket_order
ORDER BY bucket_order;


-- ============================================================================
-- QUERY 3 — RFM segmentation
-- Business question: Which customers are our champions, and which are about
-- to lapse? Scores every customer on Recency / Frequency / Monetary quartiles
-- (NTILE 4, snapshot date = latest order date in the dataset) and assigns a
-- segment label.
-- Output: customer_id, r_score, f_score, m_score, rfm_total, segment, total_spend
-- ============================================================================
WITH snapshot AS (
    SELECT MAX(order_date) AS snapshot_date FROM orders
),
customer_rfm AS (
    SELECT o.customer_id,
           (SELECT snapshot_date FROM snapshot) - MAX(o.order_date) AS recency_days,
           COUNT(*) AS frequency,
           SUM(o.net_order_value) AS monetary
    FROM orders o
    WHERE o.order_status = 'Delivered'
    GROUP BY o.customer_id
),
scored AS (
    -- customer_id appended as a deterministic tie-breaker -- see the same
    -- fix in views.sql's v_customer_segments for why this is required.
    SELECT customer_id, recency_days, frequency, monetary,
           NTILE(4) OVER (ORDER BY recency_days DESC, customer_id) AS r_score,
           NTILE(4) OVER (ORDER BY frequency ASC, customer_id)     AS f_score,
           NTILE(4) OVER (ORDER BY monetary ASC, customer_id)      AS m_score
    FROM customer_rfm
)
SELECT customer_id,
       r_score, f_score, m_score,
       (r_score + f_score + m_score) AS rfm_total,
       -- Canonical segment rule (fixed thresholds, not NTILE quartiles) --
       -- matches build_dashboard.py's assign_segment() exactly, per the
       -- Phase 3 reconciliation. r_score/f_score/m_score above are still
       -- exposed as informational quartile scores, but no longer drive
       -- segment assignment.
       CASE
           WHEN recency_days <= 30 AND frequency >= 5 THEN 'Champion'
           WHEN recency_days <= 60 AND frequency >= 3 THEN 'Loyal'
           WHEN recency_days <= 90 THEN 'At Risk'
           WHEN recency_days <= 180 THEN 'About to Lapse'
           ELSE 'Lost'
       END AS segment,
       ROUND(monetary, 2) AS total_spend
FROM scored
ORDER BY rfm_total DESC, customer_id;


-- ============================================================================
-- QUERY 4 — Discount dependency vs LTV
-- Business question: Do customers who rely heavily on discounts turn out to
-- be less valuable (lower spend, weaker retention) than customers who rarely
-- use them? Classifies customers by the share of their orders that carried a
-- discount, then compares cohort-level outcomes.
-- Output: discount_group, customer_count, avg_total_orders, avg_net_spend,
--         avg_90day_retention_pct, avg_delivery_delay
-- ============================================================================
WITH customer_orders AS (
    SELECT o.customer_id, COUNT(*) AS total_orders, SUM(o.net_order_value) AS net_spend
    FROM orders o
    WHERE o.order_status = 'Delivered'
    GROUP BY o.customer_id
),
customer_discounts AS (
    SELECT o.customer_id, COUNT(DISTINCT d.order_id) AS discounted_orders
    FROM orders o
    LEFT JOIN discounts d ON d.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
    GROUP BY o.customer_id
),
customer_delay AS (
    SELECT o.customer_id, AVG(de.delivery_delay_min) AS avg_delay
    FROM orders o
    JOIN delivery_events de ON de.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
    GROUP BY o.customer_id
),
snapshot AS (
    SELECT MAX(order_date) AS snapshot_date FROM orders
),
order_seq AS (
    SELECT customer_id, order_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date) AS rn
    FROM orders
    WHERE order_status = 'Delivered'
),
first_two AS (
    SELECT o1.customer_id, o1.order_date AS first_order_date, o2.order_date AS second_order_date
    FROM (SELECT * FROM order_seq WHERE rn = 1) o1
    LEFT JOIN (SELECT * FROM order_seq WHERE rn = 2) o2 ON o2.customer_id = o1.customer_id
),
-- right-censoring fix: exclude customers whose 90-day reorder outcome isn't
-- knowable yet (no 2nd order, and fewer than 90 days elapsed since 1st order).
customer_profile AS (
    SELECT co.customer_id,
           co.total_orders,
           co.net_spend,
           100.0 * cd.discounted_orders / co.total_orders AS discount_pct_of_orders,
           cdel.avg_delay,
           CASE
               WHEN ft.second_order_date IS NOT NULL
                AND (ft.second_order_date - ft.first_order_date) <= 90
               THEN 1 ELSE 0
           END AS retained_90d
    FROM customer_orders co
    JOIN customer_discounts cd ON cd.customer_id = co.customer_id
    JOIN customer_delay cdel ON cdel.customer_id = co.customer_id
    JOIN first_two ft ON ft.customer_id = co.customer_id
    CROSS JOIN snapshot sn
    WHERE ft.second_order_date IS NOT NULL
       OR (sn.snapshot_date - ft.first_order_date) >= 90
),
grouped AS (
    SELECT *,
           CASE
               WHEN discount_pct_of_orders = 0 THEN 'Never'
               WHEN discount_pct_of_orders <= 30 THEN 'Light'
               WHEN discount_pct_of_orders <= 60 THEN 'Moderate'
               ELSE 'Heavy'
           END AS discount_group,
           CASE
               WHEN discount_pct_of_orders = 0 THEN 1
               WHEN discount_pct_of_orders <= 30 THEN 2
               WHEN discount_pct_of_orders <= 60 THEN 3
               ELSE 4
           END AS group_order
    FROM customer_profile
)
SELECT discount_group,
       COUNT(*) AS customer_count,
       ROUND(AVG(total_orders), 2) AS avg_total_orders,
       ROUND(AVG(net_spend), 2) AS avg_net_spend,
       ROUND(100.0 * AVG(retained_90d), 2) AS avg_90day_retention_pct,
       ROUND(AVG(avg_delay), 2) AS avg_delivery_delay
FROM grouped
GROUP BY discount_group, group_order
ORDER BY group_order;


-- ============================================================================
-- QUERY 5 — Revenue concentration (Pareto)
-- Business question: How concentrated is our revenue? Ranks every customer by
-- total net spend and tracks the cumulative share of GMV as we move down the
-- customer list, plus a summary of what % of customers drive 50/65/80% of GMV.
-- Output: row_type, milestone_label, rnk, customer_id, cumulative_customer_pct,
--         cumulative_gmv, cumulative_gmv_pct
-- ============================================================================
WITH customer_spend AS (
    SELECT customer_id, SUM(net_order_value) AS net_spend
    FROM orders
    WHERE order_status = 'Delivered'
    GROUP BY customer_id
),
ranked AS (
    SELECT customer_id, net_spend,
           ROW_NUMBER() OVER (ORDER BY net_spend DESC) AS rnk
    FROM customer_spend
),
totals AS (
    SELECT COUNT(*) AS total_customers, SUM(net_spend) AS total_gmv FROM customer_spend
),
cum AS (
    SELECT r.rnk, r.customer_id, r.net_spend,
           SUM(r.net_spend) OVER (ORDER BY r.rnk) AS cumulative_gmv,
           t.total_customers, t.total_gmv
    FROM ranked r
    CROSS JOIN totals t
),
detail AS (
    SELECT 'detail'::text AS row_type,
           NULL::text AS milestone_label,
           rnk,
           customer_id,
           ROUND(100.0 * rnk / total_customers, 3) AS cumulative_customer_pct,
           ROUND(cumulative_gmv, 2) AS cumulative_gmv,
           ROUND(100.0 * cumulative_gmv / total_gmv, 3) AS cumulative_gmv_pct
    FROM cum
),
milestones AS (
    SELECT 'milestone'::text AS row_type,
           'Top ' || MIN(ROUND(100.0 * cum.rnk / cum.total_customers, 2)) ||
               '% of customers drive ' || target.gmv_target_pct || '% of GMV' AS milestone_label,
           NULL::bigint AS rnk,
           NULL::text AS customer_id,
           MIN(ROUND(100.0 * cum.rnk / cum.total_customers, 3)) AS cumulative_customer_pct,
           NULL::numeric AS cumulative_gmv,
           target.gmv_target_pct::numeric AS cumulative_gmv_pct
    FROM (VALUES (50), (65), (80)) AS target(gmv_target_pct)
    JOIN cum ON (100.0 * cum.cumulative_gmv / cum.total_gmv) >= target.gmv_target_pct
    GROUP BY target.gmv_target_pct
)
SELECT row_type, milestone_label, rnk, customer_id,
       cumulative_customer_pct, cumulative_gmv, cumulative_gmv_pct
FROM detail
UNION ALL
SELECT row_type, milestone_label, rnk, customer_id,
       cumulative_customer_pct, cumulative_gmv, cumulative_gmv_pct
FROM milestones
ORDER BY row_type DESC, rnk;
