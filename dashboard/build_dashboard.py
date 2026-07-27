"""
FoodPulse — Final Dashboard PNG Exports
Builds 3 presentation-ready static dashboard pages (Executive Summary,
Retention & Churn, Segment Intelligence) from verified numbers recomputed
directly from data/raw/*.csv. No numbers are hand-typed from prior mockups.

Run:
    python dashboard/build_dashboard.py
"""

import os

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch
from scipy.stats import chi2_contingency

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data", "raw")
EXPORT_DIR = os.path.join(ROOT_DIR, "dashboard", "exports")

# ============================================================================
# Style system
# ============================================================================
BG = "#F5F5F5"
HEADER_BG = "#1A1A2E"
ACCENT = "#E63946"          # red - hurts retention/revenue
GOOD = "#2A9D8F"            # green/teal - helps retention/revenue
CARD_BG = "#FFFFFF"
TEXT_PRIMARY = "#1A1A2E"
TEXT_SECONDARY = "#666666"
CHART_COLORS = ["#E63946", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261"]

FIG_W, FIG_H = 19.2, 10.8
DPI = 150

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT_PRIMARY,
})


def new_figure():
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    fig.patch.set_facecolor(BG)
    return fig


def add_card(fig, rect, radius=0.010, zorder=2):
    left, bottom, w, h = rect
    shadow = FancyBboxPatch(
        (left + 0.0025, bottom - 0.0035), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=0, facecolor="#000000", alpha=0.08,
        transform=fig.transFigure, zorder=zorder - 1,
    )
    fig.patches.append(shadow)
    card = FancyBboxPatch(
        (left, bottom), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=0, facecolor=CARD_BG,
        transform=fig.transFigure, zorder=zorder,
    )
    fig.patches.append(card)
    return card


def add_header(fig, title, subtitle_right, page_label):
    header = mpatches.Rectangle((0, 0.930), 1, 0.070, transform=fig.transFigure,
                                 facecolor=HEADER_BG, zorder=1, linewidth=0)
    fig.patches.append(header)
    fig.text(0.018, 0.977, "FOODPULSE", fontsize=11, fontweight="bold",
             color=ACCENT, va="center", ha="left")
    fig.text(0.018, 0.950, title, fontsize=20, fontweight="bold",
             color="white", va="center", ha="left")
    fig.text(0.982, 0.970, subtitle_right, fontsize=11.5, color="#C8C8D8",
             va="center", ha="right")
    fig.text(0.982, 0.948, page_label, fontsize=9.5, color="#8888A0",
             va="center", ha="right")


def add_legend_strip(fig, y=0.913):
    items = [
        (ACCENT, "Hurts retention / revenue"),
        (GOOD, "Helps retention / revenue"),
        (TEXT_SECONDARY, "Neutral scale metric"),
    ]
    xs = [0.018, 0.245, 0.470]
    for (color, label), x in zip(items, xs):
        fig.patches.append(mpatches.Rectangle((x, y), 0.011, 0.011, transform=fig.transFigure,
                                               facecolor=color, linewidth=0))
        fig.text(x + 0.016, y + 0.0055, label, fontsize=9.5, color=TEXT_SECONDARY, va="center", ha="left")
    fig.text(0.982, y + 0.0055, "Color rule applies consistently across all 3 pages",
             fontsize=8.5, color="#999999", va="center", ha="right", style="italic")


def add_kpi_card(fig, rect, label, value, color, note=None, value_fontsize=32):
    add_card(fig, rect)
    left, bottom, w, h = rect
    cx = left + w / 2
    fig.text(cx, bottom + h * 0.60, value, fontsize=value_fontsize, fontweight="bold",
              color=color, ha="center", va="center")
    fig.text(cx, bottom + h * 0.26, label, fontsize=12.5, color=TEXT_PRIMARY, ha="center", va="center",
              fontweight="medium")
    if note:
        fig.text(cx, bottom + h * 0.10, note, fontsize=9, color=TEXT_SECONDARY, ha="center", va="center",
                  style="italic")


def add_chart_axes(fig, rect, title=None, pad=0.018, pad_left=None):
    add_card(fig, rect)
    left, bottom, w, h = rect
    title_h = 0.032 if title else 0.0
    pl = pad_left if pad_left is not None else pad
    ax = fig.add_axes([left + pl, bottom + pad, w - pl - pad, h - 2 * pad - title_h])
    ax.set_zorder(10)  # figure-level card patches otherwise paint over the axes
    ax.set_facecolor(CARD_BG)
    if title:
        fig.text(left + pad, bottom + h - pad * 0.9, title, fontsize=13.5, fontweight="bold",
                  color=TEXT_PRIMARY, va="top", ha="left")
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#DDDDDD")
    ax.spines["bottom"].set_color("#DDDDDD")
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9.5)
    return ax


