"""
FoodPulse — Synthetic Data Generator
Generates internally-consistent, reproducible food-delivery data for a
retention / churn / revenue-risk case study (SQL + Power BI ready).

Run:
    python generate_data.py
"""

import os
import numpy as np
import pandas as pd
from faker import Faker

# --------------------------------------------------------------------------
# Reproducibility
# --------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)
Faker.seed(SEED)
fake = Faker()

# --------------------------------------------------------------------------
# Global constants
# --------------------------------------------------------------------------
OUTPUT_DIR = os.path.join("data", "raw")

N_CUSTOMERS = 50_000
N_RESTAURANTS = 500
TARGET_ORDERS = 380_000

START_DATE = pd.Timestamp("2023-07-01")
END_DATE = pd.Timestamp("2025-06-30")  # 24-month window

def _generate_cities(n=10):
    """Reproducible set of distinct city names, sourced from Faker."""
    cities = []
    while len(cities) < n:
        candidate = fake.city()
        if candidate not in cities:
            cities.append(candidate)
    return cities


CITIES = _generate_cities()

CUISINES = [
    "North Indian", "South Indian", "Chinese", "Italian", "Fast Food",
    "Desserts & Bakery", "Continental", "Mexican", "Biryani", "Healthy & Salads",
]

PRICE_BANDS = ["Budget", "Mid", "Premium"]
PRICE_BAND_WEIGHTS = [0.45, 0.40, 0.15]
PRICE_BAND_ITEM_RANGE = {
    "Budget": (60, 180),
    "Mid": (140, 380),
    "Premium": (300, 750),
}

ACQUISITION_CHANNELS = ["Referral", "Organic", "App Store", "Social Media", "Paid Search"]
CHANNEL_WEIGHTS = [0.12, 0.30, 0.18, 0.20, 0.20]
# retention effect added directly to a customer's retention score
CHANNEL_RETENTION_EFFECT = {
    "Referral": 0.55,
    "Organic": 0.10,
    "App Store": 0.05,
    "Social Media": -0.20,
    "Paid Search": -0.35,
}

PAYMENT_METHODS = ["UPI", "Credit Card", "Debit Card", "Digital Wallet", "Cash on Delivery"]
PAYMENT_WEIGHTS = [0.38, 0.20, 0.16, 0.18, 0.08]

ITEM_CATEGORIES = ["Starters", "Main Course", "Beverages", "Desserts", "Sides", "Combo Meals"]

DISCOUNT_TYPES = ["Flat", "Percentage", "Free Delivery", "Buy1Get1"]
PROMO_SOURCES = ["In-App Promo", "First Order Offer", "Loyalty Reward", "Referral Bonus", "Seasonal Campaign"]


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_csv(df: pd.DataFrame, name: str):
    path = os.path.join(OUTPUT_DIR, name)
    df.to_csv(path, index=False)
    print(f"  saved {name:<22} rows={len(df):>8,}  ->  {path}")


# --------------------------------------------------------------------------
# 1. Customers + latent traits
# --------------------------------------------------------------------------
def generate_customers():
    n = N_CUSTOMERS
    customer_id = [f"C{100000 + i}" for i in range(n)]

    city = rng.choice(CITIES, size=n)
    channel = rng.choice(ACQUISITION_CHANNELS, size=n, p=CHANNEL_WEIGHTS)

    # signup_date / cohort_month are filled in later, once each customer's
    # order dates are known (signup = shortly before their first order)
    customers_df = pd.DataFrame({
        "customer_id": customer_id,
        "signup_date": pd.NaT,
        "acquisition_channel": channel,
        "city": city,
        "cohort_month": "",
    })

    # ---- latent traits (internal use only, not exported) ----
    base_loyalty = rng.beta(2.0, 5.0, size=n)                 # right-skewed, mostly low loyalty
    delay_affinity = rng.gamma(2.0, 1.5, size=n)               # exposure to poor logistics (higher = worse)
    discount_affinity = rng.beta(2.0, 3.0, size=n)             # price sensitivity / discount-seeking
    channel_effect = np.array([CHANNEL_RETENTION_EFFECT[c] for c in channel])

    retention_score = (
        1.3 * base_loyalty
        + channel_effect
        - 0.55 * discount_affinity
        - 0.22 * delay_affinity
        + rng.normal(0, 0.12, size=n)
    )

    # basket-size / spend multiplier correlated with loyalty -> drives revenue concentration
    spend_multiplier = np.clip(0.35 + 2.4 * base_loyalty + rng.normal(0, 0.22, size=n), 0.25, 4.2)

    latent = pd.DataFrame({
        "customer_id": customer_id,
        "base_loyalty": base_loyalty,
        "delay_affinity": delay_affinity,
        "discount_affinity": discount_affinity,
        "retention_score": retention_score,
        "spend_multiplier": spend_multiplier,
        "channel": channel,
    })

    return customers_df, latent


