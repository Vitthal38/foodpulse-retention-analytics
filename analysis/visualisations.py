"""
FoodPulse — Publication-quality charts
Reads the CSVs in analysis/results/ and produces 4 charts (150 DPI PNG) into
analysis/charts/, using only seaborn and matplotlib.

Run:
    python analysis/visualisations.py
"""

import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT_DIR, "analysis", "results")
CHARTS_DIR = os.path.join(ROOT_DIR, "analysis", "charts")

DPI = 150

# clean, minimal, professional look
sns.set_theme(style="white", font="DejaVu Sans")
plt.rcParams.update({
    "axes.edgecolor": "#4d4d4d",
    "axes.labelcolor": "#333333",
    "text.color": "#333333",
    "xtick.color": "#4d4d4d",
    "ytick.color": "#4d4d4d",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})

MUTED_GREEN_TO_RED = ["#3E7C59", "#8FAE64", "#D9B23C", "#C97A3D", "#A6423B"]
STEEL_BLUE = "#4C72A8"
CORAL = "#D97B4F"
DARK_BLUE = "#1F4E79"
LIGHT_GREY = "#B0B0B0"


def ensure_charts_dir():
    os.makedirs(CHARTS_DIR, exist_ok=True)


def save(fig, filename):
    path = os.path.join(CHARTS_DIR, filename)
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
# Chart 1 — Cohort retention heatmap
# --------------------------------------------------------------------------
def chart_cohort_retention_heatmap():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "cohort_retention.csv"))

    month_order = [0, 1, 2, 3, 6, 9, 12]
    pivot = df.pivot(index="cohort_month", columns="months_since_first", values="retention_pct")
    pivot = pivot.reindex(columns=month_order)
    pivot = pivot.sort_index()

    # mask cells that haven't had time to occur yet (beyond the data horizon),
    # so "not observed" is never rendered as if it were "0% retention"
    data_horizon = pd.Period(pivot.index.max(), freq="M")
    mask = pd.DataFrame(False, index=pivot.index, columns=pivot.columns)
    for cohort_month in pivot.index:
        cohort_period = pd.Period(cohort_month, freq="M")
        for month_offset in pivot.columns:
            if cohort_period + month_offset > data_horizon:
                mask.loc[cohort_month, month_offset] = True

    fig, ax = plt.subplots(figsize=(14, 8))
    sns.heatmap(
        pivot, mask=mask, annot=True, fmt=".0f", cmap="Blues", vmin=0, vmax=100,
        linewidths=0.5, linecolor="white", cbar_kws={"label": "Retention %"},
        annot_kws={"size": 8}, ax=ax,
    )
    ax.set_title("Customer Cohort Retention — % Still Ordering by Month", fontsize=15, fontweight="bold", pad=16)
    ax.set_xlabel("Months Since First Order", fontsize=11)
    ax.set_ylabel("Acquisition Cohort (Month)", fontsize=11)
    ax.tick_params(left=False, bottom=False)

    fig.text(
        0.01, -0.02, "Each row = customers who placed their first order in that month",
        fontsize=9, style="italic", color="#666666",
    )

    save(fig, "cohort_retention_heatmap.png")
    print("Chart 1 saved: cohort_retention_heatmap.png")


# --------------------------------------------------------------------------
# Chart 2 — Delivery delay vs 90-day retention
# --------------------------------------------------------------------------
def chart_delivery_delay_churn():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "delay_churn.csv"))

    bucket_order = ["0-10 min", "10-20 min", "20-35 min", "35-50 min", "50+ min"]
    df["delay_bucket"] = pd.Categorical(df["delay_bucket"], categories=bucket_order, ordered=True)
    df = df.sort_values("delay_bucket")

    overall_avg = 100.0 * df["retained_customers"].sum() / df["total_customers"].sum()

    fig, ax = plt.subplots(figsize=(10, 5))
    # top-to-bottom = best-to-worst delay bucket
    plot_order = list(reversed(bucket_order))
    colors = list(reversed(MUTED_GREEN_TO_RED))
    bars = ax.barh(plot_order, df.set_index("delay_bucket").loc[plot_order, "retention_rate_pct"], color=colors)

    for bar, value in zip(bars, df.set_index("delay_bucket").loc[plot_order, "retention_rate_pct"]):
        ax.text(bar.get_width() + 0.6, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%",
                va="center", ha="left", fontsize=10, color="#333333")

    ax.axvline(overall_avg, color="#555555", linestyle="--", linewidth=1.2)
    ax.text(overall_avg + 0.6, 1, f"Overall avg: {overall_avg:.1f}%",
            fontsize=9, color="#555555", va="center", ha="left")

    ax.set_xlim(0, 40)
    ax.set_xlabel("90-Day Retention Rate (%)", fontsize=11)
    ax.set_ylabel("")
    ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle("90-Day Retention Rate by Delivery Delay Bucket", fontsize=15, fontweight="bold", y=1.02)
    ax.set_title("Customers with delays above 35 minutes show near-total churn", fontsize=10, color="#666666", pad=10)

    save(fig, "delivery_delay_churn.png")
    print("Chart 2 saved: delivery_delay_churn.png")


