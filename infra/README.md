# Deploying to Real AWS (Optional)

The project is fully testable and demoable locally using `moto` (see
`tests/test_lambda_local.py`) with zero AWS cost or account needed. This
guide is for anyone who wants to deploy the Lambda to a real AWS account —
useful if you want to show it running live, but not required to prove the
pipeline works.

## Prerequisites

- AWS account with the AWS CLI installed and configured (`aws configure`)
- An IAM user/role with permissions for S3, Lambda, DynamoDB, and SNS

## 1. Create the S3 buckets

```bash
aws s3 mb s3://your-inventory-incoming-bucket
aws s3 mb s3://your-inventory-processed-bucket
```

## 2. Create the DynamoDB table

```bash
aws dynamodb create-table \
  --table-name InventoryCurrentState \
  --attribute-definitions AttributeName=sku,AttributeType=S \
  --key-schema AttributeName=sku,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## 3. Create the SNS topic for low-stock alerts

```bash
aws sns create-topic --name low-stock-alerts
# Note the TopicArn returned -- subscribe your email to it:
aws sns subscribe --topic-arn <TopicArn> --protocol email --notification-endpoint you@example.com
```

## 4. Package and deploy the Lambda function

```bash
cd src/lambda
pip install boto3 -t . --break-system-packages   # boto3 is included in the Lambda runtime by default, but pinning locally avoids version drift
zip -r ../../lambda_deployment.zip .
cd ../..

aws lambda create-function \
  --function-name inventory-etl-processor \
  --runtime python3.12 \
  --role arn:aws:iam::<your-account-id>:role/<your-lambda-execution-role> \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_deployment.zip \
  --environment "Variables={DYNAMODB_TABLE_NAME=InventoryCurrentState,SNS_TOPIC_ARN=<TopicArn>}" \
  --timeout 30
```

## 5. Connect S3 to trigger the Lambda

```bash
aws lambda add-permission \
  --function-name inventory-etl-processor \
  --statement-id s3invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::your-inventory-incoming-bucket

aws s3api put-bucket-notification-configuration \
  --bucket your-inventory-incoming-bucket \
  --notification-configuration file://infra/s3-notification-config.json
```

(See `infra/s3-notification-config.json` for the notification config —
update the Lambda ARN in it first.)

## 6. Test it live

```bash
aws s3 cp data/raw/inventory_snapshot.csv s3://your-inventory-incoming-bucket/incoming/inventory_snapshot.csv
aws logs tail /aws/lambda/inventory-etl-processor --follow
```

You should see the Lambda's JSON summary output in the logs, and a low-stock
email alert if you subscribed to the SNS topic.

## Cost note

This architecture is designed to stay within the AWS Free Tier for
light/demo usage: Lambda (1M free requests/month), DynamoDB on-demand
(25 GB free storage), S3 (5 GB free), and SNS (1,000 free email
notifications/month). Realistic for portfolio/demo use at no cost.
