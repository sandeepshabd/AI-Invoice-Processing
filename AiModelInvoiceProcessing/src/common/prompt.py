# src/common/prompt.py
SYSTEM = (
  "You are a strict, deterministic invoice-normalization engine. "
  "Always output ONLY minified JSON matching the schema. No prose."
)

# Few-shot examples keep it compact; show EUR + USD
FEW_SHOTS = [
  {
    "input_schema_note": "Textract expense JSON (truncated) and a rough parsed dict",
    "textract_hint": {"SummaryFields":[{"Type":{"Text":"VENDOR_NAME"},"ValueDetection":{"Text":"Papeterie Paris"}}]},
    "deterministic_parse": {"vendor":"Papeterie Paris","currency":"EUR"},
    "output": {
      "vendor": {"name":"Papeterie Paris","country_hint":"FR"},
      "invoice": {"number":"PP-2025-187","date_iso":"2025-10-04","currency":"EUR"},
      "totals": {"subtotal": "76.80", "tax":"15.36", "total":"92.16"},
      "line_items":[{"description":"Ramette A4 (500 feuilles)","qty":"6","unit_price":"6.40","amount":"38.40"}],
      "confidence":{"structure":"0.88","vendor":"0.90","totals":"0.86","lines":"0.84"},
      "validations":{"sum_matches_total": true}
    }
  },
  {
    "textract_hint": {"SummaryFields":[{"Type":{"Text":"VENDOR_NAME"},"ValueDetection":{"Text":"Alpha Supplies Inc."}}]},
    "deterministic_parse": {"vendor":"Alpha Supplies Inc.","currency":"USD"},
    "output": {
      "vendor":{"name":"Alpha Supplies Inc.","country_hint":"US"},
      "invoice":{"number":"INV-2025-104","date_iso":"2025-10-04","currency":"USD"},
      "totals":{"subtotal":"114.48","tax":"9.43","total":"123.91"},
      "line_items":[
        {"description":"A4 Paper (500 sheets)","qty":"5","unit_price":"6.49","amount":"32.45"},
        {"description":"Printer Ink Cartridge - Black","qty":"2","unit_price":"34.50","amount":"69.00"},
        {"description":"Stapler Set","qty":"1","unit_price":"12.50","amount":"12.50"}
      ],
      "confidence":{"structure":"0.92","vendor":"0.93","totals":"0.90","lines":"0.91"},
      "validations":{"sum_matches_total": true}
    }
  }
]

# “Schema-first” instruction (the guardrail)
SCHEMA_TEXT = """
TARGET_JSON_SCHEMA (all values strings unless boolean noted):
{
  "vendor": {"name":"", "country_hint":""},
  "invoice": {"number":"", "date_iso":"YYYY-MM-DD", "currency":""},
  "totals": {"subtotal":"", "tax":"", "total":""},
  "line_items": [{"description":"", "qty":"", "unit_price":"", "amount":""}],
  "confidence": {"structure":"0.0-1.0", "vendor":"0.0-1.0", "totals":"0.0-1.0", "lines":"0.0-1.0"},
  "validations": {"sum_matches_total": true|false}
}
Hard rules:
- Output ONLY minified JSON that validates against this shape.
- Use ISO 8601 for dates (YYYY-MM-DD). Infer if needed.
- Normalize currency to ISO code.
- If any field unknown, use empty string (not null).
- If sum(line_items.amount) ~ totals.total (+/- 1%), set sum_matches_total=true else false.
- Never include explanations or markdown, just JSON.
"""