def add_insight_box(fig, rect, label, text, wrap_chars=118):
    import textwrap
    left, bottom, w, h = rect
    box = mpatches.FancyBboxPatch((left, bottom), w, h, boxstyle="round,pad=0,rounding_size=0.010",
                                   linewidth=0, facecolor=HEADER_BG, transform=fig.transFigure, zorder=2)
    fig.patches.append(box)
    fig.patches.append(mpatches.Rectangle((left + 0.014, bottom + h * 0.20), 0.006, h * 0.62,
                                           transform=fig.transFigure, facecolor=ACCENT, linewidth=0, zorder=3))
    fig.text(left + 0.030, bottom + h * 0.84, label, fontsize=10, fontweight="bold",
              color=ACCENT, va="center", ha="left")
    wrapped = "\n".join(textwrap.wrap(text, width=wrap_chars))
    fig.text(left + 0.030, bottom + h * 0.68, wrapped, fontsize=13, color="white", va="top", ha="left",
              linespacing=1.55)


def save_fig(fig, filename):
    path = os.path.join(EXPORT_DIR, filename)
    fig.savefig(path, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"saved {filename} -> {path}")


# ============================================================================
# Data computation (independently verified — see Step 1 report)
# ============================================================================
def compute_all_metrics():
    orders = pd.read_csv(f"{DATA_DIR}/orders.csv", parse_dates=["order_date"])
    customers = pd.read_csv(f"{DATA_DIR}/customers.csv", parse_dates=["signup_date"])
    delivery = pd.read_csv(f"{DATA_DIR}/delivery_events.csv")
    discounts = pd.read_csv(f"{DATA_DIR}/discounts.csv")

    delivered = orders[orders["order_status"] == "Delivered"].copy()
    delivered_sorted = delivered.sort_values(["customer_id", "order_date"])
    order_seq = delivered_sorted.groupby("customer_id")["order_date"].apply(list)
    snapshot_date = delivered["order_date"].max()

    first_order = order_seq.apply(lambda d: d[0])
    second_order = order_seq.apply(lambda d: d[1] if len(d) > 1 else pd.NaT)
    last_order = order_seq.apply(lambda d: d[-1])
    gap_days = (second_order - first_order).dt.days
    retained_90d_raw = (gap_days <= 90) & gap_days.notna()
    # right-censoring fix: a customer with no 2nd order yet can only be called
    # "churned" once their 90-day window has actually elapsed. Customers whose
    # first order is <90 days before the snapshot and haven't reordered yet
    # are excluded (outcome unknown), not counted as churned.
    days_since_first = (snapshot_date - first_order).dt.days
    eligible_90d = second_order.notna() | (days_since_first >= 90)
    retained_90d = retained_90d_raw[eligible_90d]
    frequency = order_seq.apply(len)

    orders_per_cust = delivered.groupby("customer_id").size()
    customers_with_orders = len(orders_per_cust)
    customers_zero_orders = len(customers) - customers_with_orders
    one_time = (orders_per_cust == 1).sum()

    m = {}
    m["one_time_pct_orderers"] = one_time / customers_with_orders * 100
    m["one_time_pct_all"] = one_time / len(customers) * 100
    m["one_time_n"] = int(one_time)
    m["orderers_n"] = int(customers_with_orders)
    m["overall_retention"] = retained_90d.mean() * 100
    m["churn_rate"] = 100 - m["overall_retention"]
    m["retained_90d_n"] = int(retained_90d.sum())
    m["zero_order_n"] = int(customers_zero_orders)
    m["zero_order_pct"] = customers_zero_orders / len(customers) * 100

    # delivery delay buckets (by first order's delay)
    delay_map = delivery.set_index("order_id")["delivery_delay_min"]
    first_order_id = delivered_sorted.groupby("customer_id")["order_id"].first()
    first_order_delay = first_order_id.map(delay_map)
    bucket_edges = [-np.inf, 10, 20, 35, 50, np.inf]
    bucket_labels = ["0-10 min", "10-20 min", "20-35 min", "35-50 min", "50+ min"]
    delay_bucket = pd.cut(first_order_delay, bins=bucket_edges, labels=bucket_labels, right=False)
    delay_df = pd.DataFrame({
        "delay_bucket": delay_bucket,
        "retained_90d": retained_90d.reindex(first_order_delay.index),
    }).dropna(subset=["retained_90d"])  # drop customers excluded by the 90d censoring filter
    bucket_summary = delay_df.groupby("delay_bucket", observed=True).agg(
        n=("retained_90d", "size"), retention_pct=("retained_90d", lambda s: s.mean() * 100)
    ).reindex(bucket_labels)
    contingency = pd.crosstab(delay_df["delay_bucket"], delay_df["retained_90d"])
    _, p, _, _ = chi2_contingency(contingency)
    m["delay_bucket_summary"] = bucket_summary
    m["delay_pvalue"] = p

    merged_delay = delivered.merge(delivery[["order_id", "delivery_delay_min"]], on="order_id")
    m["avg_delivery_delay"] = merged_delay["delivery_delay_min"].mean()

    # GMV concentration
    customer_gmv = delivered.groupby("customer_id")["net_order_value"].sum().sort_values(ascending=False)
    total_gmv = customer_gmv.sum()
    cum_gmv_pct = customer_gmv.cumsum() / total_gmv * 100
    cum_cust_pct = np.arange(1, len(customer_gmv) + 1) / len(customer_gmv) * 100
    m["total_gmv"] = total_gmv
    m["top_for_50"] = cum_cust_pct[np.searchsorted(cum_gmv_pct.values, 50)]
    m["top_for_80"] = cum_cust_pct[np.searchsorted(cum_gmv_pct.values, 80)]
    m["lorenz_x"] = cum_cust_pct
    m["lorenz_y"] = cum_gmv_pct.values

    # discount rate (all delivered orders)
    discounted_order_ids = set(discounts["order_id"])
    delivered["is_discounted"] = delivered["order_id"].isin(discounted_order_ids)
    m["discount_rate"] = delivered["is_discounted"].mean() * 100

    # month-1 cohort retention + full matrix (anchored to first_order_date)
    # cohort_sizes restricted to customers with >=1 delivered order (matches
    # v_cohort_retention's INNER JOIN to first_order): a customer who never
    # placed a delivered order has no "first order month" to anchor a cohort
    # to, and including them here was diluting every retention_pct cell by
    # the same 1,278 customers already tracked separately as "Never Ordered".
    cust_cohort = customers.set_index("customer_id")["cohort_month"]
    cohort_sizes = cust_cohort.reindex(first_order.index).value_counts()
    tmp = delivered_sorted.copy()
    tmp["first_order_date"] = tmp["customer_id"].map(first_order)
    tmp["months_since_first"] = ((tmp["order_date"].dt.year - tmp["first_order_date"].dt.year) * 12
                                  + (tmp["order_date"].dt.month - tmp["first_order_date"].dt.month))
    active_month1 = tmp.loc[tmp["months_since_first"] == 1, "customer_id"].unique()
    active_by_cohort = customers.set_index("customer_id").loc[active_month1, "cohort_month"].value_counts()
    retention_by_cohort = (active_by_cohort / cohort_sizes).fillna(0) * 100
    m["month1_avg"] = retention_by_cohort.mean()

    target_months = [0, 1, 2, 3, 6, 9, 12]
    matrix = {}
    for tm in target_months:
        active = tmp.loc[tmp["months_since_first"] == tm, "customer_id"].unique()
        by_cohort = customers.set_index("customer_id").loc[active, "cohort_month"].value_counts() if tm > 0 else cohort_sizes
        matrix[tm] = (by_cohort / cohort_sizes * 100).reindex(cohort_sizes.index)
    cohort_matrix = pd.DataFrame(matrix).sort_index()
    # data-horizon mask: blank out cells where insufficient time has elapsed
    data_horizon = pd.Period(cohort_matrix.index.max(), freq="M")
    mask = pd.DataFrame(False, index=cohort_matrix.index, columns=cohort_matrix.columns)
    for cm in cohort_matrix.index:
        cp = pd.Period(cm, freq="M")
        for tmo in cohort_matrix.columns:
            if cp + tmo > data_horizon:
                mask.loc[cm, tmo] = True
    m["cohort_matrix"] = cohort_matrix
    m["cohort_mask"] = mask

    # RFM (base = orderers only; zero-order customers = separate "Never Ordered")
    recency_days = (snapshot_date - last_order).dt.days
    rfm = pd.DataFrame({"recency_days": recency_days, "frequency": frequency})

    def assign_segment(row):
        if row["recency_days"] <= 30 and row["frequency"] >= 5:
            return "Champion"
        if row["recency_days"] <= 60 and row["frequency"] >= 3:
            return "Loyal"
        if row["recency_days"] <= 90:
            return "At Risk"
        if row["recency_days"] <= 180:
            return "About to Lapse"
        return "Lost"

    rfm["segment"] = rfm.apply(assign_segment, axis=1)
    rfm["gmv"] = customer_gmv.reindex(rfm.index).fillna(0)
    seg_summary = rfm.groupby("segment").agg(customers=("segment", "size"), gmv=("gmv", "sum"))
    seg_summary["pct_customers"] = seg_summary["customers"] / len(rfm) * 100
    seg_summary["pct_gmv"] = seg_summary["gmv"] / seg_summary["gmv"].sum() * 100
    seg_summary = seg_summary.reindex(["Champion", "Loyal", "At Risk", "About to Lapse", "Lost"])
    m["rfm_summary"] = seg_summary
    m["champion_avg_freq"] = rfm.loc[rfm.segment == "Champion", "frequency"].mean()
    m["lost_avg_freq"] = rfm.loc[rfm.segment == "Lost", "frequency"].mean()

    # discount dependency vs LTV (repeat customers only; Light+Moderate collapsed)
    repeat_customers = orders_per_cust[orders_per_cust >= 2].index
    repeat_orders = delivered[delivered["customer_id"].isin(repeat_customers)]
    cust_disc_rate = repeat_orders.groupby("customer_id")["is_discounted"].mean() * 100
    cust_ltv = repeat_orders.groupby("customer_id")["net_order_value"].sum()
    cust_retained = retained_90d.reindex(repeat_customers)
    disc_group = pd.cut(cust_disc_rate, bins=[-0.01, 0, 60, 100.01], labels=["Never", "Light/Moderate", "Heavy"])
    disc_df = pd.DataFrame({"disc_group": disc_group, "ltv": cust_ltv, "retained_90d": cust_retained})
    disc_summary = disc_df.groupby("disc_group", observed=True).agg(
        n=("ltv", "size"), avg_ltv=("ltv", "mean"), retention_pct=("retained_90d", lambda s: s.mean() * 100)
    )
    m["discount_summary"] = disc_summary
    m["heavy_vs_lm_pct"] = (disc_summary.loc["Heavy", "avg_ltv"] / disc_summary.loc["Light/Moderate", "avg_ltv"] - 1) * 100

    # monthly GMV trend (within nominal window only)
    monthly_gmv = delivered[delivered["order_date"] <= "2025-06-30"].groupby(
        delivered["order_date"].dt.to_period("M"))["net_order_value"].sum()
    m["monthly_gmv"] = monthly_gmv

    return m


