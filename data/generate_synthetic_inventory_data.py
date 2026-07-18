"""
Generates synthetic warehouse inventory snapshot data -- the kind of file
that would land in an S3 "incoming" bucket daily from a POS/warehouse system.

Includes intentional data-quality issues (nulls, negative stock, duplicate
SKU rows) so the Lambda transform has real issues to catch and log.

Output: data/raw/inventory_snapshot.csv
"""

import csv
import os
import random
import uuid
from datetime import datetime, timedelta

random.seed(7)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "raw")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "inventory_snapshot.csv")

WAREHOUSES = ["WH-EAST", "WH-WEST", "WH-CENTRAL", "WH-SOUTH"]
CATEGORIES = ["electronics", "apparel", "home_goods", "grocery", "toys", "sporting_goods"]

NUM_SKUS = 800


def generate_rows(num_skus: int):
    rows = []
    for i in range(num_skus):
        sku = f"SKU-{100000 + i}"
        category = random.choice(CATEGORIES)
        warehouse = random.choice(WAREHOUSES)

        reorder_threshold = random.randint(20, 100)
        # Skew some SKUs to be near/at/below threshold so alerting has real cases
        if random.random() < 0.15:
            current_stock = random.randint(0, reorder_threshold)
        else:
            current_stock = random.randint(reorder_threshold, reorder_threshold * 10)

        unit_cost = round(random.uniform(2, 250), 2)

        rows.append({
            "sku": sku,
            "warehouse_id": warehouse,
            "category": category,
            "current_stock": current_stock,
            "reorder_threshold": reorder_threshold,
            "unit_cost": unit_cost,
            "last_updated": (datetime.now() - timedelta(hours=random.randint(0, 48))).isoformat(),
        })

    # --- Inject data-quality issues ---
    # 1. Null current_stock (~1%)
    for row in random.sample(rows, k=int(num_skus * 0.01)):
        row["current_stock"] = ""

    # 2. Negative stock from a hypothetical sync glitch (~0.5%)
    for row in random.sample(rows, k=int(num_skus * 0.005)):
        row["current_stock"] = -abs(random.randint(1, 20))

    # 3. Duplicate SKU rows (~1%)
    duplicates = [dict(r) for r in random.sample(rows, k=int(num_skus * 0.01))]
    rows.extend(duplicates)

    # 4. Missing warehouse_id (~0.5%)
    for row in random.sample(rows, k=int(num_skus * 0.005)):
        row["warehouse_id"] = ""

    random.shuffle(rows)
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows = generate_rows(NUM_SKUS)

    fieldnames = [
        "sku", "warehouse_id", "category", "current_stock",
        "reorder_threshold", "unit_cost", "last_updated",
    ]

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} inventory rows across {len(WAREHOUSES)} warehouses")
    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
