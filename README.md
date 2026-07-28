# FoodPulse — Customer Retention & Revenue Risk Analytics

A focused retention case study for a fictional Indian food delivery platform — built to answer: why do customers stop ordering, what revenue is at risk, and which lever should the business pull first?

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
│   └── charts/                # chart PNGs — tracked in git
├── data/
│   └── raw/                  # synthetic CSVs — gitignored, regenerated on run
├── .env.example               # PostgreSQL connection template
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

## Analysis Overview

**Cohort retention analysis.** Customers are grouped into monthly acquisition cohorts and tracked at 0, 1, 2, 3, 6, 9, and 12 months after their first order. This is the clearest lens on the platform's core problem: the steep drop after month 0 is driven by the 65.3% of customers who never return, making early-lifecycle retention — not later-stage loyalty — the primary lever available to the business.

**Delivery delay vs churn threshold.** Customers are bucketed by their first order's delivery delay (0–10, 10–20, 20–35, 35–50, and 50+ minutes), then measured on whether they placed a 2nd delivered order within 90 days — customers whose 90-day window hasn't fully elapsed yet are excluded rather than counted as churned. Retention declines in a clear, monotonic step down as delay increases — from 39.9% in the best bucket to roughly 20.5% in the worst — a gradual decline, not a cliff. This turns delivery performance from an operations metric into a quantified retention risk.

**RFM segmentation.** Every customer is scored on Recency, Frequency, and Monetary value (NTILE 4 quartile ranks are computed and retained as reference columns), then assigned to one of five segments — Champion, Loyal, At Risk, About to Lapse, and Lost — using fixed thresholds rather than the quartile ranks directly (e.g. Champion = a delivered order within the last 30 days and at least 5 lifetime orders). This segmentation is the mechanism for turning the cohort and delay findings into an actionable, customer-level target list rather than an aggregate statistic.

**Discount dependency vs LTV.** Customers are classified by the share of their orders that carried a discount — Never, Light (1–30%), Moderate (31–60%), and Heavy (60%+) — and compared on total orders, net spend, and retention. Heavy discount users show lower spend and weaker retention than light or non-discount users, indicating that discount-driven acquisition is attracting price-sensitive, low-loyalty customers rather than building repeat demand.

**Revenue concentration (Pareto).** Customers are ranked by total net spend and their cumulative share of GMV is tracked down the ranked list. The result is a textbook power-law curve: roughly 9.9% of customers account for half of all revenue, and 22.9% account for 80%. This reframes retention from a broad, undifferentiated problem into a narrower question of protecting a specific, identifiable group of high-value customers.

## Charts

![Cohort Retention Heatmap](analysis/charts/cohort_retention_heatmap.png)

![Delivery Delay vs Churn](analysis/charts/delivery_delay_churn.png)

![Revenue Lorenz Curve](analysis/charts/revenue_lorenz_curve.png)

![RFM Segments](analysis/charts/rfm_segments.png)

## Key Business Recommendations

**1. Treat delivery delay as a churn-prevention lever, not just an ops metric.** Customers experiencing delivery delays that push them into the 50+ minute bucket retain at roughly 20.5%, versus 39.9% in the 0–10 minute bucket — a real, gradual decline, not a cliff — so the operational target is keeping median delivery delay inside that lowest band, and treating any customer drifting past it as an early-warning candidate for proactive service recovery (credits, priority dispatch) before they lapse.

**2. Build a key-account motion around the top ~10% of customers.** Since roughly 9.9% of customers already generate half of all GMV, losing even a small fraction of this group is a disproportionately large revenue event — this segment should be tracked and protected with dedicated retention treatment (priority support, loyalty perks) rather than folded into generic, platform-wide campaigns.

**3. Stop using deep discounts as the default retention tool, and redirect that spend toward the first-order experience.** With 65.3% of customers never returning and heavy discount users showing lower spend and retention than light/no-discount users, blanket discounting is not converting one-time buyers into repeat customers — instead, use the RFM segments to target "About to Lapse" and "At Risk" customers specifically, while reinvesting discount budget into delivery reliability and onboarding quality for first-time buyers.

## Repository Notes

Raw data CSVs are gitignored — fully regeneratable by running `generate_data.py` (seed=42, runtime ~35 seconds). Query results under `analysis/results/` are likewise gitignored and regenerated by `analysis/run_queries.py`.

The Power BI dashboard and the Python verification scripts (`dashboard/build_dashboard.py`) agree to within 0.03 percentage points on 90-day retention (35.44% vs 35.41%); the Python script is documented as the reference implementation for audit purposes.