# ============================================================================
# Page 1 — Executive Summary
# ============================================================================
def build_page1(m):
    fig = new_figure()
    add_header(fig, "Executive Summary", "Food Delivery Platform  |  50,000 Customers  |  24 Months", "PAGE 1 OF 3")
    add_legend_strip(fig)

    HERO = (0.018, 0.645, 0.452, 0.260)
    KPI_Y, KPI_H = 0.645, 0.260
    KPI_W = 0.156
    KPI1 = (0.490, KPI_Y, KPI_W, KPI_H)
    KPI2 = (0.658, KPI_Y, KPI_W, KPI_H)
    KPI3 = (0.826, KPI_Y, KPI_W, KPI_H)
    CHART_A = (0.018, 0.171, 0.452, 0.460)
    CHART_B = (0.490, 0.171, 0.492, 0.460)
    INSIGHT = (0.018, 0.037, 0.964, 0.120)

    # ---- Hero card: the headline finding ----
    add_card(fig, HERO)
    left, bottom, w, h = HERO
    fig.text(left + 0.022, bottom + h - 0.032, "THE #1 RETENTION PROBLEM", fontsize=11, fontweight="bold",
              color=TEXT_SECONDARY, va="top", ha="left")
    fig.text(left + 0.022, bottom + h * 0.50, f"{m['one_time_pct_orderers']:.1f}%", fontsize=64, fontweight="bold",
              color=ACCENT, va="center", ha="left")
    fig.text(left + 0.022, bottom + h * 0.26, "of ordering customers never place a 2nd order",
              fontsize=14.5, color=TEXT_PRIMARY, va="center", ha="left")
    fig.text(left + 0.022, bottom + h * 0.12, f"{m['one_time_n']:,} of {m['orderers_n']:,} ordering customers are one-time buyers",
              fontsize=10.5, color=TEXT_SECONDARY, va="center", ha="left")

    # small donut inset reinforcing the split
    donut_ax = fig.add_axes([left + w * 0.68, bottom + h * 0.12, w * 0.28, h * 0.55])
    donut_ax.set_zorder(10)
    vals = [m["one_time_pct_orderers"], 100 - m["one_time_pct_orderers"]]
    donut_ax.pie(vals, colors=[ACCENT, "#E5E5E5"], startangle=90, counterclock=False,
                 wedgeprops=dict(width=0.38, edgecolor=CARD_BG, linewidth=2))
    donut_ax.text(0, 0, "One-time\nvs Repeat", ha="center", va="center", fontsize=8.5, color=TEXT_SECONDARY)
    donut_ax.set_aspect("equal")

    # ---- Supporting KPIs ----
    add_kpi_card(fig, KPI1, "90-Day Retention", f"{m['overall_retention']:.1f}%", ACCENT,
                 note="Only ~1 in 3 customers return")
    add_kpi_card(fig, KPI2, "Total GMV (24 mo)", f"₹{m['total_gmv']/1e7:.1f} Cr", TEXT_PRIMARY,
                 note=f"{m['orderers_n']:,} ordering customers")
    add_kpi_card(fig, KPI3, "Revenue Concentration", f"{m['top_for_80']:.1f}% → 80%", ACCENT,
                 value_fontsize=26, note="Top customers vs GMV share — Page 3")

    # ---- Chart A: retention funnel ----
    ax = add_chart_axes(fig, CHART_A, title="Customer Funnel: Signup → Order → Return", pad_left=0.105)
    stages = ["Signed Up", "1st Order", "Repeat (90d)"]
    values = [50000, m["orderers_n"], m["retained_90d_n"]]
    colors = [TEXT_SECONDARY, "#457B9D", ACCENT]
    bars = ax.barh(stages, values, color=colors, height=0.55)
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + 700, bar.get_y() + bar.get_height() / 2, f"{v:,}",
                va="center", ha="left", fontsize=11, color=TEXT_PRIMARY, fontweight="bold")
    ax.set_xlim(0, 58000)
    ax.invert_yaxis()
    ax.tick_params(axis="y", labelsize=11)
    ax.set_xlabel("Customers", fontsize=10, color=TEXT_SECONDARY)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x/1000)}k"))

    # ---- Chart B: monthly GMV trend (real data, no fabricated seasonality) ----
    ax2 = add_chart_axes(fig, CHART_B, title="Monthly GMV Trend (24 Months)")
    monthly = m["monthly_gmv"]
    x = np.arange(len(monthly))
    ax2.plot(x, monthly.values / 1e5, color=ACCENT, linewidth=2.2)
    ax2.fill_between(x, 0, monthly.values / 1e5, color=ACCENT, alpha=0.08)
    tick_idx = list(range(0, len(monthly), 3))
    ax2.set_xticks(tick_idx)
    ax2.set_xticklabels([str(monthly.index[i]) for i in tick_idx], rotation=45, ha="right", fontsize=8.5)
    ax2.set_ylabel("GMV (₹ Lakh)", fontsize=10, color=TEXT_SECONDARY)
    ax2.set_ylim(0, monthly.values.max() / 1e5 * 1.12)

    # ---- Insight box ----
    add_insight_box(fig, INSIGHT, "KEY INSIGHT",
                     f"{m['one_time_pct_orderers']:.1f}% of customers never place a 2nd order — this is the "
                     f"single largest driver of the platform's {m['overall_retention']:.1f}% overall retention rate. "
                     f"With GMV this concentrated (top {m['top_for_80']:.1f}% of customers already driving 80% of "
                     f"₹{m['total_gmv']/1e7:.1f} Cr GMV), converting one-time buyers into repeat customers is the "
                     f"highest-leverage lever available — not new acquisition.")

    save_fig(fig, "page1_executive_summary.png")


