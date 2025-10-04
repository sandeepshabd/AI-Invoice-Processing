# AI-Invoice-Processing
🚀 Building a Multi-Agent System for Invoice Processing on AWS

Summary
Managing thousands of invoices manually is costly, slow, and error-prone. By leveraging AWS services, MCP (Model Context Protocol), and a multi-agent approach, we can progressively evolve from a simple invoice pipeline into a scalable, AI-driven system. Here’s a 3-phase journey:

Phase 1: Baseline Invoice Processing without any AI 

We begin with a simple but working pipeline: upload invoices, extract data, and store results.

🔹 Flow: Web → S3 → Textract → DynamoDB
🔹 Tech stack: FastAPI, Boto3, DynamoDB, custom parser
🔹 Output: Vendor, totals, and line items in a clean JSON schema

        (User / System Upload)
                  │
                  ▼
        ┌─────────────────────┐
        │   S3 Raw Bucket     │   invoices/raw/YYYY/MM/DD/<file>.pdf
        └────────┬────────────┘
                 │ S3:ObjectCreated
                 ▼
        ┌─────────────────────┐
        │ InvoiceProcessorFn  │  (src/s3_trigger/handler.py)
        │  - Textract call    │  analyze_expense
        │  - parse → JSON     │  src/common/parser.py
        │  - write outputs    │  src/common/process.py
        └────────┬────────────┘
                 │
     writes JSON │                      writes item
                 ▼                               ▼
        ┌─────────────────────┐        ┌──────────────────────┐
        │ S3 Processed Bucket │        │  DynamoDB: Invoices  │
        │ invoices/processed/ │        │  invoice_id (HASH)   │
        └─────────────────────┘        └──────────────────────┘


             (Nightly / On-demand)
                  │
       EventBridge Rule (cron)
                  │
                  ▼
        ┌─────────────────────┐    lists: invoices/raw/YYYY/MM/DD/
        │   DailyBatchFn      │ -> process_one_object(...) per key
        │ (src/daily_batch/   │    same pipeline as above
        │  handler.py)        │
        └─────────────────────┘


-----------------------------------Basic setup and Comamnds-----------------------------------------

# Copy .env file and rename it :
cp .env.example .env



# Different AWS profile check commands locally:

aws configure list-profiles
aws sts get-caller-identity --profile demo
aws s3api list-buckets --profile demo


This worked for deploymnent and tml was created.
# load env (if you’re using .env)      
set -a; source .env; set +a
sam deploy --guided --region "$AWS_DEFAULT_REGION" --profile "$AWS_PROFILE"

# push data files:
make seed



# validate pushed files 
# set once per shell
export AWS_PROFILE=demo
export AWS_DEFAULT_REGION=us-east-1
export RAW_BUCKET=invoices-raw--sandeepsingh-2025-10-04

Y=$(TZ=America/Chicago date +%Y)
M=$(TZ=America/Chicago date +%m)
D=$(TZ=America/Chicago date +%d)
P="invoices/raw/$Y/$M/$D"

aws s3 ls "s3://$RAW_BUCKET/$P/" --recursive --human-readable --summarize


# check processed files:
export PROCESSED_BUCKET=invoice-processed--sandeepsingh-2025-10-04
aws s3 ls "s3://$PROCESSED_BUCKET/invoices/processed/$Y/$M/$D/" \
  --recursive --human-readable --summarize


  # check dynamo DB
  aws dynamodb scan --table-name Invoices --region $AWS_DEFAULT_REGION --profile $AWS_PROFILE \
  --max-items 10 --output table

# Check lambda logs
# List functions in the stack
aws cloudformation describe-stack-resources \
  --stack-name invoice-phase1-prod --region $AWS_DEFAULT_REGION --profile $AWS_PROFILE \
  --query "StackResources[?ResourceType=='AWS::Lambda::Function'].[LogicalResourceId,PhysicalResourceId]" \
  --output table
# Replace <physical-fn-name> with the S3-trigger lambda you see above (InvoiceProcessorFn)
aws logs describe-log-groups --region $AWS_DEFAULT_REGION --profile $AWS_PROFILE \
  --query "logGroups[?contains(logGroupName, '<physical-fn-name>')].logGroupName" --output text


# Tail the latest logs (use the log group from the previous command)
aws logs tail "/aws/lambda/<physical-fn-name>" --follow --since 30m \
  --region $AWS_DEFAULT_REGION --profile $AWS_PROFILE


# running daily batch manually
# Get the batch function name
aws cloudformation describe-stack-resource \
  --stack-name invoice-phase1-prod --logical-resource-id DailyBatchFn \
  --region $AWS_DEFAULT_REGION --profile $AWS_PROFILE \
  --query 'StackResourceDetail.PhysicalResourceId' --output text

  example output from above -> invoice-phase1-prod-DailyBatchFn-6cqr4XD2EPeW
plug this in below command for <daily-batch-physical-name>
# Invoke it (replace function name below)
aws lambda invoke --function-name <daily-batch-physical-name> /tmp/out.json \
  --region $AWS_DEFAULT_REGION --profile $AWS_PROFILE && cat /tmp/out.json


# Debugging lambda function
# Find the function name(s) in the stack
aws cloudformation describe-stack-resources \
  --stack-name invoice-phase1-prod \
  --region us-east-1 --profile demo \
  --query "StackResources[?ResourceType=='AWS::Lambda::Function'].[LogicalResourceId,PhysicalResourceId]" \
  --output table



  |                           DescribeStackResources                            |
+---------------------+-------------------------------------------------------+
|  DailyBatchFn       |  invoice-phase1-prod-DailyBatchFn-6cqr4XD2EPeW        |
|  InvoiceProcessorFn |  invoice-phase1-prod-InvoiceProcessorFn-CQwwRCvZpDWu

# Tail logs (pick the physical name for DailyBatchFn or InvoiceProcessorFn)
aws logs tail "/aws/lambda/<physical-function-name>" \
  --since 30m --follow \
  --region us-east-1 --profile demo

aws logs tail "/aws/lambda/invoice-phase1-prod-InvoiceProcessorFn-CQwwRCvZpDWu" \
  --since 30m --follow \
  --region us-east-1 --profile demo



Output: 
Db entries:
  -------------------------------------------------------------------------------------------------
|                                             Scan                                              |
+-----------------------------------------+------------------+----------------------------------+
|            ConsumedCapacity             |      Count       |          ScannedCount            |
+-----------------------------------------+------------------+----------------------------------+
|  None                                   |  3               |  3                               |
+-----------------------------------------+------------------+----------------------------------+
||                                            Items                                            ||
|||                                         currency                                          |||
||+--------------------------------------------+----------------------------------------------+||
|||  NULL                                      |  True                                        |||
||+--------------------------------------------+----------------------------------------------+||
|||                                       invoice_date                                        |||
||+----------------------+--------------------------------------------------------------------+||
|||  S                   |  2025-10-01                                                        |||
||+----------------------+--------------------------------------------------------------------+||
|||                                        invoice_id                                         |||
||+-------+-----------------------------------------------------------------------------------+||
|||  S    |  abc46fe67341dfa4c7841180cff6f3396426bb0c                                         |||
||+-------+-----------------------------------------------------------------------------------+||
|||                                      invoice_number                                       |||
||+-------------------+-----------------------------------------------------------------------+||
|||  S                |  AOS-2025-0098                                                        |||
||+-------------------+-----------------------------------------------------------------------+||