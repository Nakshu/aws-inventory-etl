# AWS Inventory ETL & Low-Stock Alerting Pipeline

An event-driven inventory pipeline built on AWS S3, Lambda, DynamoDB, and
SNS. Simulates a real warehouse system: a daily inventory snapshot lands in
S3, triggers a Lambda that cleans and validates it, writes current state to
DynamoDB, and fires an alert for any SKU at or below its reorder threshold.

Fully testable locally with zero AWS cost using `moto` to mock every AWS
service the Lambda touches — the whole pipeline is proven correct without
needing an AWS account.

## 1. Problem

A warehouse/inventory team needs an automated way to process daily stock
snapshots: validate the data, maintain a queryable current-state table, and
get alerted immediately when something needs to be reordered — without a
human manually checking a spreadsheet every day.

## 2. Approach

| Stage | AWS Service | What it does |
|---|---|---|
| Ingestion | S3 | Raw inventory CSV lands in an "incoming" bucket |
| Trigger | S3 Event Notification | Fires the Lambda automatically on every new file |
| Processing | Lambda | Parses, validates, and cleans the CSV; logs a data-quality report |
| Current state | DynamoDB | One item per SKU, upserted on every run |
| Alerting | SNS | Publishes a low-stock alert message/email for SKUs at or below threshold |
| Reporting | matplotlib (local) / QuickSight, Tableau, Power BI (production) | Dashboards on top of the DynamoDB export |

## 3. Repo Structure

```
aws-inventory-etl/
├── data/
│   └── generate_synthetic_inventory_data.py   # Creates data/raw/inventory_snapshot.csv
├── src/
│   ├── lambda/
│   │   └── lambda_function.py                 # Core Lambda: parse/clean/write/alert
│   └── dashboard/
│       └── build_dashboard.py                 # Builds summary charts from DynamoDB export
├── tests/
│   └── test_lambda_local.py                   # Full pipeline test using moto (no AWS account needed)
├── infra/
│   ├── README.md                              # Real AWS deployment steps (optional)
│   └── s3-notification-config.json            # S3 -> Lambda trigger config template
├── architecture/
│   └── pipeline_diagram.md
└── README.md
```

## 4. How to Run (Local, No AWS Account Needed)

```bash
pip install boto3 moto pandas matplotlib

# 1. Generate synthetic inventory data
python3 data/generate_synthetic_inventory_data.py

# 2. Run the full pipeline against mocked AWS services (S3, DynamoDB, SNS)
python3 tests/test_lambda_local.py

# 3. Build the dashboard charts from the DynamoDB export
python3 src/dashboard/build_dashboard.py
```

Step 2 uploads the synthetic CSV to a mocked S3 bucket, invokes the actual
Lambda handler function against it, writes results to a mocked DynamoDB
table, and verifies the data landed correctly — proving the pipeline logic
end-to-end.

## 5. Deploying to Real AWS (Optional)

See `infra/README.md` for the full AWS CLI deployment walkthrough. Designed
to stay within the AWS Free Tier for demo/portfolio use.

## 6. Results

**Test run (808 synthetic SKUs, 4 warehouses):**

| Metric | Value |
|---|---|
| Total rows in source file | 808 |
| Dropped — missing required fields | 4 |
| Dropped — invalid/negative stock | 12 |
| Dropped — duplicate SKU | 7 |
| Clean rows written to DynamoDB | 785 |
| Low-stock alerts triggered | 132 (16.8% of SKUs) |
| Total inventory value tracked | $28,079,529.87 |

**Pipeline verification:** all assertions passed — DynamoDB item count
matches the Lambda's reported write count, and low-stock alert count matches
the flagged items in the data, confirming the full S3 → Lambda → DynamoDB →
SNS flow behaves correctly.

## 7. Why This Project

Built to demonstrate AWS service integration (S3, Lambda, DynamoDB, SNS) and
event-driven ETL design — the kind of architecture used for real-time or
near-real-time data pipelines, as opposed to the batch/warehouse-style
pipeline in the companion credit-card-transaction-pipeline project. Testing
via `moto` also demonstrates a production-realistic practice: proving Lambda
logic correct in CI/local dev before ever deploying to a real AWS account.