# --------------------------------------------------------------------------
# 2. Restaurants
# --------------------------------------------------------------------------
def generate_restaurants():
    n = N_RESTAURANTS
    restaurant_id = [f"R{1000 + i}" for i in range(n)]
    city = rng.choice(CITIES, size=n)
    cuisine = rng.choice(CUISINES, size=n)
    price_band = rng.choice(PRICE_BANDS, size=n, p=PRICE_BAND_WEIGHTS)
    active_flag = rng.choice([1, 0], size=n, p=[0.92, 0.08])

    restaurants_df = pd.DataFrame({
        "restaurant_id": restaurant_id,
        "city": city,
        "cuisine_type": cuisine,
        "price_band": price_band,
        "active_flag": active_flag,
    })
    return restaurants_df


# --------------------------------------------------------------------------
# 3. Order-count assignment per customer (repeat-order distribution)
# --------------------------------------------------------------------------
def assign_order_counts(latent: pd.DataFrame):
    n = len(latent)
    score = latent["retention_score"].to_numpy()

    # logistic probability of being a repeat customer
    a, b = 1.55, 0.0
    p_repeat = 1 / (1 + np.exp(-(a * score + b)))
    is_repeat = rng.random(n) < p_repeat

    order_count = np.ones(n, dtype=int)

    n_repeat = is_repeat.sum()
    # overdispersed count via negative binomial, mean driven by retention_score
    score_r = score[is_repeat]
    score_scaled = (score_r - score_r.min()) / (score_r.max() - score_r.min() + 1e-9)
    p_nb = np.clip(0.55 - 0.42 * score_scaled, 0.05, 0.85)
    raw_counts = rng.negative_binomial(n=3, p=p_nb) + 2  # minimum 2 orders for repeat customers
    order_count[is_repeat] = raw_counts

    # scale repeat counts so the grand total lands near TARGET_ORDERS
    n_one_time = n - n_repeat
    current_repeat_total = order_count[is_repeat].sum()
    target_repeat_total = TARGET_ORDERS - n_one_time
    scale = max(target_repeat_total / current_repeat_total, 0.1)
    scaled = np.round(order_count[is_repeat] * scale).astype(int)
    scaled = np.clip(scaled, 2, 400)
    order_count[is_repeat] = scaled

    latent = latent.copy()
    latent["is_repeat"] = is_repeat
    latent["order_count"] = order_count
    return latent


# --------------------------------------------------------------------------
# 4. Seasonality weight curve (daily), used to sample order dates
# --------------------------------------------------------------------------
def build_day_weights():
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    dow = dates.dayofweek  # Mon=0 ... Sun=6
    month = dates.month

    weekend_w = np.where(dow >= 5, 1.40, 1.0)          # weekends ~35-45% higher
    season_w = np.where(np.isin(month, [7, 8, 9]), 1.22, 1.0)  # Jul-Sep uplift

    # smooth monthly noise so seasonality isn't a single flat spike
    year_month = dates.to_period("M")
    unique_ym = year_month.unique()
    monthly_noise_map = {
        ym: rng.normal(1.0, 0.08) for ym in unique_ym
    }
    monthly_noise = np.array([monthly_noise_map[ym] for ym in year_month])
    monthly_noise = np.clip(monthly_noise, 0.75, 1.3)

    daily_jitter = np.clip(rng.normal(1.0, 0.05, size=len(dates)), 0.6, 1.5)

    weight = weekend_w * season_w * monthly_noise * daily_jitter
    return dates, weight


