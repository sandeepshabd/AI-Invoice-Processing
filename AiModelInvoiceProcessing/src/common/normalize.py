# src/common/normalize.py
import json, re, os
from .llm_client import invoke_bedrock_claude, invoke_bedrock_llama
from .prompt import SYSTEM, FEW_SHOTS, SCHEMA_TEXT, SCHEMA_PROMPT
from .config import USE_LLM, BEDROCK_MODEL_ID

def _json_only(s: str) -> str:
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    return m.group(0) if m else "{}"

def build_messages(textract_raw: dict, deterministic_parse: dict):
    msgs = [{"role": "system", "content": SYSTEM}]
    for ex in FEW_SHOTS:
        note = ex.get("input_schema_note", "Few-shot example")
        tex_hint = json.dumps(ex.get("textract_hint", {}), separators=(",", ":"))
        det = json.dumps(ex.get("deterministic_parse", {}), separators=(",", ":"))
        out = json.dumps(ex.get("output", {}), separators=(",", ":"))
        msgs.append({
            "role": "user",
            "content": f"{note}\nTEXTRACT={tex_hint}\nPARSE={det}\nSCHEMA={SCHEMA_TEXT}\n{SCHEMA_PROMPT}"
        })
        msgs.append({"role": "assistant", "content": out})

    tex = json.dumps(textract_raw or {}, separators=(",", ":"))
    det = json.dumps(deterministic_parse or {}, separators=(",", ":"))
    msgs.append({
        "role": "user",
        "content": f"TEXTRACT={tex}\nPARSE={det}\nSCHEMA={SCHEMA_TEXT}\n{SCHEMA_PROMPT}"
    })
    return msgs

def normalize_invoice(textract_raw: dict, deterministic_parse: dict) -> dict:
    # If LLM is disabled, just return a minimal normalized shell using det parse.
    if not USE_LLM:
        data = {
          "vendor":{"name": deterministic_parse.get("vendor","") or "", "country_hint":""},
          "invoice":{"number": deterministic_parse.get("invoice_number","") or "",
                     "date_iso": deterministic_parse.get("date_iso","") or "",
                     "currency": deterministic_parse.get("currency","") or ""},
          "totals":{"subtotal":"", "tax":"", "total": deterministic_parse.get("total","") or ""},
          "line_items": deterministic_parse.get("line_items", []) or [],
          "confidence":{"structure":"0.00","vendor":"0.00","totals":"0.00","lines":"0.00"},
          "validations":{"sum_matches_total": False}
        }
        return data

    msgs = build_messages(textract_raw, deterministic_parse)

    if BEDROCK_MODEL_ID.startswith("anthropic."):
        text = invoke_bedrock_claude(msgs)
    else:
        joined = (
            SYSTEM + "\n\n" + SCHEMA_TEXT +
            "\n\n" + json.dumps({"few_shots": FEW_SHOTS}, ensure_ascii=False) +
            "\n\nUser:\n" + json.dumps({"inputs":{
                "textract_expense": textract_raw,
                "deterministic_parse": deterministic_parse}}, ensure_ascii=False)
        )
        text = invoke_bedrock_llama(joined)

    js = _json_only(text)
    try:
        data = json.loads(js)
    except Exception:
        data = {
          "vendor":{"name":"","country_hint":""},
          "invoice":{"number":"","date_iso":"","currency":""},
          "totals":{"subtotal":"","tax":"","total":""},
          "line_items":[],
          "confidence":{"structure":"0.00","vendor":"0.00","totals":"0.00","lines":"0.00"},
          "validations":{"sum_matches_total": False}
        }
    for k in ["vendor","invoice","totals","confidence","validations"]:
        data.setdefault(k, {})
    data.setdefault("line_items", [])
    return data
