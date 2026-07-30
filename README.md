# FoodPulse — Customer Retention & Revenue Risk Analytics

![CI](https://github.com/Vitthal38/foodpulse-retention-analytics/actions/workflows/ci.yml/badge.svg) ![License](https://img.shields.io/github/license/Vitthal38/foodpulse-retention-analytics) ![Python](https://img.shields.io/badge/python-3.12-blue)

A focused retention case study for a fictional Indian food delivery platform — built to answer: why do customers stop ordering, what revenue is at risk, and which lever should the business pull first?

**TL;DR:** 65.3% of customers never place a second order (35.44% 90-day retention overall); the top ~9.9% of customers drive 50% of GMV (and ~22.9% drive 80%); delivery delay is a real but gradual — not catastrophic — churn driver.

**Contents:** [Dashboard](#dashboard) · [Key Findings](#key-findings) · [Tech Stack](#tech-stack) · [How to Reproduce](#how-to-reproduce) · [Key Business Recommendations](#key-business-recommendations) · [Limitations & Assumptions](#limitations--assumptions)

## Dashboard

### Executive Summary
![Executive Summary](dashboard/screenshots/page1_executive_summary.png)

### Retention & Churn Analysis
![Retention & Churn](dashboard/screenshots/page2_retention_churn.png)

### Segment Intelligence
![Segment Intelligence](dashboard/screenshots/page3_segment_intelligence.png)

## Business Questions

- Why do customers stop ordering after their first (or an early) order?
- How much of the platform's revenue is concentrated in, and therefore at risk from, a small share of customers?
- Which operational lever — delivery reliability, discount strategy, or customer targeting — should the business prioritize first to protect retention and revenue?

## Key Findings

- **65.3% of customers never place a second order, and overall 90-day retention (right-censored — excluding customers whose 90-day window hasn't fully elapsed yet) sits at 35.44% (64.6% churn).** One-time buyers are the dominant lifecycle pattern on the platform, not the exception.
- **Delivery delay is a real, statistically significant retention driver — but a gradual decline, not a cliff.** Retention falls steadily from 39.9% in the 0–10 minute bucket to roughly 20.5% in the 50+ minute bucket — meaningful, but far from the near-total collapse an earlier draft of this analysis assumed.
- **Revenue is heavily concentrated.** The top **~9.9%** of customers by spend drive **50%** of GMV, and the top **~22.9%** drive **80%** — a small customer base carries most of the business.
- **Discount dependency correlates with lower value, not higher.** Heavy discount users show lower total spend and weaker retention than customers who use discounts lightly or not at all — discounting is not a reliable path to loyalty on its own.

## Tech Stack

- **Python 3.12** — synthetic data generation, preprocessing, and analysis.
- **pandas, numpy, Faker** — data creation and transformation.
- **PostgreSQL 18** — relational storage and SQL analysis.
- **SQL** — cohort retention, RFM segmentation, discount analysis, and Pareto analysis.
- **seaborn, matplotlib** — statistical visualizations and charts.
- **Power BI Desktop** — executive dashboard and storytelling.
- **pytest, ruff, GitHub Actions** — regression tests and CI.
- **HTML/CSS/vanilla JavaScript, PapaParse** — the live GitHub Pages site, including a client-side interactive recomputation panel.

**Note:** GitHub's language detector under-counts SQL/DAX due to file size — SQL and Power BI are core to this project. See `analysis/sql/` and the dashboard screenshots above.

## Project Structure

```
foodpulseretention-analytics/
├── generate_data.py          # synthetic data generator (customers, orders, items, delivery, discounts)
├── pipeline/
│   └── load_postgres.py      # creates the database/schema and loads the CSVs with FK verification
├── analysis/
│   ├── sql/
│   │   ├── queries.sql       # the 5 core analyses (see below)
│   │   └── views.sql         # 3 Power BI-facing views
│   ├── run_queries.py        # executes queries.sql and saves results to analysis/results/
│   ├── results/               # query outputs — gitignored, regenerated on run
│   ├── visualisations.py     # builds the 4 charts below from analysis/results/
│   ├── export_customer_facts.py  # regenerates the per-customer CSV the Power BI dashboard reads
│   └── charts/                # chart PNGs — tracked in git
├── data/
│   └── raw/                  # synthetic CSVs — gitignored, regenerated on run
├── docs/
│   └── data_dictionary.md    # every table/column, business meaning, synthetic-data caveats
├── tests/                    # pytest regression tests (see .github/workflows/ci.yml)
├── .env.example               # PostgreSQL connection template
├── requirements.txt
├── requirements-dev.txt
├── LICENSE
├── .gitignore
└── README.md
```

## How to Reproduce

```
Step 1: pip install -r requirements.txt
Step 2: python generate_data.py
Step 3: python pipeline/load_postgres.py
Step 4: python analysis/run_queries.py
Step 5: python analysis/visualisations.py
Step 6: python analysis/export_customer_facts.py   # regenerates customer_facts_v2.csv
Step 7: Open the Power BI dashboard and refresh its data source
```

Copy `.env.example` to `.env` and fill in your local PostgreSQL credentials before running Step 3.

See [docs/data_dictionary.md](docs/data_dictionary.md) for every table/column and its business meaning.

## Analysis Overview

**Cohort retention analysis.** Customers are grouped into monthly acquisition cohorts and tracked at 0, 1, 2, 3, 6, 9, and 12 months after their first order. This is the clearest lens on the platform's core problem: the steep drop after month 0 is driven by the 65.3% of customers who never return, making early-lifecycle retention — not later-stage loyalty — the primary lever available to the business.

**Delivery delay vs churn threshold.** Customers are bucketed by their first order's delivery delay (0–10, 10–20, 20–35, 35–50, and 50+ minutes), then measured on whether they placed a 2nd delivered order within 90 days — customers whose 90-day window hasn't fully elapsed yet are excluded rather than counted as churned. Retention declines in a clear, monotonic step down as delay increases — from 39.9% in the best bucket to roughly 20.5% in the worst — a gradual decline, not a cliff. This turns delivery performance from an operations metric into a quantified retention risk.

**RFM segmentation.** Every customer is scored on Recency, Frequency, and Monetary value (NTILE 4 quartile ranks are computed and retained as reference columns), then assigned to one of five segments — Champion, Loyal, At Risk, About to Lapse, and Lost — using fixed thresholds rather than the quartile ranks directly (e.g. Champion = a delivered order within the last 30 days and at least 5 lifetime orders). This segmentation is the mechanism for turning the cohort and delay findings into an actionable, customer-level target list rather than an aggregate statistic.

**Discount dependency vs LTV.** Customers are classified by the share of their orders that carried a discount — Never, Light (1–30%), Moderate (31–60%), and Heavy (60%+) — and compared on total orders, net spend, and retention. Heavy discount users show lower spend and weaker retention than light or non-discount users, indicating that discount-driven acquisition is attracting price-sensitive, low-loyalty customers rather than building repeat demand.

**Revenue concentration (Pareto).** Customers are ranked by total net spend and their cumulative share of GMV is tracked down the ranked list. The result is a textbook power-law curve: roughly 9.9% of customers account for half of all revenue, and 22.9% account for 80%. This reframes retention from a broad, undifferentiated problem into a narrower question of protecting a specific, identifiable group of high-value customers.

## Charts

![Cohort Retention Heatmap](analysis/charts/cohort_retention_heatmap.png)
*Notice how the color intensity barely changes moving right from month 1 onward — nearly all of the drop happens in the first month, not gradually across the year.*

![Delivery Delay vs Churn](analysis/charts/delivery_delay_churn.png)
*The decline is a steady staircase across all 5 buckets rather than a cliff at any single threshold — there's no "safe" delay level below which retention suddenly jumps.*

![Revenue Lorenz Curve](analysis/charts/revenue_lorenz_curve.png)
*The curve's steepest bend happens within just the first ~10% of customers — past the 80% milestone, each additional customer adds comparatively little incremental revenue.*

![RFM Segments](analysis/charts/rfm_segments.png)
*Champions are a small slice of the customer base but a disproportionate majority of GMV — Lost is the mirror image, large in headcount but comparatively small in revenue contribution.*

## Key Business Recommendations

**1. Treat delivery delay as a churn-prevention lever, not just an ops metric.** Customers experiencing delivery delays that push them into the 50+ minute bucket retain at roughly 20.5%, versus 39.9% in the 0–10 minute bucket — a real, gradual decline, not a cliff — so the operational target is keeping median delivery delay inside that lowest band, and treating any customer drifting past it as an early-warning candidate for proactive service recovery (credits, priority dispatch) before they lapse.

**2. Build a key-account motion around the top ~9.9% of customers.** This cohort — 4,832 of 48,722 ordering customers — drives ₹120.7M of the platform's ₹241.5M annual GMV (50%), at an average spend of ₹24,986 per customer versus ₹4,956 across the ordering base as a whole (~5x). Losing even 5% of this cohort (~242 customers) to churn would put roughly **₹6.0M of annual GMV at risk** — equivalent to the combined GMV of the bottom 20,937 customers (43% of the ordering base). This segment should be tracked and protected with dedicated retention treatment (priority support, loyalty perks) rather than folded into generic, platform-wide campaigns.

**3. Stop using deep discounts as the default retention tool, and redirect that spend toward the first-order experience.** Heavy discount users (3,268 customers whose orders are 60%+ discounted) show an average LTV of ₹10,101 versus ₹13,952 for light/moderate discount users — a ₹3,851 per-customer gap that totals **~₹12.6M in foregone lifetime value** across the heavy-discount cohort alone. Combined with 65.3% of customers never returning at all, blanket discounting is not converting one-time buyers into repeat customers — instead, use the RFM segments to target "About to Lapse" and "At Risk" customers specifically, while reinvesting discount budget into delivery reliability and onboarding quality for first-time buyers.

## Limitations & Assumptions

- **This is entirely synthetic data.** `generate_data.py` uses [Faker](https://faker.readthedocs.io/) to generate customer cities and identifiers (seed=42) — these are not real Indian cities, customers, restaurants, or orders. Any resemblance of a city name or business pattern to a real place or company is coincidental.
- **The underlying behavioral mechanics are hand-tuned, not fit to real data.** Retention propensity (`retention_score`), spend concentration (`spend_multiplier`), delivery-delay exposure (`delay_affinity`), and discount-seeking behavior (`discount_affinity`) are latent traits assigned via chosen distributions and coefficients (see `generate_customers()` in `generate_data.py`), not estimated from an actual food-delivery dataset. The resulting patterns (65.3% one-time-buyer rate, revenue concentration, delay-vs-retention gradient) are the generator's designed behavior, not an empirical discovery — the analysis pipeline and dashboard reconciliation work are real and independently verified, but the input data's realism is a modeling choice, not a fact about any real business.
- **Power BI vs. Python retention figures agree to within 0.03 percentage points, not exactly.** The live Power BI dashboard reports 35.44% 90-day retention; the Python reference implementation (`dashboard/build_dashboard.py`) computes 35.41%. Both use the same right-censoring and boundary-condition rules; the residual gap was root-caused as far as practical value allowed and accepted as within tolerance rather than chased further (see Repository Notes below).
- **Known non-determinism (not yet fixed):** a small (~1–3 customer) run-to-run variance exists in `queries.sql` Query 2's delay-bucket assignment, from the same class of missing-tie-breaker issue fixed elsewhere (`ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date)` has no tie-breaker for same-day orders). Left as a known, low-impact issue rather than fixed, to keep this hardening pass scoped to its stated phases.

## Repository Notes

Raw data CSVs are gitignored — fully regeneratable by running `generate_data.py` (seed=42, runtime ~35 seconds). Query results under `analysis/results/` are likewise gitignored and regenerated by `analysis/run_queries.py`.

The Power BI dashboard's per-customer staging table (`customer_facts_v2.csv`, read by its DAX measures for `FirstOrderDate`/`Retained90d`) is generated by `analysis/export_customer_facts.py` directly from the PostgreSQL database — it is not a hand-maintained or externally-sourced file. Its `Retained90d` column uses the same right-censoring boundary (`order_date > FirstOrderDate AND order_date <= FirstOrderDate + 90`) as `dashboard/build_dashboard.py`, verified to match exactly (15,907 retained / 32,815 not, out of 48,722 customers).

The Power BI dashboard and the Python verification scripts (`dashboard/build_dashboard.py`) agree to within 0.03 percentage points on 90-day retention (35.44% vs 35.41%); the Python script is documented as the reference implementation for audit purposes.

## Author

Vitthal Misal — Data Analyst (Python, SQL, Power BI)
[LinkedIn](https://www.linkedin.com/in/vitthal-misal-analyst) · [GitHub](https://github.com/Vitthal38)
Open to Data Analyst roles.