DATES, DAY_WEIGHTS = build_day_weights()
DAY_PROBS = DAY_WEIGHTS / DAY_WEIGHTS.sum()


# --------------------------------------------------------------------------
# 5. Orders (dates, restaurant assignment, hour, payment, status - values
#    filled in after order_items are generated)
# --------------------------------------------------------------------------
HOUR_BUCKETS = list(range(24))
HOUR_WEIGHTS = np.array([
    0.5, 0.3, 0.2, 0.2, 0.2, 0.3, 0.5, 1.0,       # 0-7
    1.6, 1.4, 1.2, 1.8, 3.2, 3.0, 1.6, 1.2,       # 8-15
    1.4, 1.8, 2.6, 3.4, 3.2, 2.4, 1.6, 0.9,       # 16-23
])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()


def generate_orders(customers_df, restaurants_df, latent):
    order_customer_ids = np.repeat(latent["customer_id"].to_numpy(), latent["order_count"].to_numpy())
    order_discount_affinity = np.repeat(latent["discount_affinity"].to_numpy(), latent["order_count"].to_numpy())
    order_spend_multiplier = np.repeat(latent["spend_multiplier"].to_numpy(), latent["order_count"].to_numpy())
    order_delay_affinity = np.repeat(latent["delay_affinity"].to_numpy(), latent["order_count"].to_numpy())

    total_orders = len(order_customer_ids)

    # draw order dates i.i.d. from the global seasonality distribution (weekend +
    # Jul-Sep uplift baked into DAY_PROBS), then sort chronologically within each
    # customer. Because draws are i.i.d., every customer segment (incl. one-time
    # buyers) reproduces the same global seasonal mix - no artificial growth ramp.
    order_dates = rng.choice(DATES, size=total_orders, replace=True, p=DAY_PROBS)

    tmp = pd.DataFrame({
        "customer_id": order_customer_ids,
        "order_date": order_dates,
        "discount_affinity": order_discount_affinity,
        "spend_multiplier": order_spend_multiplier,
        "delay_affinity": order_delay_affinity,
    }).sort_values(["customer_id", "order_date"], kind="mergesort").reset_index(drop=True)

    total_orders = len(tmp)
    order_id = np.array([f"O{i:08d}" for i in range(total_orders)])

    restaurant_ids = restaurants_df["restaurant_id"].to_numpy()
    restaurant_choice_idx = rng.integers(0, len(restaurant_ids), size=total_orders)
    order_restaurant_id = restaurant_ids[restaurant_choice_idx]
    restaurant_price_band = restaurants_df["price_band"].to_numpy()[restaurant_choice_idx]

    order_hour = rng.choice(HOUR_BUCKETS, size=total_orders, p=HOUR_WEIGHTS)
    payment_method = rng.choice(PAYMENT_METHODS, size=total_orders, p=PAYMENT_WEIGHTS)

    order_dates_idx = pd.DatetimeIndex(tmp["order_date"])
    dow = order_dates_idx.dayofweek
    is_weekend = (dow >= 5).astype(int)

    orders_df = pd.DataFrame({
        "order_id": order_id,
        "customer_id": tmp["customer_id"].to_numpy(),
        "restaurant_id": order_restaurant_id,
        "order_date": order_dates_idx.strftime("%Y-%m-%d"),
        "order_hour": order_hour,
        "order_day_of_week": order_dates_idx.day_name(),
        "order_month": order_dates_idx.strftime("%Y-%m"),
        "is_weekend": is_weekend,
        "payment_method": payment_method,
    })

    # internal helper columns (dropped before export) used by downstream steps
    helper = pd.DataFrame({
        "order_id": order_id,
        "price_band": restaurant_price_band,
        "discount_affinity": tmp["discount_affinity"].to_numpy(),
        "spend_multiplier": tmp["spend_multiplier"].to_numpy(),
        "delay_affinity": tmp["delay_affinity"].to_numpy(),
    })

    return orders_df, helper


