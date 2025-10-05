# src/common/normalize.py
import json, re, os
from .llm_client import invoke_bedrock_claude, invoke_bedrock_llama
from .prompt import SYSTEM, FEW_SHOTS, SCHEMA_TEXT

MODEL_ID = os.getenv("BEDROCK_MODEL_ID","anthropic.claude-3-haiku-20240307")

def _json_only(s: str) -> str:
    # Extract first {...} blob
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    return m.group(0) if m else "{}"

def build_messages(textract_raw: dict, deterministic_parse: dict) -> list[dict]:
    shots = []
    for ex in FEW_SHOTS:
        shots.append({"role":"user", "content": json.dumps({
            "note": ex["input_schema_note"],
            "textract_hint": ex.get("textract_hint",{}),
            "deterministic_parse": ex.get("deterministic_parse",{})
        }, ensure_ascii=False)})
        shots.append({"role":"assistant", "content": json.dumps(ex["output"], separators=(',',':'), ensure_ascii=False)})

    user_payload = {
      "instructions": "Normalize the invoice using the schema and rules.",
      "schema": SCHEMA_TEXT,
      "inputs": {
        "textract_expense": textract_raw,
        "deterministic_parse": deterministic_parse
      }
    }
    return [{"role":"system","content":SYSTEM}, *shots, {"role":"user","content":json.dumps(user_payload, ensure_ascii=False)}]

def normalize_invoice(textract_raw: dict, deterministic_parse: dict) -> dict:
    # Build prompt
    msgs = build_messages(textract_raw, deterministic_parse)

    if MODEL_ID.startswith("anthropic."):
        text = invoke_bedrock_claude(msgs)
    else:
        # Fall back to Llama with a single concatenated prompt
        joined = SYSTEM + "\n\n" + SCHEMA_TEXT + "\n\n" + json.dumps({"few_shots": FEW_SHOTS}, ensure_ascii=False) + \
                 "\n\nUser:\n" + json.dumps({"inputs":{
                    "textract_expense": textract_raw,
                    "deterministic_parse": deterministic_parse}}, ensure_ascii=False)
        text = invoke_bedrock_llama(joined)

    js = _json_only(text)
    try:
        data = json.loads(js)
    except Exception:
        # Safety net: empty-but-valid shape
        data = {
          "vendor":{"name":"","country_hint":""},
          "invoice":{"number":"","date_iso":"","currency":""},
          "totals":{"subtotal":"","tax":"","total":""},
          "line_items":[],
          "confidence":{"structure":"0.00","vendor":"0.00","totals":"0.00","lines":"0.00"},
          "validations":{"sum_matches_total": False}
        }
    # Minimal hard validation/coercion
    for k in ["vendor","invoice","totals","confidence","validations"]:
        data.setdefault(k, {})
    data.setdefault("line_items", [])
    return data
