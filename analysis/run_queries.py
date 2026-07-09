"""
FoodPulse — SQL Analysis Runner
Creates the Power BI-facing views, then executes the 5 core analyses defined
in analysis/sql/queries.sql against the `foodpulse` PostgreSQL database,
printing a preview of each and saving full results to analysis/results/*.csv.

Run:
    python analysis/run_queries.py
"""

import os
import re
import warnings

import pandas as pd
import psycopg2
from dotenv import load_dotenv

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(ROOT_DIR, "analysis", "sql")
RESULTS_DIR = os.path.join(ROOT_DIR, "analysis", "results")

load_dotenv(os.path.join(ROOT_DIR, ".env"))

PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("PGDATABASE", "foodpulse")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")

# query number (1-indexed, matching the QUERY N headers in queries.sql) -> output CSV
QUERY_OUTPUT_FILES = {
    1: "cohort_retention.csv",
    2: "delay_churn.csv",
    3: "rfm_segments.csv",
    4: "discount_ltv.csv",
    5: "revenue_pareto.csv",
}

HEADER_PATTERN = re.compile(
    r"-- ={20,}\n-- QUERY (\d+).*?\n(?:-- .*\n)*-- ={20,}\n",
    re.MULTILINE,
)


def get_connection():
    return psycopg2.connect(host=PGHOST, port=PGPORT, dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD)


def parse_queries(sql_text: str) -> dict:
    """Split queries.sql into {query_number: sql_body} using the QUERY N header blocks."""
    matches = list(HEADER_PATTERN.finditer(sql_text))
    queries = {}
    for i, match in enumerate(matches):
        query_num = int(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sql_text)
        queries[query_num] = sql_text[start:end].strip()
    return queries


def run_views(conn):
    views_sql = open(os.path.join(SQL_DIR, "views.sql"), encoding="utf-8").read()
    with conn.cursor() as cur:
        cur.execute(views_sql)
    conn.commit()
    print("Created/refreshed views: v_cohort_retention, v_customer_segments, v_monthly_kpis")

    for view in ["v_cohort_retention", "v_customer_segments", "v_monthly_kpis"]:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {view};")
            count = cur.fetchone()[0]
        print(f"  {view:<22} rows={count:,}")


def run_query(conn, name: str, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    conn = get_connection()

    try:
        print("=" * 70)
        print("Creating Power BI views")
        print("=" * 70)
        run_views(conn)

        print("\n" + "=" * 70)
        print("Running core SQL analyses")
        print("=" * 70)

        sql_text = open(os.path.join(SQL_DIR, "queries.sql"), encoding="utf-8").read()
        queries = parse_queries(sql_text)
        assert len(queries) == 5, f"expected 5 queries, parsed {len(queries)}"

        for query_num in sorted(queries):
            csv_name = QUERY_OUTPUT_FILES[query_num]
            print(f"\n-- QUERY {query_num} -> {csv_name} --")
            df = run_query(conn, csv_name, queries[query_num])
            print(f"  rows: {len(df):,}")
            print(df.head(5).to_string())

            out_path = os.path.join(RESULTS_DIR, csv_name)
            df.to_csv(out_path, index=False)
            print(f"  saved -> {out_path}")

        print("\n" + "=" * 70)
        print("All queries executed and results saved to analysis/results/")
        print("=" * 70)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
