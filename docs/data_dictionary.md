# Data Dictionary

Covers every table loaded by `pipeline/load_postgres.py` from the CSVs produced by `generate_data.py`. All data is synthetic (see [README.md § Limitations & Assumptions](../README.md#limitations--assumptions)) — column definitions below describe what each field *represents in the simulation*, not a real-world data source.

## `customers`

One row per customer.

| Column | Type | Business meaning | Caveats |
|---|---|---|---|
| `customer_id` | `VARCHAR(15)` PK | Unique customer identifier (`C100000`, `C100001`, ...) | Sequential, not a real customer ID scheme |
| `signup_date` | `DATE` | Date the customer created an account | Drawn uniformly at random across the 24-month window (2023-07-01 to 2025-06-30), independent of how loyal the customer later turns out to be — this independence was a deliberate fix for an earlier cohort-assignment bias where loyal customers structurally landed in early cohorts |
| `acquisition_channel` | `VARCHAR(50)` | How the customer was acquired: Referral, Organic, App Store, Social Media, Paid Search | Each channel carries a hand-tuned retention-effect coefficient (`CHANNEL_RETENTION_EFFECT` in `generate_data.py`) that biases the customer's underlying retention propensity — this is a modeling assumption, not an empirical finding |
| `city` | `VARCHAR(100)` | Customer's city | Faker-generated city names — not real Indian cities |
| `cohort_month` | `VARCHAR(7)` | `YYYY-MM` of `signup_date` | Used as the acquisition-cohort key in cohort retention analysis |

## `restaurants`

One row per restaurant.

| Column | Type | Business meaning | Caveats |
|---|---|---|---|
| `restaurant_id` | `VARCHAR(15)` PK | Unique restaurant identifier | |
| `city` | `VARCHAR(100)` | Restaurant's city | Faker-generated, independent of any customer's city (orders are not city-matched) |
| `cuisine_type` | `VARCHAR(50)` | One of 10 fixed cuisine categories | |
| `price_band` | `VARCHAR(20)` | Budget / Mid / Premium | Drives the price range items on that restaurant's menu are drawn from |
| `active_flag` | `SMALLINT` | 1 = active, 0 = inactive | ~8% of restaurants are inactive; not currently used to filter any analysis |

## `orders`

One row per order. This is the central fact table almost every analysis joins against.

| Column | Type | Business meaning | Caveats |
|---|---|---|---|
| `order_id` | `VARCHAR(15)` PK | Unique order identifier | |
| `customer_id` | `VARCHAR(15)` FK → `customers` | Which customer placed the order | |
| `restaurant_id` | `VARCHAR(15)` FK → `restaurants` | Which restaurant fulfilled the order | |
| `order_date` | `DATE` | Calendar date the order was placed | For a customer's first order, always within 0–7 days of `signup_date`; subsequent orders are sampled forward from the first order date only (never before it) |
| `order_hour` | `SMALLINT` | Hour of day (0–23) | Weighted toward lunch (12–13h) and dinner (18–20h) peaks |
| `order_day_of_week` | `VARCHAR(10)` | Day name | Derived from `order_date` |
| `order_month` | `VARCHAR(7)` | `YYYY-MM` of `order_date` | Used as the grain for `v_monthly_kpis` |
| `is_weekend` | `SMALLINT` | 1 if Saturday/Sunday | Weekend order volume is ~35–45% higher per day than weekday (seasonality design choice) |
| `items_count` | `SMALLINT` | Number of line items in the order | |
| `gross_order_value` | `NUMERIC(10,2)` | Sum of item line totals before any discount | |
| `net_order_value` | `NUMERIC(10,2)` | `gross_order_value` minus any applied discount | **The revenue figure used throughout the analysis** (GMV, LTV, Pareto) |
| `payment_method` | `VARCHAR(30)` | UPI / Credit Card / Debit Card / Digital Wallet / Cash on Delivery | Not currently used in any analysis query |
| `order_status` | `VARCHAR(20)` | Delivered / Cancelled / Refunded | **Every revenue, retention, and segmentation query must filter `WHERE order_status = 'Delivered'`** — this was the single most common bug found and fixed across this project's history (missing this filter inflated GMV and miscounted retention in ~5 separate places). ~3.5% of orders are Cancelled (very-late deliveries), ~3% of the remainder are Refunded |

## `order_items`

One row per line item within an order.

| Column | Type | Business meaning | Caveats |
|---|---|---|---|
| `order_item_id` | `VARCHAR(15)` PK | Unique line-item identifier | |
| `order_id` | `VARCHAR(15)` FK → `orders` | Parent order | Every order has ≥1 item |
| `item_id` | `VARCHAR(15)` | Menu item identifier | Reused across orders/restaurants (4,000 distinct IDs); not a real per-restaurant menu |
| `item_category` | `VARCHAR(50)` | Starters / Main Course / Beverages / Desserts / Sides / Combo Meals | |
| `quantity` | `SMALLINT` | Units of this item ordered | 1–3, weighted toward 1 |
| `item_price` | `NUMERIC(10,2)` | Unit price | Drawn from the parent restaurant's `price_band` range, adjusted down for price-sensitive (high discount-affinity) customers |

## `delivery_events`

Exactly one row per order (1:1 with `orders`).

| Column | Type | Business meaning | Caveats |
|---|---|---|---|
| `delivery_event_id` | `VARCHAR(15)` PK | Unique delivery event identifier | |
| `order_id` | `VARCHAR(15)` FK, UNIQUE → `orders` | The order this delivery corresponds to | Enforced 1:1 by a UNIQUE constraint |
| `pickup_time` | `TIMESTAMP` | When the order was picked up for delivery | |
| `dispatched_time` | `TIMESTAMP` | When the order left the restaurant | |
| `delivered_time` | `TIMESTAMP` | When the order was delivered | |
| `delivery_delay_min` | `NUMERIC(6,1)` | Minutes late (negative = early) relative to `promised_delivery_min` | **The key driver variable in the delay-vs-churn analysis** (bucketed into 0-10/10-20/20-35/35-50/50+ min bands); drawn from a right-tailed gamma distribution scaled by each customer's latent `delay_affinity` — a modeling assumption, not measured logistics data |
| `promised_delivery_min` | `SMALLINT` | Promised delivery time in minutes | Uniform 25–55 minutes |
| `delivery_status` | `VARCHAR(20)` | On Time / Slightly Late / Late / Very Late / Cancelled | Derived from `delivery_delay_min`; feeds `orders.order_status` (Very Late orders have a 12% chance of becoming Cancelled) |

## `discounts`

One row per discounted order (~45% of orders have a matching row; the rest have none).

| Column | Type | Business meaning | Caveats |
|---|---|---|---|
| `discount_id` | `VARCHAR(15)` PK | Unique discount identifier | |
| `order_id` | `VARCHAR(15)` FK → `orders` | The discounted order | An order with no row here is not discounted — always `LEFT JOIN` from `orders`, never `INNER JOIN` |
| `discount_type` | `VARCHAR(30)` | Flat / Percentage / Free Delivery / Buy1Get1 | |
| `discount_value` | `NUMERIC(10,2)` | Currency amount deducted from `gross_order_value` | Capped at 70% of the order's gross value |
| `discount_pct` | `NUMERIC(5,1)` | Percentage discount (0 for Flat/Free Delivery types) | Only meaningful for Percentage/Buy1Get1 discount types |
| `promo_source` | `VARCHAR(50)` | In-App Promo / First Order Offer / Loyalty Reward / Referral Bonus / Seasonal Campaign | Not currently used in any analysis query |

## Derived / analysis-layer concepts

These aren't raw columns but recur across `analysis/sql/queries.sql`, `analysis/sql/views.sql`, and `dashboard/build_dashboard.py`, and are worth defining once:

- **Snapshot date**: `MAX(order_date)` across all orders — the "as-of" date every recency/right-censoring calculation is measured against. Computed fresh in every query rather than hardcoded.
- **Right-censoring**: a customer is only classified as "retained" or "churned" once their 90-day post-first-order window has actually elapsed (or they've already re-ordered within it). Customers acquired too recently to have a knowable outcome are excluded from the retention denominator entirely, rather than counted as churned.
- **Retained (90-day)**: a customer has ≥1 *Delivered* order strictly after (`>`, not `>=`) their first delivered order and within 90 days (`<=`) of it. This exact boundary (matching the Power BI DAX measure) was the source of a historical ~0.08pp reconciliation gap against a naive "gap to the 2nd order" implementation.
- **RFM segment**: assigned via fixed thresholds on `recency_days`/`frequency` (e.g. Champion = last order ≤30 days ago AND ≥5 lifetime orders) — not via the NTILE quartile scores, which are computed and exposed only as informational reference columns.