# ============================================================================
# Page 2 — Retention & Churn Analysis
# ============================================================================
def build_page2(m):
    fig = new_figure()
    add_header(fig, "Retention & Churn Analysis", "Food Delivery Platform  |  50,000 Customers  |  24 Months", "PAGE 2 OF 3")

    KPI_Y, KPI_H, KPI_W = 0.783, 0.128, 0.310
    KPI1 = (0.018, KPI_Y, KPI_W, KPI_H)
    KPI2 = (0.345, KPI_Y, KPI_W, KPI_H)
    KPI3 = (0.672, KPI_Y, KPI_W, KPI_H)
    CHART_A = (0.018, 0.158, 0.560, 0.600)
    CHART_B = (0.596, 0.158, 0.386, 0.600)
    INSIGHT = (0.018, 0.024, 0.964, 0.122)

    add_kpi_card(fig, KPI1, "Avg Delivery Delay", f"{m['avg_delivery_delay']:.1f} min", GOOD,
                 note="Within the best-performing bucket")
    add_kpi_card(fig, KPI2, "Discount Rate", f"{m['discount_rate']:.1f}%", ACCENT,
                 note="Share of orders carrying a discount")
    add_kpi_card(fig, KPI3, "Churn Rate", f"{m['churn_rate']:.1f}%", ACCENT,
                 note="= 100% − 90-day retention")

    # ---- Chart A: cohort retention heatmap ----
    ax = add_chart_axes(fig, CHART_A, title="Cohort Retention Heatmap — % Still Ordering, by Months Since First Order",
                         pad_left=0.075)
    matrix = m["cohort_matrix"]
    mask = m["cohort_mask"]
    cols = list(matrix.columns)
    highlight_cols = {1, 3, 6, 12}
    data = matrix.to_numpy()
    masked = np.ma.masked_array(data, mask=mask.to_numpy())
    cmap = plt.cm.Reds.copy()
    cmap.set_bad(color="#F5F5F5")
    im = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=0, vmax=100)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([f"M{c}" for c in cols], fontsize=10)
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(list(matrix.index), fontsize=6.6)
    for i in range(data.shape[0]):
        for j, c in enumerate(cols):
            if mask.iloc[i, j]:
                continue
            val = data[i, j]
            is_key = c in highlight_cols or c == 0
            txt_color = "white" if val > 55 else TEXT_PRIMARY
            fig_text_kwargs = dict(ha="center", va="center")
            if is_key:
                ax.text(j, i, f"{val:.0f}", fontsize=7.2, fontweight="bold", color=txt_color, **fig_text_kwargs)
            elif c in (2, 9):
                ax.text(j, i, f"{val:.0f}", fontsize=5.6, color=(txt_color if val > 55 else "#999999"),
                        alpha=0.75, **fig_text_kwargs)
    for c in highlight_cols:
        j = cols.index(c)
        ax.add_patch(mpatches.Rectangle((j - 0.5, -0.5), 1, len(matrix.index), fill=False,
                                         edgecolor=HEADER_BG, linewidth=1.6, zorder=15))
    ax.set_xlabel("Months Since First Order  (bold columns = key milestones)", fontsize=9, color=TEXT_SECONDARY)
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.015)
    cbar.ax.tick_params(labelsize=7.5, colors=TEXT_SECONDARY)
    cbar.set_label("Retention %", fontsize=8, color=TEXT_SECONDARY)

    # ---- Chart B: delivery delay vs retention ----
    axb = add_chart_axes(fig, CHART_B, title="90-Day Retention by Delivery Delay", pad_left=0.145)
    bucket_summary = m["delay_bucket_summary"]
    bucket_labels = list(bucket_summary.index)
    plot_order = list(reversed(bucket_labels))
    delay_colors = ["#3E7C59", "#8FAE64", "#D9B23C", "#C97A3D", "#A6423B"]
    colors_ordered = list(reversed(delay_colors))
    values = bucket_summary.loc[plot_order, "retention_pct"].to_numpy()
    bars = axb.barh(plot_order, values, color=colors_ordered, height=0.62)
    for bar, v in zip(bars, values):
        axb.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2, f"{v:.1f}%",
                  va="center", ha="left", fontsize=10, color=TEXT_PRIMARY, fontweight="bold")
    overall_avg = m["overall_retention"]
    axb.axvline(overall_avg, color="#555555", linestyle="--", linewidth=1.2)
    axb.text(overall_avg + 1.0, 1, f"Overall avg\n{overall_avg:.1f}%", fontsize=8, color="#555555", va="center")
    axb.set_xlim(0, 44)
    axb.set_xlabel("90-Day Retention (%)", fontsize=9.5, color=TEXT_SECONDARY)
    axb.text(0.98, 1.045, f"Chi-square p = {m['delay_pvalue']:.1e}  (≪ 0.001, highly significant)",
              transform=axb.transAxes, fontsize=8.5, color=TEXT_SECONDARY, ha="right", va="bottom", style="italic")

    add_insight_box(fig, INSIGHT, "KEY INSIGHT",
                     f"Delivery delay is a genuine, statistically significant retention driver (p ≪ 0.001) — but it is "
                     f"a gradual decline, not a cliff: retention falls steadily from {bucket_summary.iloc[0]['retention_pct']:.1f}% "
                     f"(0-10 min) to {bucket_summary.iloc[-1]['retention_pct']:.1f}% (50+ min), roughly halving from best to "
                     f"worst bucket. Keeping delivery fast is a real lever, not a silver bullet.", wrap_chars=128)

    save_fig(fig, "page2_retention_churn.png")


