"""
Regression test for the business-facing Champion segment count staying
deterministic across repeated runs.

Note on scope: the original KPI drift (Champion share observed at 23.22%,
23.20%, 23.26% across repeated refreshes) was caused by NTILE() non-
determinism feeding a quartile-based segment rule. Query 3's segment CASE
WHEN was later rewritten (Phase 3 reconciliation) to use fixed thresholds
on raw recency_days/frequency instead of the NTILE-derived r_score/f_score
-- so Champion count is now structurally decoupled from NTILE and this test
does NOT reproduce the original bug (verified: it still passes even with
the NTILE tie-breaker removed). It's kept as a regression guard against a
*future* regression that recouples segment assignment to NTILE scores.
test_ntile_scores_are_deterministic in test_sql_invariants.py is the test
that actually exercises the original bug.
"""

import pandas as pd

from conftest import load_query, requires_db, get_test_connection_forcing_parallel_plan


@requires_db
def test_champion_segment_stable():
    query3_sql = load_query(3).rstrip().rstrip(";")
    champion_sql = f"SELECT COUNT(*) AS champion_count FROM ({query3_sql}) t WHERE segment = 'Champion'"

    counts = []
    for _ in range(5):
        conn = get_test_connection_forcing_parallel_plan()
        try:
            counts.append(int(pd.read_sql_query(champion_sql, conn)["champion_count"].iloc[0]))
        finally:
            conn.close()

    assert len(set(counts)) == 1, f"Champion segment count is non-deterministic across runs: {counts}"
