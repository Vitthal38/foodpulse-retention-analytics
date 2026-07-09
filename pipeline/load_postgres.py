"""
FoodPulse — PostgreSQL Load Pipeline
Loads the 6 synthetic CSVs from data/raw/ into a local PostgreSQL database,
creating the database/tables/constraints as needed and verifying the load.

Run:
    python pipeline/load_postgres.py
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data", "raw")

load_dotenv(os.path.join(ROOT_DIR, ".env"))

PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("PGDATABASE", "foodpulse")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")

# --------------------------------------------------------------------------
# Table definitions: DDL + CSV file + column order (must match CSV header)
# --------------------------------------------------------------------------
TABLES = [
    {
        "name": "customers",
        "csv": "customers.csv",
        "columns": ["customer_id", "signup_date", "acquisition_channel", "city", "cohort_month"],
        "ddl": """
            CREATE TABLE customers (
                customer_id         VARCHAR(15) PRIMARY KEY,
                signup_date         DATE NOT NULL,
                acquisition_channel VARCHAR(50) NOT NULL,
                city                VARCHAR(100) NOT NULL,
                cohort_month        VARCHAR(7) NOT NULL
            );
        """,
    },
    {
        "name": "restaurants",
        "csv": "restaurants.csv",
        "columns": ["restaurant_id", "city", "cuisine_type", "price_band", "active_flag"],
        "ddl": """
            CREATE TABLE restaurants (
                restaurant_id VARCHAR(15) PRIMARY KEY,
                city          VARCHAR(100) NOT NULL,
                cuisine_type  VARCHAR(50) NOT NULL,
                price_band    VARCHAR(20) NOT NULL,
                active_flag   SMALLINT NOT NULL
            );
        """,
    },
    {
        "name": "orders",
        "csv": "orders.csv",
        "columns": [
            "order_id", "customer_id", "restaurant_id", "order_date", "order_hour",
            "order_day_of_week", "order_month", "is_weekend", "items_count",
            "gross_order_value", "net_order_value", "payment_method", "order_status",
        ],
        "ddl": """
            CREATE TABLE orders (
                order_id           VARCHAR(15) PRIMARY KEY,
                customer_id        VARCHAR(15) NOT NULL REFERENCES customers(customer_id),
                restaurant_id      VARCHAR(15) NOT NULL REFERENCES restaurants(restaurant_id),
                order_date         DATE NOT NULL,
                order_hour         SMALLINT NOT NULL,
                order_day_of_week  VARCHAR(10) NOT NULL,
                order_month        VARCHAR(7) NOT NULL,
                is_weekend         SMALLINT NOT NULL,
                items_count        SMALLINT NOT NULL,
                gross_order_value  NUMERIC(10,2) NOT NULL,
                net_order_value    NUMERIC(10,2) NOT NULL,
                payment_method     VARCHAR(30) NOT NULL,
                order_status       VARCHAR(20) NOT NULL
            );
        """,
    },
    {
        "name": "order_items",
        "csv": "order_items.csv",
        "columns": ["order_item_id", "order_id", "item_id", "item_category", "quantity", "item_price"],
        "ddl": """
            CREATE TABLE order_items (
                order_item_id VARCHAR(15) PRIMARY KEY,
                order_id      VARCHAR(15) NOT NULL REFERENCES orders(order_id),
                item_id       VARCHAR(15) NOT NULL,
                item_category VARCHAR(50) NOT NULL,
                quantity      SMALLINT NOT NULL,
                item_price    NUMERIC(10,2) NOT NULL
            );
        """,
    },
    {
        "name": "delivery_events",
        "csv": "delivery_events.csv",
        "columns": [
            "delivery_event_id", "order_id", "pickup_time", "dispatched_time",
            "delivered_time", "delivery_delay_min", "promised_delivery_min", "delivery_status",
        ],
        "ddl": """
            CREATE TABLE delivery_events (
                delivery_event_id     VARCHAR(15) PRIMARY KEY,
                order_id              VARCHAR(15) NOT NULL UNIQUE REFERENCES orders(order_id),
                pickup_time           TIMESTAMP NOT NULL,
                dispatched_time       TIMESTAMP NOT NULL,
                delivered_time        TIMESTAMP NOT NULL,
                delivery_delay_min    NUMERIC(6,1) NOT NULL,
                promised_delivery_min SMALLINT NOT NULL,
                delivery_status       VARCHAR(20) NOT NULL
            );
        """,
    },
    {
        "name": "discounts",
        "csv": "discounts.csv",
        "columns": ["discount_id", "order_id", "discount_type", "discount_value", "discount_pct", "promo_source"],
        "ddl": """
            CREATE TABLE discounts (
                discount_id    VARCHAR(15) PRIMARY KEY,
                order_id       VARCHAR(15) NOT NULL REFERENCES orders(order_id),
                discount_type  VARCHAR(30) NOT NULL,
                discount_value NUMERIC(10,2) NOT NULL,
                discount_pct   NUMERIC(5,1) NOT NULL,
                promo_source   VARCHAR(50) NOT NULL
            );
        """,
    },
]

INDEXES = [
    "CREATE INDEX idx_orders_customer_id ON orders(customer_id);",
    "CREATE INDEX idx_orders_restaurant_id ON orders(restaurant_id);",
    "CREATE INDEX idx_orders_order_date ON orders(order_date);",
    "CREATE INDEX idx_order_items_order_id ON order_items(order_id);",
    "CREATE INDEX idx_delivery_events_order_id ON delivery_events(order_id);",
    "CREATE INDEX idx_discounts_order_id ON discounts(order_id);",
]

# FK checks to run after load: (label, orphan-count query)
FK_CHECKS = [
    ("orders.customer_id -> customers", """
        SELECT count(*) FROM orders o LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE c.customer_id IS NULL;
    """),
    ("orders.restaurant_id -> restaurants", """
        SELECT count(*) FROM orders o LEFT JOIN restaurants r ON o.restaurant_id = r.restaurant_id
        WHERE r.restaurant_id IS NULL;
    """),
    ("order_items.order_id -> orders", """
        SELECT count(*) FROM order_items oi LEFT JOIN orders o ON oi.order_id = o.order_id
        WHERE o.order_id IS NULL;
    """),
    ("delivery_events.order_id -> orders", """
        SELECT count(*) FROM delivery_events d LEFT JOIN orders o ON d.order_id = o.order_id
        WHERE o.order_id IS NULL;
    """),
    ("discounts.order_id -> orders", """
        SELECT count(*) FROM discounts d LEFT JOIN orders o ON d.order_id = o.order_id
        WHERE o.order_id IS NULL;
    """),
]


def count_csv_rows(path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # minus header


def ensure_database_exists():
    conn = psycopg2.connect(host=PGHOST, port=PGPORT, dbname="postgres", user=PGUSER, password=PGPASSWORD)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (PGDATABASE,))
            exists = cur.fetchone() is not None
            if exists:
                print(f"  database '{PGDATABASE}' already exists")
            else:
                cur.execute(f'CREATE DATABASE "{PGDATABASE}";')
                print(f"  database '{PGDATABASE}' created")
    finally:
        conn.close()


def get_connection():
    return psycopg2.connect(host=PGHOST, port=PGPORT, dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD)


def create_schema(conn):
    with conn.cursor() as cur:
        # drop in reverse dependency order so re-runs are idempotent
        for table in reversed(TABLES):
            cur.execute(f'DROP TABLE IF EXISTS {table["name"]} CASCADE;')
        for table in TABLES:
            cur.execute(table["ddl"])
            print(f"  created table {table['name']}")
        for idx_sql in INDEXES:
            cur.execute(idx_sql)
        print("  created supporting indexes")
    conn.commit()


def load_table(conn, table: dict) -> int:
    csv_path = os.path.join(DATA_DIR, table["csv"])
    col_list = ", ".join(table["columns"])
    copy_sql = f"COPY {table['name']} ({col_list}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with conn.cursor() as cur, open(csv_path, "r", encoding="utf-8") as f:
        cur.copy_expert(copy_sql, f)
    conn.commit()
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table['name']};")
        return cur.fetchone()[0]


def verify_row_counts(conn):
    print("\n-- Row count verification (CSV vs loaded table) --")
    all_ok = True
    for table in TABLES:
        csv_path = os.path.join(DATA_DIR, table["csv"])
        expected = count_csv_rows(csv_path)
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {table['name']};")
            actual = cur.fetchone()[0]
        status = "OK" if expected == actual else "MISMATCH"
        if expected != actual:
            all_ok = False
        print(f"  {table['name']:<18} csv_rows={expected:>8,}  db_rows={actual:>8,}  [{status}]")
    return all_ok


def verify_fk_integrity(conn):
    print("\n-- Foreign key integrity verification (orphaned rows) --")
    all_ok = True
    with conn.cursor() as cur:
        for label, query in FK_CHECKS:
            cur.execute(query)
            orphans = cur.fetchone()[0]
            status = "OK" if orphans == 0 else "ORPHANS FOUND"
            if orphans != 0:
                all_ok = False
            print(f"  {label:<40} orphaned_rows={orphans:>6}  [{status}]")
    return all_ok


def main():
    print("Ensuring database exists...")
    ensure_database_exists()

    print(f"\nConnecting to '{PGDATABASE}'...")
    conn = get_connection()

    try:
        print("\nCreating schema (tables + constraints + indexes)...")
        create_schema(conn)

        print("\nLoading data via COPY...")
        for table in TABLES:
            row_count = load_table(conn, table)
            print(f"  loaded {table['name']:<18} rows={row_count:>8,}")

        row_counts_ok = verify_row_counts(conn)
        fk_ok = verify_fk_integrity(conn)

        print("\n" + "=" * 60)
        if row_counts_ok and fk_ok:
            print("LOAD SUCCESSFUL — row counts match and no orphaned rows found.")
        else:
            print("LOAD COMPLETED WITH ISSUES — see warnings above.")
            sys.exit(1)
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