def finalize_customer_signup(customers_df, orders_df):
    """Derive signup_date/cohort_month from each customer's first observed order."""
    first_order = orders_df.groupby("customer_id")["order_date"].min()
    first_order = pd.to_datetime(first_order)
    offset_days = rng.integers(0, 11, size=len(first_order))
    signup_date = first_order - pd.to_timedelta(offset_days, unit="D")
    signup_date = signup_date.clip(lower=START_DATE)

    customers_df = customers_df.drop(columns=["signup_date", "cohort_month"]).merge(
        signup_date.rename("signup_date"), left_on="customer_id", right_index=True, how="left"
    )
    # customers with no generated orders (should not happen given order_count>=1) fall back to START_DATE
    customers_df["signup_date"] = customers_df["signup_date"].fillna(START_DATE)
    customers_df["cohort_month"] = customers_df["signup_date"].dt.to_period("M").astype(str)
    customers_df["signup_date"] = customers_df["signup_date"].dt.strftime("%Y-%m-%d")
    customers_df = customers_df[["customer_id", "signup_date", "acquisition_channel", "city", "cohort_month"]]
    return customers_df


# --------------------------------------------------------------------------
# 6. Order items (also finalizes items_count / gross_order_value on orders)
# --------------------------------------------------------------------------
def generate_order_items(orders_df, helper):
    n_orders = len(orders_df)

    # basket size driven by spend_multiplier (loyal/high-spend customers order more items)
    lam = np.clip(1.4 + 0.9 * (helper["spend_multiplier"].to_numpy() - 1.0), 0.8, 4.5)
    items_count = rng.poisson(lam) + 1
    items_count = np.clip(items_count, 1, 8)

    total_items = int(items_count.sum())
    item_order_id = np.repeat(orders_df["order_id"].to_numpy(), items_count)
    item_price_band = np.repeat(helper["price_band"].to_numpy(), items_count)
    item_spend_mult = np.repeat(helper["spend_multiplier"].to_numpy(), items_count)
    item_discount_aff = np.repeat(helper["discount_affinity"].to_numpy(), items_count)

    item_category = rng.choice(ITEM_CATEGORIES, size=total_items)

    low = np.array([PRICE_BAND_ITEM_RANGE[b][0] for b in item_price_band])
    high = np.array([PRICE_BAND_ITEM_RANGE[b][1] for b in item_price_band])
    base_price = rng.uniform(low, high)
    # price-sensitive (high discount_affinity) customers skew toward cheaper items
    price_adjust = 1.0 - 0.25 * item_discount_aff + 0.15 * (item_spend_mult - 1.0)
    item_price = np.round(np.clip(base_price * price_adjust, 30, None), 2)

    quantity = rng.choice([1, 2, 3], size=total_items, p=[0.78, 0.17, 0.05])

    item_id = [f"ITEM{1000 + i % 4000}" for i in range(total_items)]
    order_item_id = np.array([f"OI{i:09d}" for i in range(total_items)])

    order_items_df = pd.DataFrame({
        "order_item_id": order_item_id,
        "order_id": item_order_id,
        "item_id": item_id,
        "item_category": item_category,
        "quantity": quantity,
        "item_price": item_price,
    })

    line_total = order_items_df["quantity"] * order_items_df["item_price"]
    gross_by_order = line_total.groupby(order_items_df["order_id"]).sum()

    orders_df = orders_df.copy()
    orders_df["items_count"] = items_count
    orders_df["gross_order_value"] = orders_df["order_id"].map(gross_by_order).round(2)

    return orders_df, order_items_df


