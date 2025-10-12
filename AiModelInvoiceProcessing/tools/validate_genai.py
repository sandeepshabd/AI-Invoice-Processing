import json, math, sys
from pathlib import Path


# --- add repo paths so imports work regardless of CWD ---
ROOT = Path(__file__).resolve().parent.parent  # repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))             # enables `import src...`
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))     # enables `from common ...`

# Try both import styles depending on your layout
from src.common.normalize import normalize_invoice


FIELDS = [
    "vendor.name",
    "invoice.number",
    "invoice.date_iso",
    "invoice.currency",
    "totals.total",
    "totals.tax",
]
NEAR_PCT = 0.01  # 1%

def get_path(d: dict, path: str):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur

def present(v):
    return v is not None and v != "" and not (isinstance(v, float) and math.isnan(v))

def norm_num(v):
    try:
        s = "".join(ch for ch in str(v) if ch.isdigit() or ch in ".-")
        return float(s) if s else None
    except Exception:
        return None

def near(a, b, p=NEAR_PCT):
    na, nb = norm_num(a), norm_num(b)
    if na is None or nb is None:
        return False
    return abs(na - nb) <= p * max(1.0, abs(nb))

def ape(a, b):
    na, nb = norm_num(a), norm_num(b)
    if na is None or nb is None or nb == 0:
        return None
    return abs(na - nb) / abs(nb)

def score_case(textract_json_path: str, deterministic_json_path: str):
    from src.common.normalize import normalize_invoice

    tex = json.load(open(textract_json_path))
    det = json.load(open(deterministic_json_path))
    llm = normalize_invoice(tex, det)

    baseline = det
    output = llm

    coverage_baseline = {f: present(get_path(baseline, f)) for f in FIELDS}
    coverage_output   = {f: present(get_path(output,   f)) for f in FIELDS}
    wins_fill = {f: (not coverage_baseline[f] and coverage_output[f]) for f in FIELDS}

    wins_fix = {}
    for f in FIELDS:
        vb = get_path(baseline, f); vo = get_path(output, f)
        if not present(vb) or not present(vo):
            wins_fix[f] = False
        else:
            wins_fix[f] = (str(vb).strip() != str(vo).strip())

    num_metrics = {}
    for f in ["totals.total", "totals.tax"]:
        vb = get_path(baseline, f); vo = get_path(output, f)
        num_metrics[f] = {
            "baseline": vb, "model": vo,
            "near@1pct": near(vo, vb),
            "ape_vs_baseline": ape(vo, vb),
        }

    sum_ok = bool(output.get("validations", {}).get("sum_matches_total", False))
    conf = output.get("confidence")

    print("== Case ==")
    print(f"textract:      {textract_json_path}")
    print(f"deterministic: {deterministic_json_path}")
    cov_b = sum(coverage_baseline.values()); cov_o = sum(coverage_output.values())
    print(f"Coverage  baseline={cov_b}/{len(FIELDS)}  model={cov_o}/{len(FIELDS)}  Δ=+{cov_o-cov_b}")
    print(f"Sum matches total: {sum_ok}")
    print(f"Confidence: {conf}")
    print("\nField-by-field:")
    for f in FIELDS:
        vb = get_path(baseline, f); vo = get_path(output, f)
        tag = []
        if wins_fill[f]: tag.append("FILL")
        if wins_fix[f]:  tag.append("CHANGED")
        print(f" - {f:18} | base={vb!r} | model={vo!r} | {'/'.join(tag) if tag else '-'}")
    print("\nNumeric:")
    for f, m in num_metrics.items():
        print(f" - {f:12} near@1%={m['near@1pct']}  APE_vs_base={m['ape_vs_baseline']}")
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python tools/validate_genai.py <textract_json> <deterministic_json>")
        sys.exit(2)
    sys.exit(score_case(sys.argv[1], sys.argv[2]))
