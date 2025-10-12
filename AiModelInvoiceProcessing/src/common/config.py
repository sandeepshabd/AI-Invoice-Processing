# common/config.py
import os

def _get_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}

USE_LLM = _get_bool("USE_LLM", "false")

BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307")
BEDROCK_REGION   = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))

RAW_BUCKET       = os.getenv("RAW_BUCKET")
PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET")
DDB_TABLE        = os.getenv("DDB_TABLE")
TIMEZONE         = os.getenv("TIMEZONE", "America/Chicago")
