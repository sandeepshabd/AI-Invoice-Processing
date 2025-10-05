# tools/validate_genai.py
import json, math
from src.common.normalize import normalize_invoice

def near(a,b,p=0.01):
    return abs(float(a)-float(b)) <= p*max(1.0,float(b))

def score_case(textract_json_path, deterministic_json_path):
    tex = json.load(open(textract_json_path))
    det = json.load(open(deterministic_json_path))
    llm = normalize_invoice(tex, det)

    # Metrics
    fields = ["vendor.name","invoice.number","invoice.date_iso","invoice.currency","totals.total"]
    covered = sum(1 for f in fields if (lambda d,k: all((d:=d.get(k1,{})) or isinstance(d,dict) for k1 in k.split('.')) or d)(llm, f))
    sum_ok = llm.get("validations",{}).get("sum_matches_total", False)

    print("== Case ==")
    print("Coverage:", f"{covered}/{len(fields)}")
    print("Sum matches total:", sum_ok)
    print("Confidence:", llm.get("confidence"))

if __name__ == "__main__":
    # Example: replace with your fixture paths (or point at S3-exported textract JSONs)
    score_case("fixtures/textract_officemart.json", "fixtures/deterministic_officemart.json")
