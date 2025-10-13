# src/common/metrics.py
import math
from typing import Dict, Any, List, Tuple

FIELDS = [
    "vendor.name",
    "invoice.number",
    "invoice.date_iso",
    "invoice.currency",
    "totals.total",
    "totals.tax",
]

NEAR_PCT = 0.01  # 1% tolerance

def _get_path(d: dict, path: str):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur

def _present(v):
    return v is not None and v != "" and not (isinstance(v, float) and math.isnan(v))

def _norm_num(v):
    try:
        s = "".join(ch for ch in str(v) if ch.isdigit() or ch in ".-")
        return float(s) if s else None
    except Exception:
        return None

def _near(a, b, p=NEAR_PCT):
    na, nb = _norm_num(a), _norm_num(b)
    if na is None or nb is None:
        return False
    return abs(na - nb) <= p * max(1.0, abs(nb))

def _ape(a, b):
    na, nb = _norm_num(a), _norm_num(b)
    if na is None or nb is None or nb == 0:
        return None
    return abs(na - nb) / abs(nb)

def compare_case(source_parse: Dict[str, Any], llm_norm: Dict[str, Any]) -> Dict[str, Any]:
    baseline = source_parse or {}
    output   = llm_norm    or {}

    coverage_baseline = {f: _present(_get_path(baseline, f)) for f in FIELDS}
    coverage_output   = {f: _present(_get_path(output,   f)) for f in FIELDS}
    wins_fill = {f: (not coverage_baseline[f] and coverage_output[f]) for f in FIELDS}

    wins_fix = {}
    for f in FIELDS:
        vb = _get_path(baseline, f)
        vo = _get_path(output, f)
        if not _present(vb) or not _present(vo):
            wins_fix[f] = False
        else:
            wins_fix[f] = (str(vb).strip() != str(vo).strip())

    numeric = {}
    for f in ["totals.total", "totals.tax"]:
        vb = _get_path(baseline, f)
        vo = _get_path(output, f)
        numeric[f] = {
            "baseline": vb,
            "model": vo,
            "near@1pct": _near(vo, vb),
            "ape_vs_baseline": _ape(vo, vb),
        }

    sum_ok = bool((output.get("validations") or {}).get("sum_matches_total", False))
    conf   = output.get("confidence") or {}

    cov_b = sum(coverage_baseline.values())
    cov_o = sum(coverage_output.values())

    return {
        "coverage_baseline": cov_b,
        "coverage_model": cov_o,
        "coverage_delta": cov_o - cov_b,
        "wins_fill": wins_fill,
        "wins_fix": wins_fix,
        "numeric": numeric,
        "sum_matches_total": sum_ok,
        "confidence": conf,
    }