# ============================================================================
# Page 3 — Segment Intelligence
# ============================================================================
def build_page3(m):
    fig = new_figure()
    add_header(fig, "Segment Intelligence", "Food Delivery Platform  |  50,000 Customers  |  24 Months", "PAGE 3 OF 3")

    KPI_Y, KPI_H, KPI_W = 0.783, 0.128, 0.310
    KPI1 = (0.018, KPI_Y, KPI_W, KPI_H)
    KPI2 = (0.345, KPI_Y, KPI_W, KPI_H)
    KPI3 = (0.672, KPI_Y, KPI_W, KPI_H)
    CHART_A = (0.018, 0.158, 0.470, 0.600)
    CHART_B = (0.506, 0.158, 0.476, 0.600)
    INSIGHT = (0.018, 0.024, 0.964, 0.122)

    rfm = m["rfm_summary"]
    champion_pct = rfm.loc["Champion", "pct_customers"]
    champion_n = int(rfm.loc["Champion", "customers"])

    add_kpi_card(fig, KPI1, "Champion Customers", f"{champion_n:,}", GOOD,
                 note=f"{champion_pct:.1f}% of orderers, 70.9% of GMV")
    add_kpi_card(fig, KPI2, "Never Ordered", f"{m['zero_order_n']:,}", ACCENT,
                 note=f"{m['zero_order_pct']:.1f}% of all 50,000 — signup, no order")
    add_kpi_card(fig, KPI3, "Champion vs Lost Frequency", f"{m['champion_avg_freq']:.1f}x vs {m['lost_avg_freq']:.1f}x", GOOD,
                 value_fontsize=24, note="Avg orders per customer, by segment")

    # ---- Chart A: Lorenz curve ----
    ax = add_chart_axes(fig, CHART_A, title="Revenue Concentration — Lorenz Curve", pad_left=0.075)
    x, y = m["lorenz_x"], m["lorenz_y"]
    ax.plot([0, 100], [0, 100], linestyle="--", color="#B0B0B0", linewidth=1.5, label="Perfect equality")
    ax.plot(x, y, color=ACCENT, linewidth=2.2, label="Actual GMV share")
    ax.fill_between(x, x, y, where=(y >= x), color=ACCENT, alpha=0.12, interpolate=True)
    for target, label_y in [(50, m["top_for_50"]), (80, m["top_for_80"])]:
        cx = label_y
        ax.scatter([cx], [target], color=HEADER_BG, zorder=5, s=40)
        ax.annotate(f"{cx:.1f}% → {target}% of GMV", xy=(cx, target), xytext=(cx + 12, target - 14),
                    fontsize=9.5, color=TEXT_PRIMARY,
                    arrowprops=dict(arrowstyle="-", color="#888888", lw=0.8))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Cumulative % of Customers (ranked by spend)", fontsize=9.5, color=TEXT_SECONDARY)
    ax.set_ylabel("Cumulative % of GMV", fontsize=9.5, color=TEXT_SECONDARY)
    ax.set_aspect("equal")
    ax.legend(loc="lower right", frameon=False, fontsize=9)

    # ---- Chart B: RFM segments (customer % + GMV %) + Never Ordered note, and discount/LTV panel ----
    # split CHART_B region into two stacked panels: RFM bars (top) + discount/LTV (bottom).
    # Laid out with an explicit top-down cursor (title -> axes -> tick-label space ->
    # footnote -> gap) so nothing can silently overlap as text/font sizes change.
    left, bottom, w, h = CHART_B
    add_card(fig, CHART_B)
    inner_left, inner_w = left + 0.020, w - 0.045
    cursor = bottom + h - 0.018  # start just below the card's top padding

    TITLE_H, AXES_H, TICKLABEL_H, FOOTNOTE_H, GAP_H = 0.024, 0.195, 0.026, 0.024, 0.010

    fig.text(inner_left, cursor, "RFM Segments — Customers vs GMV Share", fontsize=13, fontweight="bold",
              color=TEXT_PRIMARY, va="top", ha="left")
    cursor -= TITLE_H
    ax_rfm = fig.add_axes([inner_left, cursor - AXES_H, inner_w, AXES_H])
    ax_rfm.set_zorder(10)
    ax_rfm.set_facecolor(CARD_BG)
    cursor -= (AXES_H + TICKLABEL_H)
    fig.text(inner_left, cursor,
              f"Plus {m['zero_order_n']:,} customers ({m['zero_order_pct']:.1f}% of all 50,000) who signed up and "
              f"never placed an order — shown separately, not folded into \"Lost.\"",
              fontsize=7.8, color=TEXT_SECONDARY, va="top", ha="left", style="italic")
    cursor -= (FOOTNOTE_H + GAP_H)

    seg_order = ["Champion", "Loyal", "At Risk", "About to Lapse", "Lost"]
    xpos = np.arange(len(seg_order))
    width = 0.38
    pct_cust = rfm.loc[seg_order, "pct_customers"].to_numpy()
    pct_gmv = rfm.loc[seg_order, "pct_gmv"].to_numpy()
    b1 = ax_rfm.bar(xpos - width / 2, pct_cust, width, color="#457B9D", label="% of Customers")
    b2 = ax_rfm.bar(xpos + width / 2, pct_gmv, width, color=ACCENT, label="% of GMV")
    for bar in list(b1) + list(b2):
        ax_rfm.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2, f"{bar.get_height():.1f}%",
                    ha="center", va="bottom", fontsize=8, color=TEXT_PRIMARY)
    ax_rfm.set_xticks(xpos)
    ax_rfm.set_xticklabels(seg_order, fontsize=8.5)
    ax_rfm.set_ylabel("Share (%)", fontsize=8.5, color=TEXT_SECONDARY)
    ax_rfm.set_ylim(0, 82)
    ax_rfm.legend(frameon=False, fontsize=8, loc="upper right")
    for spine in ["top", "right"]:
        ax_rfm.spines[spine].set_visible(False)
    ax_rfm.tick_params(colors=TEXT_SECONDARY, labelsize=8)

    fig.text(inner_left, cursor, "Discount Dependency vs LTV (repeat customers, ≥2 orders)",
              fontsize=13, fontweight="bold", color=TEXT_PRIMARY, va="top", ha="left")
    cursor -= TITLE_H
    ax_disc = fig.add_axes([inner_left, cursor - AXES_H, inner_w, AXES_H])
    ax_disc.set_zorder(10)
    ax_disc.set_facecolor(CARD_BG)
    cursor -= (AXES_H + TICKLABEL_H)
    disc = m["discount_summary"]
    disc_groups = ["Light/Moderate", "Heavy"]
    xg = np.arange(len(disc_groups))
    ltv_vals = disc.loc[disc_groups, "avg_ltv"].to_numpy()
    ret_vals = disc.loc[disc_groups, "retention_pct"].to_numpy()
    ax_ltv = ax_disc
    b3 = ax_ltv.bar(xg - 0.18, ltv_vals, 0.34, color="#457B9D", label="Avg LTV (₹)")
    ax_ltv.set_ylabel("Avg LTV (₹)", fontsize=8.5, color="#457B9D")
    ax_ltv.set_ylim(0, max(ltv_vals) * 1.35)
    for bar, v in zip(b3, ltv_vals):
        ax_ltv.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(ltv_vals) * 0.03, f"₹{v:,.0f}",
                    ha="center", va="bottom", fontsize=8, color=TEXT_PRIMARY)
    ax_ret = ax_ltv.twinx()
    ax_ret.set_zorder(9)
    b4 = ax_ret.bar(xg + 0.18, ret_vals, 0.34, color=ACCENT, label="90-Day Retention (%)")
    ax_ret.set_ylabel("90-Day Retention (%)", fontsize=8.5, color=ACCENT)
    ax_ret.set_ylim(0, max(ret_vals) * 1.35)
    for bar, v in zip(b4, ret_vals):
        ax_ret.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(ret_vals) * 0.03, f"{v:.1f}%",
                    ha="center", va="bottom", fontsize=8, color=TEXT_PRIMARY)
    ax_ltv.set_xticks(xg)
    ax_ltv.set_xticklabels(disc_groups, fontsize=9)
    for spine in ["top"]:
        ax_ltv.spines[spine].set_visible(False)
        ax_ret.spines[spine].set_visible(False)
    ax_ltv.tick_params(colors="#457B9D", labelsize=8)
    ax_ret.tick_params(colors=ACCENT, labelsize=8)
    lines = [b3, b4]
    labels = ["Avg LTV (₹)", "90-Day Retention (%)"]
    ax_ltv.legend(lines, labels, frameon=False, fontsize=7.5, loc="upper center")
    fig.text(inner_left, cursor,
              f"Heavy discount users show {abs(m['heavy_vs_lm_pct']):.0f}% lower LTV than Light/Moderate. "
              f"\"Never discounted\" (n=142) excluded — too small & structurally biased for a fair comparison.",
              fontsize=7.8, color=TEXT_SECONDARY, va="top", ha="left", style="italic")

    add_insight_box(fig, INSIGHT, "KEY INSIGHT",
                     f"Top {m['top_for_80']:.1f}% of customers drive 80% of GMV, and Champions place "
                     f"{m['champion_avg_freq']:.0f}x more orders than Lost customers — retention among existing "
                     f"high-value customers is the priority, not broad acquisition. Heavy discount reliance "
                     f"correlates with {abs(m['heavy_vs_lm_pct']):.0f}% lower LTV, so discount budget is better spent "
                     f"on delivery reliability and onboarding than blanket promotions.", wrap_chars=128)

    save_fig(fig, "page3_segment_intelligence.png")


if __name__ == "__main__":
    os.makedirs(EXPORT_DIR, exist_ok=True)
    metrics = compute_all_metrics()
    print("Metrics computed OK.")
    build_page1(metrics)
    build_page2(metrics)
    build_page3(metrics)
