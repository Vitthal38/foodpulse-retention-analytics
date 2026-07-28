"""
Regression tests for the "missing Delivered filter" and "NTILE()
non-determinism" bug classes found and fixed across this project's history
(see git log: a18c3a5, 10aa525, 259f7ac, d961a90 among others).
"""

import re

import pandas as pd
import pytest

from conftest import read_sql_file, load_query, requires_db, get_test_connection_forcing_parallel_plan

# CTEs that legitimately read FROM orders without a Delivered filter: every
# one of these is a "snapshot" CTE computing MAX(order_date) across ALL
# orders. MAX(order_date) is provably identical whether or not it's
# Delivered-filtered in this dataset (verified during the original audit),
# so it's an intentional, reviewed exception -- not an oversight.
ALLOWLISTED_CTE_NAMES = {"snapshot"}

CTE_PATTERN = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", re.IGNORECASE)
DELIVERED_FILTER_PATTERN = re.compile(r"order_status\s*=\s*'Delivered'")
FROM_ORDERS_PATTERN = re.compile(r"\bFROM\s+orders\b", re.IGNORECASE)


def extract_ctes(sql_text: str):
    """Return [(name, body), ...] for every top-level `name AS ( ... )` CTE
    block in sql_text, using paren-depth counting (not just regex) so nested
    parens inside window functions like NTILE(4) OVER (...) don't truncate
    the body early."""
    ctes = []
    for m in CTE_PATTERN.finditer(sql_text):
        name = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while depth > 0 and i < len(sql_text):
            if sql_text[i] == "(":
                depth += 1
            elif sql_text[i] == ")":
                depth -= 1
            i += 1
        ctes.append((name, sql_text[start:i - 1]))
    return ctes


@pytest.mark.parametrize("filename", ["queries.sql", "views.sql"])
def test_all_order_queries_filter_delivered_status(filename):
    """Every CTE that reads directly FROM orders must filter
    order_status = 'Delivered', unless explicitly allowlisted. This is the
    exact bug class fixed in v_monthly_kpis (GMV inflated 250.19M -> 241.5M),
    Query 5 (Pareto milestones moved 9.70%->9.92%), and three other places."""
    sql_text = read_sql_file(filename)
    ctes = extract_ctes(sql_text)

    violations = [
        name for name, body in ctes
        if name not in ALLOWLISTED_CTE_NAMES
        and FROM_ORDERS_PATTERN.search(body)
        and not DELIVERED_FILTER_PATTERN.search(body)
    ]

    assert not violations, (
        f"{filename}: CTE(s) {violations} read FROM orders without a "
        f"WHERE order_status = 'Delivered' filter and are not allowlisted"
    )


@requires_db
def test_ntile_scores_are_deterministic():
    """Regression test for the NTILE() non-determinism bug: RFM r/f/m scores
    (and therefore Champion segment membership) drifted across repeated runs
    (23.22%/23.20%/23.26% observed) because NTILE()'s ORDER BY had no
    tie-breaker on columns with large tie clusters (e.g. total_orders=1 for
    every one-time buyer). Fixed by appending `, customer_id` to every
    NTILE(...) OVER (ORDER BY ...) call in Query 3.

    Uses get_test_connection_forcing_parallel_plan(): on this project's
    dataset size, Postgres's default planner picks a single-threaded plan
    that's incidentally stable run-to-run even without the tie-breaker, so a
    plain "run twice on default settings" version of this test would not
    have caught the original bug. Forcing a parallel Gather plan (which is
    what actually raced in production) makes the test meaningful."""
    query3_sql = load_query(3)
    runs = []
    for _ in range(5):
        conn = get_test_connection_forcing_parallel_plan()
        try:
            runs.append(pd.read_sql_query(query3_sql, conn).sort_values("customer_id").reset_index(drop=True))
        finally:
            conn.close()
    for run in runs[1:]:
        pd.testing.assert_frame_equal(runs[0], run)