# --------------------------------------------------------------------------
# 7. Discounts (~45% of orders) + net_order_value on orders
# --------------------------------------------------------------------------
def generate_discounts(orders_df, helper):
    n_orders = len(orders_df)
    discount_affinity = helper.set_index("order_id").loc[orders_df["order_id"], "discount_affinity"].to_numpy()

    # heavier discount-seekers are more likely to have a discounted order
    discount_prob = np.clip(0.20 + 0.55 * discount_affinity, 0.05, 0.85)
    # rescale so overall share lands near 45%
    scale = 0.45 / discount_prob.mean()
    discount_prob = np.clip(discount_prob * scale, 0.02, 0.95)
    has_discount = rng.random(n_orders) < discount_prob

    disc_orders = orders_df.loc[has_discount, ["order_id"]].reset_index(drop=True)
    disc_gross = orders_df.loc[has_discount, "gross_order_value"].to_numpy()
    n_disc = len(disc_orders)

    discount_type = rng.choice(DISCOUNT_TYPES, size=n_disc, p=[0.35, 0.35, 0.15, 0.15])
    promo_source = rng.choice(PROMO_SOURCES, size=n_disc)

    discount_pct = np.where(
        np.isin(discount_type, ["Percentage", "Buy1Get1"]),
        np.round(rng.uniform(10, 50, size=n_disc), 1),
        0.0,
    )
    flat_value = np.round(rng.uniform(20, 120, size=n_disc), 2)
    pct_value = np.round(disc_gross * discount_pct / 100, 2)
    discount_value = np.where(discount_type == "Flat", flat_value,
                       np.where(discount_type == "Free Delivery", np.round(rng.uniform(25, 60, size=n_disc), 2),
                                pct_value))
    discount_value = np.minimum(discount_value, disc_gross * 0.7)

    discount_id = np.array([f"D{i:08d}" for i in range(n_disc)])
    discounts_df = pd.DataFrame({
        "discount_id": discount_id,
        "order_id": disc_orders["order_id"].to_numpy(),
        "discount_type": discount_type,
        "discount_value": discount_value,
        "discount_pct": discount_pct,
        "promo_source": promo_source,
    })

    net_order_value = orders_df["gross_order_value"].to_numpy().copy()
    discount_map = discounts_df.set_index("order_id")["discount_value"]
    net_order_value = net_order_value - orders_df["order_id"].map(discount_map).fillna(0).to_numpy()
    orders_df = orders_df.copy()
    orders_df["net_order_value"] = np.round(net_order_value, 2)

    return orders_df, discounts_df


# --------------------------------------------------------------------------
# 8. Delivery events (1 per order) with right-tailed delay distribution
# --------------------------------------------------------------------------
def generate_delivery_events(orders_df, helper):
    n_orders = len(orders_df)
    delay_affinity = helper.set_index("order_id").loc[orders_df["order_id"], "delay_affinity"].to_numpy()

    promised_delivery_min = rng.integers(25, 55, size=n_orders)

    # right-tailed delay: gamma noise scaled by customer delay_affinity (higher
    # affinity = consistently worse logistics exposure = higher expected delay)
    delay_scale = 3.0 + 3.2 * delay_affinity
    raw_delay = rng.gamma(shape=1.6, scale=delay_scale, size=n_orders)
    delivery_delay_min = np.round(raw_delay - 6, 1)  # allows early/on-time deliveries
    delivery_delay_min = np.clip(delivery_delay_min, -15, 180)

    order_datetime = pd.to_datetime(orders_df["order_date"]) + pd.to_timedelta(orders_df["order_hour"], unit="h")
    prep_min = rng.integers(8, 25, size=n_orders)
    dispatch_min = rng.integers(3, 12, size=n_orders)

    dispatched_time = order_datetime + pd.to_timedelta(prep_min, unit="m")
    pickup_time = dispatched_time + pd.to_timedelta(dispatch_min, unit="m")
    travel_min = np.clip(promised_delivery_min + delivery_delay_min - prep_min - dispatch_min, 5, None)
    delivered_time = pickup_time + pd.to_timedelta(travel_min, unit="m")

    delivery_status = np.where(
        delivery_delay_min <= 0, "On Time",
        np.where(delivery_delay_min <= 15, "Slightly Late",
        np.where(delivery_delay_min <= 45, "Late", "Very Late"))
    )
    # a small share of very-late orders end up cancelled at delivery stage
    cancel_roll = rng.random(n_orders)
    delivery_status = np.where((delivery_status == "Very Late") & (cancel_roll < 0.12), "Cancelled", delivery_status)

    delivery_event_id = np.array([f"DE{i:08d}" for i in range(n_orders)])
    delivery_events_df = pd.DataFrame({
        "delivery_event_id": delivery_event_id,
        "order_id": orders_df["order_id"].to_numpy(),
        "pickup_time": pickup_time.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "dispatched_time": dispatched_time.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "delivered_time": delivered_time.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "delivery_delay_min": delivery_delay_min,
        "promised_delivery_min": promised_delivery_min,
        "delivery_status": delivery_status,
    })

    orders_df = orders_df.copy()
    orders_df["order_status"] = np.where(
        delivery_status == "Cancelled", "Cancelled",
        np.where(rng.random(n_orders) < 0.03, "Refunded", "Delivered"),
    )

    return orders_df, delivery_events_df


