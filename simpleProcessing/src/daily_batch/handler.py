# src/daily_batch/handler.py
import os, datetime
from zoneinfo import ZoneInfo
import boto3

RAW_BUCKET = os.environ["RAW_BUCKET"]
REGION = os.getenv("AWS_REGION", "us-east-1")
TZ = os.getenv("TIMEZONE", "America/Chicago")

s3 = boto3.client("s3", region_name=REGION)
from common.process import process_one_object

def today_prefix():
    now = datetime.datetime.now(ZoneInfo(TZ))
    yyyy = f"{now.year:04d}"
    mm = f"{now.month:02d}"
    dd = f"{now.day:02d}"
    return f"invoices/raw/{yyyy}/{mm}/{dd}/"

def handler(event, context):
    prefix = today_prefix()
    token = None
    processed = []
    while True:
        kwargs = {"Bucket": RAW_BUCKET, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or key.lower().endswith(".tmp"):
                continue
            # process each object idempotently
            processed.append(process_one_object(RAW_BUCKET, key))
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return {"ok": True, "prefix": prefix, "count": len(processed)}
