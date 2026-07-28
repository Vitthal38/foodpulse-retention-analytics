"""Shared fixtures/helpers for the FoodPulse test suite."""

import importlib.util
import os
import re

import pytest
import psycopg2
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(ROOT_DIR, "analysis", "sql")

load_dotenv(os.path.join(ROOT_DIR, ".env"))

# Tests that hit the live PostgreSQL database only run when explicitly
# requested (set FOODPULSE_RUN_DB_TESTS=1) -- keeps CI fast/deterministic
# without a Postgres service container, per the "don't over-engineer this"
# instruction for the CI workflow.
requires_db = pytest.mark.skipif(
    os.getenv("FOODPULSE_RUN_DB_TESTS") != "1",
    reason="set FOODPULSE_RUN_DB_TESTS=1 (with a configured .env) to run tests against a live database",
)


def get_test_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "foodpulse"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
    )


# The NTILE non-determinism this project hit in production came from parallel
# workers racing to feed a HashAggregate (confirmed via EXPLAIN during the
# original investigation). On a small/default-configured database, Postgres's
# planner often picks a single-threaded plan that happens to be incidentally
# stable across repeated runs even WITHOUT a tie-breaker -- which would make a
# naive "run twice, compare" test pass even against genuinely non-deterministic
# SQL. These settings force a parallel Gather plan so the determinism tests
# actually exercise the condition that exposes the bug, in any environment.
_FORCE_PARALLEL_STATEMENTS = [
    "SET max_parallel_workers_per_gather = 4",
    "SET parallel_setup_cost = 0",
    "SET parallel_tuple_cost = 0",
    "SET min_parallel_table_scan_size = 0",
    "SET min_parallel_index_scan_size = 0",
]


def get_test_connection_forcing_parallel_plan():
    conn = get_test_connection()
    with conn.cursor() as cur:
        for stmt in _FORCE_PARALLEL_STATEMENTS:
            cur.execute(stmt)
    return conn


# Matches the QUERY N header-block format in analysis/sql/queries.sql --
# duplicated (not imported) from analysis/run_queries.py's HEADER_PATTERN
# to keep the test suite independent of that script's internals.
_HEADER_PATTERN = re.compile(
    r"-- ={20,}\n-- QUERY (\d+).*?\n(?:-- .*\n)*-- ={20,}\n",
    re.MULTILINE,
)


def load_query(query_number: int) -> str:
    """Return the SQL body of QUERY N from analysis/sql/queries.sql."""
    with open(os.path.join(SQL_DIR, "queries.sql"), encoding="utf-8") as f:
        sql_text = f.read()
    matches = list(_HEADER_PATTERN.finditer(sql_text))
    for i, match in enumerate(matches):
        if int(match.group(1)) == query_number:
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(sql_text)
            return sql_text[start:end].strip()
    raise ValueError(f"QUERY {query_number} not found in queries.sql")


def read_sql_file(filename: str) -> str:
    with open(os.path.join(SQL_DIR, filename), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="session")
def build_dashboard_module():
    """Load dashboard/build_dashboard.py by path (it isn't a package) without
    executing its __main__ block, so its pure helper functions (e.g.
    compute_retained_90d) can be unit tested directly."""
    path = os.path.join(ROOT_DIR, "dashboard", "build_dashboard.py")
    spec = importlib.util.spec_from_file_location("build_dashboard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
