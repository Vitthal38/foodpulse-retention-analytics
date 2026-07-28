"""
FoodPulse — Power BI customer-facts export
Regenerates customer_facts_v2.csv (the per-customer staging table the Power
BI dashboard's DAX measures read FirstOrderDate/Retained90d from) directly
from the `foodpulse` PostgreSQL database, closing the reproducibility gap
where this file previously existed only outside the repo.

Retained90d uses the same right-censoring boundary as
dashboard/build_dashboard.py and Query 2: any delivered order strictly
after the customer's first delivered order and within 90 days of it
(order_date > FirstOrderDate AND order_date <= FirstOrderDate + 90).

Run (after analysis/run_queries.py has populated the database):
    python analysis/export_customer_facts.py
"""

import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "analysis", "results")

load_dotenv(os.path.join(ROOT_DIR, ".env"))

PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("PGDATABASE", "foodpulse")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")

EXPORT_SQL = """
WITH delivered AS (
    SELECT o.customer_id, o.order_id, o.order_date, o.net_order_value, de.delivery_delay_min
    FROM orders o
    JOIN delivery_events de ON de.order_id = o.order_id
    WHERE o.order_status = 'Delivered'
),
-- order_id appended as a deterministic tie-breaker for same-day first orders
-- (same tie-breaker class as the NTILE fixes in views.sql/queries.sql).
seq AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS rn
    FROM delivered
),
first_order AS (
    SELECT customer_id,
           order_id AS first_order_id,
           order_date AS first_order_date,
           delivery_delay_min AS first_order_delay
    FROM seq
    WHERE rn = 1
),
agg AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(net_order_value) AS total_ltv,
           MAX(order_date) AS last_order_date
    FROM delivered
    GROUP BY customer_id
),
-- right-censoring boundary: order_date > first_order_date (strict) AND
-- <= first_order_date + 90, matching the Power BI DAX measure exactly.
qualifying AS (
    SELECT d.customer_id,
           BOOL_OR(d.order_date > fo.first_order_date AND d.order_date <= fo.first_order_date + 90) AS retained_90d
    FROM delivered d
    JOIN first_order fo ON fo.customer_id = d.customer_id
    GROUP BY d.customer_id
)
SELECT fo.customer_id AS "customer_id",
       fo.first_order_date AS "FirstOrderDate",
       agg.last_order_date AS "LastOrderDate",
       agg.order_count AS "OrderCount",
       agg.total_ltv AS "TotalLTV",
       q.retained_90d AS "Retained90d",
       fo.first_order_id AS "FirstOrderID",
       fo.first_order_delay AS "FirstOrderDelay",
       CASE
           WHEN fo.first_order_delay < 10 THEN '0-10 min'
           WHEN fo.first_order_delay < 20 THEN '10-20 min'
           WHEN fo.first_order_delay < 35 THEN '20-35 min'
           WHEN fo.first_order_delay < 50 THEN '35-50 min'
           ELSE '50+ min'
       END AS "DelayBucket"
FROM first_order fo
JOIN agg ON agg.customer_id = fo.customer_id
JOIN qualifying q ON q.customer_id = fo.customer_id
ORDER BY fo.customer_id;
"""


def get_connection():
    return psycopg2.connect(host=PGHOST, port=PGPORT, dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD)


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    conn = get_connection()
    try:
        df = pd.read_sql_query(EXPORT_SQL, conn)
    finally:
        conn.close()

    out_path = os.path.join(RESULTS_DIR, "customer_facts_v2.csv")
    df.to_csv(out_path, index=False)
    print(f"customer_facts_v2.csv regenerated: {len(df):,} rows -> {out_path}")
    print(f"  Retained90d True : {int(df['Retained90d'].sum()):,}")
    print(f"  Retained90d False: {int((~df['Retained90d']).sum()):,}")


if __name__ == "__main__":
    main()
