"""
AWS Lambda function: triggered on S3 PutObject (a new inventory CSV landing
in the "incoming" bucket). Cleans and validates the file, writes clean
records to DynamoDB, and publishes an SNS alert for any SKU at or below its
reorder threshold.

This mirrors a real event-driven inventory pipeline:
  S3 (raw CSV upload) -> Lambda (validate/transform) -> DynamoDB (current
  state) -> SNS (low-stock alerts) -> downstream dashboard reads from DynamoDB

Deploy this as a real Lambda (see infra/README.md for the AWS CLI/SAM
deployment steps) or run it locally against mocked AWS services -- see
tests/test_lambda_local.py, which uses `moto` to mock S3/DynamoDB/SNS so the
whole pipeline can be proven correct without an AWS account or any cost.
"""

import csv
import io
import json
import os
from datetime import datetime, timezone

import boto3

DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "InventoryCurrentState")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")  # set by infra deployment
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")  # optional, for archiving cleaned files

REQUIRED_COLUMNS = [
    "sku", "warehouse_id", "category", "current_stock",
    "reorder_threshold", "unit_cost", "last_updated",
]


def parse_and_clean(csv_text: str):
    """
    Parses raw CSV text, validates each row, and returns (clean_rows,
    quality_report) where quality_report counts what was dropped and why --
    this is the data-quality logging layer, functionally similar in spirit
    to the Great Expectations checks in the credit-card-pipeline project,
    but implemented natively in the Lambda for a lightweight, dependency-free
    runtime (Lambda cold-start time matters in production).
    """
    reader = csv.DictReader(io.StringIO(csv_text))

    clean_rows = []
    seen_skus = set()
    quality_report = {
        "total_rows": 0,
        "dropped_missing_fields": 0,
        "dropped_invalid_stock": 0,
        "dropped_duplicate_sku": 0,
    }

    for row in reader:
        quality_report["total_rows"] += 1

        # Missing required fields
        if not row.get("sku") or not row.get("warehouse_id"):
            quality_report["dropped_missing_fields"] += 1
            continue

        # Invalid / missing stock value
        try:
            current_stock = int(row["current_stock"])
        except (ValueError, TypeError):
            quality_report["dropped_invalid_stock"] += 1
            continue

        if current_stock < 0:
            quality_report["dropped_invalid_stock"] += 1
            continue

        # Duplicate SKU (keep first occurrence)
        if row["sku"] in seen_skus:
            quality_report["dropped_duplicate_sku"] += 1
            continue
        seen_skus.add(row["sku"])

        reorder_threshold = int(row.get("reorder_threshold", 0) or 0)

        clean_rows.append({
            "sku": row["sku"],
            "warehouse_id": row["warehouse_id"],
            "category": row.get("category", "unknown"),
            "current_stock": current_stock,
            "reorder_threshold": reorder_threshold,
            "unit_cost": float(row.get("unit_cost", 0) or 0),
            "last_updated": row.get("last_updated", datetime.now(timezone.utc).isoformat()),
            "is_low_stock": current_stock <= reorder_threshold,
        })

    return clean_rows, quality_report


def write_to_dynamodb(rows, table_name: str, dynamodb_resource=None):
    dynamodb = dynamodb_resource or boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    with table.batch_writer() as batch:
        for row in rows:
            item = dict(row)
            item["unit_cost"] = str(item["unit_cost"])  # Decimal-safety for DynamoDB
            batch.put_item(Item=item)

    return len(rows)


def publish_low_stock_alert(low_stock_rows, topic_arn: str, sns_client=None):
    if not low_stock_rows or not topic_arn:
        return None

    sns = sns_client or boto3.client("sns")

    lines = [f"{r['sku']} ({r['warehouse_id']}): {r['current_stock']} units, threshold {r['reorder_threshold']}"
             for r in low_stock_rows[:20]]
    message = (
        f"LOW STOCK ALERT: {len(low_stock_rows)} SKU(s) at or below reorder threshold.\n\n"
        + "\n".join(lines)
    )
    if len(low_stock_rows) > 20:
        message += f"\n...and {len(low_stock_rows) - 20} more."

    response = sns.publish(
        TopicArn=topic_arn,
        Subject=f"Low Stock Alert: {len(low_stock_rows)} SKUs",
        Message=message,
    )
    return response


def lambda_handler(event, context):
    """
    Standard AWS Lambda entry point. Expects an S3 PutObject event.
    """
    s3 = boto3.client("s3")

    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]

    obj = s3.get_object(Bucket=bucket, Key=key)
    csv_text = obj["Body"].read().decode("utf-8")

    clean_rows, quality_report = parse_and_clean(csv_text)

    written_count = write_to_dynamodb(clean_rows, DYNAMODB_TABLE_NAME)

    low_stock_rows = [r for r in clean_rows if r["is_low_stock"]]
    if SNS_TOPIC_ARN:
        publish_low_stock_alert(low_stock_rows, SNS_TOPIC_ARN)

    result = {
        "source_file": f"s3://{bucket}/{key}",
        "quality_report": quality_report,
        "rows_written": written_count,
        "low_stock_alerts": len(low_stock_rows),
    }

    print(json.dumps(result, indent=2))

    return {
        "statusCode": 200,
        "body": json.dumps(result),
    }
