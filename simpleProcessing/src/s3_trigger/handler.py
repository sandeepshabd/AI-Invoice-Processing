# src/s3_trigger/handler.py
import urllib.parse, os
from common.process import process_one_object, RAW_BUCKET

def handler(event, context):
    results = []
    for rec in event["Records"]:
        bucket = rec["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
        # only handle if it’s the configured raw bucket
        if bucket != RAW_BUCKET:
            continue
        results.append(process_one_object(bucket, key))
    return {"ok": True, "processed": results}
