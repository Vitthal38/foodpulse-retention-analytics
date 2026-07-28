"""
Regression tests for dashboard/build_dashboard.py's compute_retained_90d(),
covering the two boundary bugs found and fixed in this project's history:
  1. the retained-order window boundary (commit 9834e5c): a naive
     "gap to the chronological 2nd order <= 90" check overcounted retained
     customers by 48 relative to the Power BI DAX measure's strict
     "order_date > FirstOrder AND order_date <= FirstOrder + 90" rule.
  2. right-censoring (commit 7f28ac9): customers whose 90-day outcome isn't
     knowable yet must be excluded, not counted as churned -- but a customer
     with a KNOWN positive outcome (an actual qualifying repeat order) must
     never be excluded, no matter how little time has elapsed.
"""

import pandas as pd


def _orders_df(rows):
    return (
        pd.DataFrame(rows, columns=["customer_id", "order_date"])
        .sort_values(["customer_id", "order_date"])
        .reset_index(drop=True)
    )


def test_retained_90d_boundary_condition(build_dashboard_module):
    compute_retained_90d = build_dashboard_module.compute_retained_90d
    day0 = pd.Timestamp("2024-01-01")

    rows = [
        # A: 2nd order on the SAME DAY as the 1st -- must NOT qualify (strict ">")
        ("A", day0), ("A", day0),
        # B: 2nd order 1 day later -- must qualify
        ("B", day0), ("B", day0 + pd.Timedelta(days=1)),
        # C: 2nd order exactly 90 days later -- must qualify (inclusive upper bound)
        ("C", day0), ("C", day0 + pd.Timedelta(days=90)),
        # D: 2nd order 91 days later -- must NOT qualify (outside the window)
        ("D", day0), ("D", day0 + pd.Timedelta(days=91)),
    ]
    df = _orders_df(rows)
    snapshot = day0 + pd.Timedelta(days=200)  # far enough out that all 4 are eligible

    retained_90d_raw, eligible_90d, retained_90d = compute_retained_90d(df, snapshot)

    assert not retained_90d_raw["A"], "same-day repeat order must not count as retained"
    assert retained_90d_raw["B"]
    assert retained_90d_raw["C"], "exactly 90 days later must count (inclusive upper bound)"
    assert not retained_90d_raw["D"], "91 days later must not count (outside the 90-day window)"


def test_right_censoring_excludes_only_unresolved_negatives(build_dashboard_module):
    compute_retained_90d = build_dashboard_module.compute_retained_90d
    day0 = pd.Timestamp("2024-01-01")

    rows = [
        # POS: known positive outcome (a qualifying repeat order 5 days later)
        ("POS", day0), ("POS", day0 + pd.Timedelta(days=5)),
        # NEG_RECENT: only 1 order ever, and the snapshot is only 10 days after
        # it -- the 90-day window has NOT elapsed, so this outcome is unknown.
        ("NEG_RECENT", day0),
    ]
    df = _orders_df(rows)
    snapshot = day0 + pd.Timedelta(days=10)

    retained_90d_raw, eligible_90d, retained_90d = compute_retained_90d(df, snapshot)

    assert eligible_90d["POS"], "a known positive outcome must never be censored, regardless of elapsed time"
    assert "POS" in retained_90d.index
    assert retained_90d["POS"]

    assert not eligible_90d["NEG_RECENT"], "an unresolved non-repeat customer within the window must be censored"
    assert "NEG_RECENT" not in retained_90d.index
