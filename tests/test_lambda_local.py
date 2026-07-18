"""
Local, cost-free test of the full pipeline using `moto` to mock S3,
DynamoDB, and SNS. This proves the Lambda function's logic is correct
without needing a real AWS account, credentials, or spending any money --
and it's exactly the kind of test AWS recommends before deploying a Lambda
for real.

Run: python3 tests/test_lambda_local.py
"""

import json
import os
import sys

import boto3
from moto import mock_aws

# boto3 requires a region and (dummy, since we're mocking) credentials to be
# set even when moto intercepts every real network call.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lambda"))
import lambda_function  # noqa: E402

RAW_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "inventory_snapshot.csv")

INCOMING_BUCKET = "test-inventory-incoming"
TABLE_NAME = "InventoryCurrentState"
TOPIC_NAME = "low-stock-alerts"
REGION = "us-east-1"


@mock_aws
def run_test():
    # --- Set up mocked AWS resources ---
    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=INCOMING_BUCKET)

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "sku", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "sku", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()

    sns = boto3.client("sns", region_name=REGION)
    topic = sns.create_topic(Name=TOPIC_NAME)
    topic_arn = topic["TopicArn"]

    # --- Point the Lambda module's env vars at our mocked resources ---
    os.environ["DYNAMODB_TABLE_NAME"] = TABLE_NAME
    os.environ["SNS_TOPIC_ARN"] = topic_arn

    # --- Upload the synthetic inventory CSV to the mocked "incoming" bucket ---
    with open(RAW_DATA_PATH, "r") as f:
        csv_content = f.read()

    object_key = "incoming/inventory_snapshot.csv"
    s3.put_object(Bucket=INCOMING_BUCKET, Key=object_key, Body=csv_content)

    # --- Build a realistic S3 event and invoke the Lambda handler directly ---
    fake_s3_event = {
        "Records": [{
            "s3": {
                "bucket": {"name": INCOMING_BUCKET},
                "object": {"key": object_key},
            }
        }]
    }

    print("=== Invoking Lambda handler locally against mocked AWS ===\n")
    response = lambda_function.lambda_handler(fake_s3_event, context=None)
    body = json.loads(response["body"])

    print("\n=== Lambda Response ===")
    print(json.dumps(body, indent=2))

    # --- Verify data actually landed in DynamoDB ---
    scan_result = table.scan()
    items = scan_result["Items"]

    print(f"\n=== Verification ===")
    print(f"Items in DynamoDB: {len(items)}")
    print(f"Rows written per Lambda response: {body['rows_written']}")
    assert len(items) == body["rows_written"], "Mismatch between DynamoDB scan and Lambda response!"

    low_stock_items = [i for i in items if i["is_low_stock"]]
    print(f"Low-stock items found: {len(low_stock_items)}")
    assert len(low_stock_items) == body["low_stock_alerts"], "Low-stock count mismatch!"

    print("\nAll assertions passed. Pipeline logic verified end-to-end.")

    # --- Export DynamoDB contents to CSV for the dashboard step ---
    export_path = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "inventory_current_state.csv")
    os.makedirs(os.path.dirname(export_path), exist_ok=True)

    import csv
    fieldnames = ["sku", "warehouse_id", "category", "current_stock",
                  "reorder_threshold", "unit_cost", "last_updated", "is_low_stock"]
    with open(export_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            row = {k: item.get(k) for k in fieldnames}
            writer.writerow(row)

    print(f"Exported DynamoDB contents to {export_path} for the dashboard step.")

    return body


if __name__ == "__main__":
    run_test()
