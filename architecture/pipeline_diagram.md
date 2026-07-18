# Pipeline Architecture

```
┌───────────────────────────────┐
│  Synthetic Inventory Generator  │   808 SKUs across 4 warehouses,
│  (data/generate_synthetic_      │   intentional data-quality issues
│   inventory_data.py)            │
└────────────────┬─────────────────┘
                 │  CSV upload
                 ▼
┌───────────────────────────────┐
│  S3 "incoming" bucket           │   Triggers Lambda on ObjectCreated
└────────────────┬─────────────────┘
                 │  S3 event
                 ▼
┌───────────────────────────────┐
│  AWS Lambda                     │   Parse, validate, clean;
│  (src/lambda/lambda_function.py)│   log data-quality report
└────────────────┬─────────────────┘
                 │
        ┌────────┴────────┐
        ▼                    ▼
┌───────────────┐   ┌───────────────────┐
│  DynamoDB       │   │  SNS Topic          │
│  (current        │   │  (low-stock          │
│   inventory       │   │   email alerts)      │
│   state, one       │   └───────────────────┘
│   item per SKU)    │
└────────┬──────────┘
        │  export / BI connector
        ▼
┌───────────────────────────────┐
│  Dashboard                      │   Low-stock by warehouse,
│  (src/dashboard/                │   inventory value by category,
│   build_dashboard.py)           │   stock vs. threshold scatter
└───────────────────────────────┘

  Local testing (no AWS account/cost needed):
  tests/test_lambda_local.py uses `moto` to mock S3 + DynamoDB + SNS
  and invokes lambda_handler() directly, proving the full pipeline
  logic end-to-end.

  Real deployment (optional): see infra/README.md for AWS CLI steps.
```