# --------------------------------------------------------------------------
# 9. Validation
# --------------------------------------------------------------------------
def run_validations(customers_df, restaurants_df, orders_df, order_items_df, delivery_events_df, discounts_df):
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    # row counts
    print("\n-- Row counts --")
    for name, df in [
        ("customers", customers_df), ("restaurants", restaurants_df),
        ("orders", orders_df), ("order_items", order_items_df),
        ("delivery_events", delivery_events_df), ("discounts", discounts_df),
    ]:
        print(f"  {name:<16}: {len(df):>10,}")

    # PK uniqueness
    print("\n-- Primary key uniqueness --")
    pk_checks = [
        ("customers.customer_id", customers_df["customer_id"]),
        ("restaurants.restaurant_id", restaurants_df["restaurant_id"]),
        ("orders.order_id", orders_df["order_id"]),
        ("order_items.order_item_id", order_items_df["order_item_id"]),
        ("delivery_events.delivery_event_id", delivery_events_df["delivery_event_id"]),
        ("discounts.discount_id", discounts_df["discount_id"]),
    ]
    for label, series in pk_checks:
        print(f"  {label:<34}: unique={series.is_unique}  nulls={series.isna().sum()}")

    # FK integrity
    print("\n-- Foreign key integrity --")
    valid_customers = set(customers_df["customer_id"])
    valid_restaurants = set(restaurants_df["restaurant_id"])
    valid_orders = set(orders_df["order_id"])
    print(f"  orders.customer_id in customers   : {orders_df['customer_id'].isin(valid_customers).all()}")
    print(f"  orders.restaurant_id in restaurants: {orders_df['restaurant_id'].isin(valid_restaurants).all()}")
    print(f"  order_items.order_id in orders     : {order_items_df['order_id'].isin(valid_orders).all()}")
    print(f"  delivery_events.order_id in orders : {delivery_events_df['order_id'].isin(valid_orders).all()}")
    print(f"  discounts.order_id in orders       : {discounts_df['order_id'].isin(valid_orders).all()}")

    # 1 delivery event per order, >=1 item per order
    orders_with_items = order_items_df["order_id"].nunique()
    orders_with_delivery = delivery_events_df["order_id"].nunique()
    print(f"  every order has >=1 item           : {orders_with_items == len(orders_df)}")
    print(f"  every order has exactly 1 delivery : {orders_with_delivery == len(orders_df) and delivery_events_df['order_id'].is_unique}")

    # one-order customer share
    orders_per_customer = orders_df.groupby("customer_id").size()
    one_order_share = (orders_per_customer == 1).mean() * 100
    all_customers_with_orders = orders_per_customer.reindex(customers_df["customer_id"], fill_value=0)
    one_order_share_incl_zero = (all_customers_with_orders <= 1).mean() * 100
    print("\n-- Customer lifecycle --")
    print(f"  % customers with exactly 1 order (of ordering customers): {one_order_share:.2f}%")
    print(f"  % customers with <=1 order (incl. non-orderers)         : {one_order_share_incl_zero:.2f}%")
    print(f"  max orders by a single customer                          : {orders_per_customer.max()}")

    # discount share
    discounted_orders = discounts_df["order_id"].nunique()
    print("\n-- Discount usage --")
    print(f"  % of orders with a discount: {discounted_orders / len(orders_df) * 100:.2f}%")

    # weekend vs weekday volume
    print("\n-- Seasonality --")
    weekend_count = (orders_df["is_weekend"] == 1).sum()
    weekday_count = (orders_df["is_weekend"] == 0).sum()
    weekend_avg_per_day = weekend_count / (2 * 104)  # ~104 weekends of 2 days across 24 months
    weekday_avg_per_day = weekday_count / (5 * 104)
    uplift = (weekend_avg_per_day / weekday_avg_per_day - 1) * 100
    print(f"  weekend orders: {weekend_count:,}  weekday orders: {weekday_count:,}")
    print(f"  weekend-vs-weekday daily volume uplift: {uplift:.1f}%")

    order_month_num = pd.to_datetime(orders_df["order_date"]).dt.month
    jul_sep = order_month_num.isin([7, 8, 9]).sum()
    other = (~order_month_num.isin([7, 8, 9])).sum()
    jul_sep_avg = jul_sep / (3 / 12 * (END_DATE - START_DATE).days / 30.44)
    other_avg = other / (9 / 12 * (END_DATE - START_DATE).days / 30.44)
    jul_sep_uplift = (jul_sep_avg / other_avg - 1) * 100
    print(f"  Jul-Sep orders: {jul_sep:,}  other-month orders: {other:,}")
    print(f"  Jul-Sep vs other-months monthly volume uplift: {jul_sep_uplift:.1f}%")

    # revenue concentration
    print("\n-- Revenue concentration --")
    spend_per_customer = orders_df.groupby("customer_id")["net_order_value"].sum().sort_values(ascending=False)
    top_15_pct_n = max(int(len(spend_per_customer) * 0.15), 1)
    top_15_share = spend_per_customer.head(top_15_pct_n).sum() / spend_per_customer.sum() * 100
    print(f"  top 15% of customers contribute {top_15_share:.1f}% of GMV")

    # delivery delay vs churn proxy segment
    print("\n-- Delivery delay vs churn proxy --")
    avg_delay = delivery_events_df.merge(orders_df[["order_id", "customer_id"]], on="order_id") \
        .groupby("customer_id")["delivery_delay_min"].mean()
    churn_proxy = orders_per_customer.reindex(avg_delay.index, fill_value=1) == 1  # one-order = churned proxy
    print(f"  avg delivery delay (churned proxy, 1 order) : {avg_delay[churn_proxy].mean():.2f} min")
    print(f"  avg delivery delay (retained, >1 order)     : {avg_delay[~churn_proxy].mean():.2f} min")

    # summary stats
    print("\n-- Summary statistics --")
    print(orders_df[["gross_order_value", "net_order_value", "items_count"]].describe().round(2))
    print(delivery_events_df[["delivery_delay_min", "promised_delivery_min"]].describe().round(2))

    print("\n" + "=" * 70)
    print("Validation complete.")
    print("=" * 70)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ensure_output_dir()

    print("Generating customers & restaurants...")
    customers_df, latent = generate_customers()
    restaurants_df = generate_restaurants()

    print("Assigning repeat-order behavior...")
    latent = assign_order_counts(latent)

    print("Generating orders (dates, seasonality, restaurant assignment)...")
    orders_df, helper = generate_orders(customers_df, restaurants_df, latent)

    print("Deriving signup dates from first orders...")
    customers_df = finalize_customer_signup(customers_df, orders_df)

    print("Generating order items and order value totals...")
    orders_df, order_items_df = generate_order_items(orders_df, helper)

    print("Generating discounts and net order values...")
    orders_df, discounts_df = generate_discounts(orders_df, helper)

    print("Generating delivery events...")
    orders_df, delivery_events_df = generate_delivery_events(orders_df, helper)

    # finalize column order per spec + drop helper columns
    orders_out = orders_df[[
        "order_id", "customer_id", "restaurant_id", "order_date", "order_hour",
        "order_day_of_week", "order_month", "is_weekend", "items_count",
        "gross_order_value", "net_order_value", "payment_method", "order_status",
    ]]

    print("\nSaving CSV files...")
    save_csv(customers_df, "customers.csv")
    save_csv(restaurants_df, "restaurants.csv")
    save_csv(orders_out, "orders.csv")
    save_csv(order_items_df, "order_items.csv")
    save_csv(delivery_events_df, "delivery_events.csv")
    save_csv(discounts_df, "discounts.csv")

    run_validations(customers_df, restaurants_df, orders_out, order_items_df, delivery_events_df, discounts_df)


if __name__ == "__main__":
    main()
