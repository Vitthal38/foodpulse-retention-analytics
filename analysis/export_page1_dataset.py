"""
FoodPulse -- Page 1 (Executive Summary) client-side dataset export
Exports one row per customer (all 50,000, including never-ordered
customers) with the dimensions and pre-computed flags needed for the
GitHub Pages interactive dashboard (index.html) to recompute 90-Day
Retention %, Total GMV, and Ordering Customers in-browser under a
City / Acquisition Channel filter -- without re-deriving any business
logic. This deliberately reuses the exact CTE pattern already validated
in analysis/export_customer_facts.py (delivered / seq / first_order /
agg / qualifying), just widened to a LEFT JOIN from `customers` (so
never-ordered customers are included) and with city/acquisition_channel
added.

Run (after analysis/run_queries.py has populated the database):
    python analysis/export_page1_dataset.py
"""

import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT_DIR, "data", "processed")

load_dotenv(os.path.join(ROOT_DIR, ".env"))

PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("PGDATABASE", "foodpulse")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")

EXPORT_SQL = """
WITH delivered AS (
    SELECT o.customer_id, o.order_id, o.order_date, o.net_order_value
    FROM orders o
    WHERE o.order_status = 'Delivered'
),
seq AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS rn
    FROM delivered
),
first_order AS (
    SELECT customer_id, order_date AS first_order_date
    FROM seq
    WHERE rn = 1
),
agg AS (
    SELECT customer_id, COUNT(*) AS order_count, SUM(net_order_value) AS net_gmv
    FROM delivered
    GROUP BY customer_id
),
-- same right-censoring boundary as export_customer_facts.py / build_dashboard.py's
-- compute_retained_90d(): retained_90d_raw = ANY delivered order strictly after the
-- first order and within 90 days of it.
qualifying AS (
    SELECT d.customer_id,
           BOOL_OR(d.order_date > fo.first_order_date AND d.order_date <= fo.first_order_date + 90) AS retained_90d_raw
    FROM delivered d
    JOIN first_order fo ON fo.customer_id = d.customer_id
    GROUP BY d.customer_id
)
SELECT c.customer_id AS "customer_id",
       c.city AS "city",
       c.acquisition_channel AS "acquisition_channel",
       COALESCE(agg.order_count, 0) AS "order_count",
       ROUND(COALESCE(agg.net_gmv, 0), 2) AS "net_gmv",
       fo.first_order_date AS "first_order_date",
       COALESCE(q.retained_90d_raw, false) AS "retained_90d_raw"
FROM customers c
LEFT JOIN first_order fo ON fo.customer_id = c.customer_id
LEFT JOIN agg ON agg.customer_id = c.customer_id
LEFT JOIN qualifying q ON q.customer_id = c.customer_id
ORDER BY c.customer_id;
"""


def get_connection():
    return psycopg2.connect(host=PGHOST, port=PGPORT, dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = get_connection()
    try:
        df = pd.read_sql_query(EXPORT_SQL, conn)
    finally:
        conn.close()

    # Exported as 0/1 rather than pandas' default "True"/"False" bool-to-string
    # serialization: PapaParse's dynamicTyping (used by index.html) reliably
    # converts numeric strings but does NOT recognize capitalized "True"/"False"
    # as booleans, which silently left every row uncounted as retained.
    df["retained_90d_raw"] = df["retained_90d_raw"].astype(int)

    out_path = os.path.join(OUT_DIR, "customer_facts_dashboard.csv")
    df.to_csv(out_path, index=False)
    print(f"customer_facts_dashboard.csv written: {len(df):,} rows -> {out_path}")
    print(f"  ordering customers (order_count > 0): {(df['order_count'] > 0).sum():,}")
    print(f"  total GMV (Delivered-only): {df['net_gmv'].sum():,.2f}")


if __name__ == "__main__":
    main()
