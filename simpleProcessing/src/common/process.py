# src/common/process.py
import os, json, hashlib, boto3

RAW_BUCKET = os.environ["RAW_BUCKET"]
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]
TABLE = os.environ["DDB_TABLE"]
REGION = os.getenv("AWS_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=REGION)
textract = boto3.client("textract", region_name=REGION)
ddb = boto3.resource("dynamodb", region_name=REGION)
table = ddb.Table(TABLE)

from .parser import parse_textract_expense

def invoice_id_from_key(key: str) -> str:
    # stable id for idempotency
    return hashlib.sha1(key.encode("utf-8")).hexdigest()

def processed_key_for(raw_key: str) -> str:
    # Put processed JSON alongside date partition, under a per-invoice folder
    parts = raw_key.split("/")
    # expect invoices/raw/YYYY/MM/DD/<file>
    # fallback to putting under a generic folder if structure differs
    try:
        yyyy, mm, dd = parts[2], parts[3], parts[4]
        return f"invoices/processed/{yyyy}/{mm}/{dd}/{invoice_id_from_key(raw_key)}/parsed.json"
    except Exception:
        return f"invoices/processed/misc/{invoice_id_from_key(raw_key)}/parsed.json"

def process_one_object(bucket: str, key: str) -> dict:
    # 1) Textract sync call
    resp = textract.analyze_expense(Document={"S3Object": {"Bucket": bucket, "Name": key}})
    parsed = parse_textract_expense(resp)

    # 2) Save processed JSON
    out_key = processed_key_for(key)
    s3.put_object(
        Bucket=PROCESSED_BUCKET,
        Key=out_key,
        Body=json.dumps(parsed).encode("utf-8"),
        ContentType="application/json"
    )

    # 3) Upsert into DynamoDB (idempotent on same invoice_id)
    inv_id = invoice_id_from_key(key)
    table.put_item(Item={"invoice_id": inv_id, "raw_key": key, "processed_key": out_key, **parsed})

    return {"invoice_id": inv_id, "processed_key": out_key, "parsed": parsed}
