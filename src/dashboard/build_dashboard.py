"""
Generates summary visualizations from the DynamoDB-exported inventory data
(data/processed/inventory_current_state.csv), simulating the kind of
dashboard a BI tool (Tableau/Power BI/QuickSight) would build on top of the
DynamoDB table in production.

Run: python3 src/dashboard/build_dashboard.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "inventory_current_state.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "report", "figures")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    df["is_low_stock"] = df["is_low_stock"].astype(str).str.lower() == "true"
    df["inventory_value"] = df["current_stock"] * df["unit_cost"]

    # --- Chart 1: Low-stock SKU count by warehouse ---
    low_stock_by_wh = df[df["is_low_stock"]].groupby("warehouse_id").size()
    fig, ax = plt.subplots(figsize=(8, 5))
    low_stock_by_wh.plot(kind="bar", ax=ax, color="tomato")
    ax.set_title("Low-Stock SKU Count by Warehouse")
    ax.set_xlabel("Warehouse")
    ax.set_ylabel("Number of SKUs at/below reorder threshold")
    plt.xticks(rotation=0)
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "low_stock_by_warehouse.png"))
    plt.close(fig)

    # --- Chart 2: Inventory value by category ---
    value_by_category = df.groupby("category")["inventory_value"].sum().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(9, 5))
    value_by_category.plot(kind="bar", ax=ax, color="steelblue")
    ax.set_title("Total Inventory Value by Category")
    ax.set_xlabel("Category")
    ax.set_ylabel("Inventory Value ($)")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "inventory_value_by_category.png"))
    plt.close(fig)

    # --- Chart 3: Stock level distribution vs reorder threshold ---
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(df["reorder_threshold"], df["current_stock"],
               c=df["is_low_stock"].map({True: "tomato", False: "steelblue"}),
               alpha=0.6, s=15)
    max_val = max(df["reorder_threshold"].max(), df["current_stock"].max())
    ax.plot([0, max_val], [0, max_val], "k--", alpha=0.3, label="stock == threshold")
    ax.set_title("Current Stock vs. Reorder Threshold (red = low stock)")
    ax.set_xlabel("Reorder Threshold")
    ax.set_ylabel("Current Stock")
    ax.legend()
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "stock_vs_threshold.png"))
    plt.close(fig)

    # --- Summary stats printed to console + saved ---
    summary_lines = [
        f"Total SKUs tracked: {len(df)}",
        f"SKUs at/below reorder threshold: {df['is_low_stock'].sum()} ({100 * df['is_low_stock'].mean():.1f}%)",
        f"Total inventory value: ${df['inventory_value'].sum():,.2f}",
        f"Warehouses: {df['warehouse_id'].nunique()}",
        f"Categories: {df['category'].nunique()}",
    ]
    print("\n".join(summary_lines))

    with open(os.path.join(os.path.dirname(OUTPUT_DIR), "dashboard_summary.txt"), "w") as f:
        f.write("\n".join(summary_lines))

    print(f"\nSaved 3 charts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