# --------------------------------------------------------------------------
# Chart 3 — Revenue Lorenz curve (Pareto)
# --------------------------------------------------------------------------
def chart_revenue_lorenz_curve():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "revenue_pareto.csv"))

    detail = df[df["row_type"] == "detail"].sort_values("rnk")
    milestones = df[df["row_type"] == "milestone"].sort_values("cumulative_gmv_pct")

    x = detail["cumulative_customer_pct"].to_numpy()
    y = detail["cumulative_gmv_pct"].to_numpy()

    fig, ax = plt.subplots(figsize=(8, 8))

    ax.plot([0, 100], [0, 100], linestyle="--", color=LIGHT_GREY, linewidth=1.5, label="Perfect equality")
    ax.plot(x, y, color=DARK_BLUE, linewidth=2.2, label="Actual revenue share")
    ax.fill_between(x, x, y, where=(y >= x), color="#A9C6E8", alpha=0.35, interpolate=True)

    # milestone markers, pulled from the query's own milestone rows (not hardcoded) —
    # only the 50% and 80% call-outs are annotated, per spec
    for _, row in milestones.iterrows():
        target_pct = row["cumulative_gmv_pct"]
        if target_pct not in (50, 80):
            continue
        cx, cy = row["cumulative_customer_pct"], target_pct
        ax.scatter([cx], [cy], color="#A6423B", zorder=5, s=45)
        label = f"Top {cx:.1f}% → {int(cy)}% of GMV"
        ax.annotate(
            label, xy=(cx, cy), xytext=(cx + 12, cy - 12),
            fontsize=9.5, color="#333333",
            arrowprops=dict(arrowstyle="-", color="#888888", lw=0.8),
        )

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Cumulative % of Customers (ranked by spend, highest first)", fontsize=10)
    ax.set_ylabel("Cumulative % of GMV", fontsize=10)
    ax.set_aspect("equal")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right", frameon=False, fontsize=9)

    fig.suptitle("Revenue Concentration — Lorenz Curve", fontsize=15, fontweight="bold", y=0.97)
    ax.set_title("A small customer segment drives the majority of revenue", fontsize=10, color="#666666", pad=10)

    save(fig, "revenue_lorenz_curve.png")
    print("Chart 3 saved: revenue_lorenz_curve.png")


# --------------------------------------------------------------------------
# Chart 4 — RFM segment distribution
# --------------------------------------------------------------------------
def chart_rfm_segments():
    df = pd.read_csv(os.path.join(RESULTS_DIR, "rfm_segments.csv"))

    segment_order = ["Champion", "Loyal", "At Risk", "About to Lapse", "Lost"]
    total_customers = len(df)
    total_gmv = df["total_spend"].sum()

    summary = (
        df.groupby("segment")
        .agg(customer_count=("customer_id", "count"), segment_gmv=("total_spend", "sum"))
        .reindex(segment_order)
    )
    summary["pct_customers"] = 100.0 * summary["customer_count"] / total_customers
    summary["pct_gmv"] = 100.0 * summary["segment_gmv"] / total_gmv

    x = range(len(segment_order))
    width = 0.38

    fig, ax = plt.subplots(figsize=(12, 6))
    bars_customers = ax.bar([i - width / 2 for i in x], summary["pct_customers"], width,
                             color=STEEL_BLUE, label="% of Total Customers")
    bars_gmv = ax.bar([i + width / 2 for i in x], summary["pct_gmv"], width,
                       color=CORAL, label="% of Total GMV")

    for bar in list(bars_customers) + list(bars_gmv):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height + 0.6, f"{height:.1f}%",
                ha="center", va="bottom", fontsize=9.5, color="#333333")

    ax.set_xticks(list(x))
    ax.set_xticklabels(segment_order, fontsize=11)
    ax.set_ylabel("Share (%)", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=10, loc="upper right")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100))

    fig.suptitle("RFM Segment — Customer Count vs Revenue Contribution", fontsize=15, fontweight="bold", y=1.02)
    ax.set_title("Champions are few but drive outsized revenue", fontsize=10, color="#666666", pad=10)

    save(fig, "rfm_segments.png")
    print("Chart 4 saved: rfm_segments.png")


def main():
    ensure_charts_dir()
    chart_cohort_retention_heatmap()
    chart_delivery_delay_churn()
    chart_revenue_lorenz_curve()
    chart_rfm_segments()
    print("All charts saved to analysis/charts/")


if __name__ == "__main__":
    main()
