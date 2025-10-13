#!/usr/bin/env python3
# tools/score_day.py
import os, sys, csv, json, argparse, datetime, re
from zoneinfo import ZoneInfo
from pathlib import Path
from io import StringIO

# --- Repo imports (works regardless of CWD)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.common.metrics import compare_case, FIELDS  # expects src/common/metrics.py

# --- AWS (optional; only needed for S3 mode)
try:
    import boto3
except Exception:  # allow running without boto3 when using --local-dir
    boto3 = None

REGION = os.getenv("AWS_REGION", "us-east-1")
TZ     = os.getenv("TIMEZONE", "America/Chicago")

def _today_parts():
    now = datetime.datetime.now(ZoneInfo(TZ))
    return f"{now.year:04d}", f"{now.month:02d}", f"{now.day:02d}"

def _yymmdd(date_str: str | None):
    if date_str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            raise SystemExit("DATE must be YYYY-MM-DD")
        yyyy, mm, dd = date_str.split("-")
    else:
        yyyy, mm, dd = _today_parts()
    return yyyy, mm, dd

# --------------------------
# S3 helpers
# --------------------------
def _s3():
    if not boto3:
        raise SystemExit("boto3 not installed; use --local-dir or `pip install boto3`")
    return boto3.client("s3", region_name=REGION)

def list_parsed_json_s3(bucket: str, prefix: str):
    """Yield keys ending with parsed.json under an S3 prefix."""
    s3 = _s3()
    token = None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for o in resp.get("Contents", []) or []:
            k = o["Key"]
            if k.endswith("parsed.json"):
                yield k
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break

def get_json_s3(bucket: str, key: str) -> dict:
    s3 = _s3()
    b = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(b)

def put_text_s3(bucket: str, key: str, body: str, content_type: str):
    _s3().put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType=content_type)

# --------------------------
# Local helpers
# --------------------------
def list_parsed_json_local(root: Path):
    """Yield absolute paths of files named parsed.json under local dir."""
    for p in root.rglob("parsed.json"):
        yield str(p)

def get_json_local(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

# --------------------------
# Printing helpers
# --------------------------
def _bar(pct, width=28, filled="█", empty="·"):
    pct = max(0.0, min(1.0, float(pct or 0.0)))
    n = int(round(pct * width))
    return f"[{filled*n}{empty*(width-n)}] {int(pct*100):3d}%"

def print_header(date_str, source_desc):
    line = f"Invoice LLM Metrics — {date_str} "
    print(line + "─" * max(0, 78 - len(line)))
    print(f"Source: {source_desc}")

def print_kpis(n, avg_cov_delta, pct_sum, pct_near_total, pct_near_tax):
    print(f"Total invoices scored:       {n}")
    print(f"Avg fields gained (Δ):       {avg_cov_delta:.2f}")
    print(f"Line items reconcile:        {_bar(pct_sum)}")
    print(f"totals.total ±1%:            {_bar(pct_near_total)}")
    print(f"totals.tax ±1%:              {_bar(pct_near_tax)}")
    print()

def print_top_table(title, counts, n):
    print(f"{title} " + "─" * max(0, 78 - len(title)))
    for f in FIELDS:
        c = int(counts.get(f, 0))
        share = 0.0 if n == 0 else c / n
        bar = _bar(share)
        print(f"  {f:20} {c:2d}  {bar}")
    print()

def print_per_invoice(rows, max_rows=6):
    print("Per-invoice (first {:d} of {:d}) ".format(min(max_rows, len(rows)), len(rows)) + "─" * 42)
    print(f" {'Δ':>2}  {'sum≈total':>9}  {'near@1% total':>13}  {'near@1% tax':>12}   invoice_id")
    for r in rows[:max_rows]:
        delta = r.get("coverage_delta", 0)
        sm    = "YES" if str(r.get("sum_matches_total","")).lower()=="true" else "—"
        ntot  = "YES" if str(r.get("near1pct_total","")).lower()=="true" else "—"
        ntax  = "YES" if str(r.get("near1pct_tax","")).lower()=="true" else "—"
        inv_id = r.get("invoice_id") or (r.get("key","").split("/")[-2] if r.get("key") else "")
        print(f" {delta:>2}    {sm:>3}          {ntot:>3}            {ntax:>3}        {inv_id}")
    print()

def print_diffs(title, diffs):
    if not diffs:
        return
    print(title + " " + "─" * max(0, 78 - len(title)))
    for item in diffs:
        f = item["field"]
        vb = item["baseline"]
        vo = item["model"]
        print(f"  {f}: {vb!r}  ->  {vo!r}")
    print()

# --------------------------
# Core scoring
# --------------------------
def score_bucket(date_str: str, bucket: str, prefix_tpl="invoices/processed/{yyyy}/{mm}/{dd}/",
                 limit: int|None=None, show_diffs=False, upload=True):
    yyyy, mm, dd = _yymmdd(date_str)
    prefix = prefix_tpl.format(yyyy=yyyy, mm=mm, dd=dd)
    print(f"Scanning s3://{bucket}/{prefix}")

    rows = []
    agg = {
        "n": 0,
        "coverage_delta_sum": 0,
        "sum_matches_total_true": 0,
        "near1pct_total": 0,
        "near1pct_tax": 0,
        "wins_fill_counts": {f: 0 for f in FIELDS},
        "wins_fix_counts":  {f: 0 for f in FIELDS},
    }
    sample_fills = []
    sample_fixes = []

    for i, key in enumerate(list_parsed_json_s3(bucket, prefix)):
        data = get_json_s3(bucket, key)
        source = data.get("source_parse") or {}
        llm    = data.get("llm_normalized") or {}

        if not llm:
            continue  # skip textract-only

        m = compare_case(source, llm)

        # Aggregate
        agg["n"] += 1
        agg["coverage_delta_sum"] += m["coverage_delta"]
        agg["sum_matches_total_true"] += 1 if m["sum_matches_total"] else 0
        if m["numeric"]["totals.total"]["near@1pct"]: agg["near1pct_total"] += 1
        if m["numeric"]["totals.tax"]["near@1pct"]:   agg["near1pct_tax"] += 1

        for f in FIELDS:
            if m["wins_fill"][f]:
                agg["wins_fill_counts"][f] += 1
                if show_diffs:
                    sample_fills.append({
                        "key": key, "field": f,
                        "baseline": None,
                        "model": _dig(llm, f)
                    })
            if m["wins_fix"][f]:
                agg["wins_fix_counts"][f] += 1
                if show_diffs:
                    sample_fixes.append({
                        "key": key, "field": f,
                        "baseline": _dig(source, _map_field_to_source(f)),
                        "model": _dig(llm, f)
                    })

        rows.append({
            "key": key,
            "invoice_id": key.rstrip("/").split("/")[-2],
            "coverage_baseline": m["coverage_baseline"],
            "coverage_model": m["coverage_model"],
            "coverage_delta": m["coverage_delta"],
            "sum_matches_total": m["sum_matches_total"],
            "near1pct_total": bool(m["numeric"]["totals.total"]["near@1pct"]),
            "near1pct_tax":   bool(m["numeric"]["totals.tax"]["near@1pct"]),
        })

        if limit and agg["n"] >= limit:
            break

    # Print summary
    source_desc = f"s3://{bucket}/{prefix}"
    print_header(f"{yyyy}-{mm}-{dd}", source_desc)
    n = agg["n"] or 0
    avg_cov = (agg["coverage_delta_sum"]/n) if n else 0.0
    pct_sum = (agg["sum_matches_total_true"]/n) if n else 0.0
    pct_near_total = (agg["near1pct_total"]/n) if n else 0.0
    pct_near_tax   = (agg["near1pct_tax"]/n) if n else 0.0
    print_kpis(n, avg_cov, pct_sum, pct_near_total, pct_near_tax)
    print_top_table("Top fills (baseline empty → LLM filled)", agg["wins_fill_counts"], n)
    print_top_table("Top fixes (baseline had value → LLM changed)", agg["wins_fix_counts"], n)
    print_per_invoice(rows)

    if show_diffs:
        print_diffs("Sample fills (examples)", sample_fills[:12])
        print_diffs("Sample fixes (examples)", sample_fixes[:12])

    # Write S3 metrics unless disabled
    if upload and n > 0:
        metrics_prefix = f"metrics/{yyyy}/{mm}/{dd}/"
        csv_key  = metrics_prefix + "score.csv"
        json_key = metrics_prefix + "aggregate.json"

        buf = StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["key"])
        w.writeheader()
        for r in rows: w.writerow(r)
        put_text_s3(bucket, csv_key, buf.getvalue(), "text/csv")

        out = {
            "date": f"{yyyy}-{mm}-{dd}",
            "count_scored": n,
            "avg_coverage_delta": avg_cov,
            "pct_sum_matches_total": pct_sum,
            "pct_near1pct_total": pct_near_total,
            "pct_near1pct_tax": pct_near_tax,
            "wins_fill_counts": agg["wins_fill_counts"],
            "wins_fix_counts":  agg["wins_fix_counts"],
        }
        put_text_s3(bucket, json_key, json.dumps(out, indent=2), "application/json")
        print(f"Wrote s3://{bucket}/{csv_key}")
        print(f"Wrote s3://{bucket}/{json_key}")

def score_local(date_str: str, local_dir: str, limit: int|None=None, show_diffs=False):
    root = Path(local_dir).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"--local-dir not found: {root}")

    print(f"Scanning {root} for parsed.json")
    rows = []
    agg = {
        "n": 0,
        "coverage_delta_sum": 0,
        "sum_matches_total_true": 0,
        "near1pct_total": 0,
        "near1pct_tax": 0,
        "wins_fill_counts": {f: 0 for f in FIELDS},
        "wins_fix_counts":  {f: 0 for f in FIELDS},
    }
    sample_fills, sample_fixes = [], []

    for i, path in enumerate(list_parsed_json_local(root)):
        data = get_json_local(path)
        source = data.get("source_parse") or {}
        llm    = data.get("llm_normalized") or {}
        if not llm:
            continue

        m = compare_case(source, llm)

        agg["n"] += 1
        agg["coverage_delta_sum"] += m["coverage_delta"]
        agg["sum_matches_total_true"] += 1 if m["sum_matches_total"] else 0
        if m["numeric"]["totals.total"]["near@1pct"]: agg["near1pct_total"] += 1
        if m["numeric"]["totals.tax"]["near@1pct"]:   agg["near1pct_tax"] += 1

        for f in FIELDS:
            if m["wins_fill"][f]:
                agg["wins_fill_counts"][f] += 1
                if show_diffs:
                    sample_fills.append({
                        "path": path, "field": f,
                        "baseline": None,
                        "model": _dig(llm, f)
                    })
            if m["wins_fix"][f]:
                agg["wins_fix_counts"][f] += 1
                if show_diffs:
                    sample_fixes.append({
                        "path": path, "field": f,
                        "baseline": _dig(source, _map_field_to_source(f)),
                        "model": _dig(llm, f)
                    })

        rows.append({
            "key": path,
            "invoice_id": Path(path).parent.name,
            "coverage_baseline": m["coverage_baseline"],
            "coverage_model": m["coverage_model"],
            "coverage_delta": m["coverage_delta"],
            "sum_matches_total": m["sum_matches_total"],
            "near1pct_total": bool(m["numeric"]["totals.total"]["near@1pct"]),
            "near1pct_tax":   bool(m["numeric"]["totals.tax"]["near@1pct"]),
        })

        if limit and agg["n"] >= limit:
            break

    yyyy, mm, dd = _yymmdd(date_str)
    print_header(f"{yyyy}-{mm}-{dd}", f"local://{root}")
    n = agg["n"] or 0
    avg_cov = (agg["coverage_delta_sum"]/n) if n else 0.0
    pct_sum = (agg["sum_matches_total_true"]/n) if n else 0.0
    pct_near_total = (agg["near1pct_total"]/n) if n else 0.0
    pct_near_tax   = (agg["near1pct_tax"]/n) if n else 0.0
    print_kpis(n, avg_cov, pct_sum, pct_near_total, pct_near_tax)
    print_top_table("Top fills (baseline empty → LLM filled)", agg["wins_fill_counts"], n)
    print_top_table("Top fixes (baseline had value → LLM changed)", agg["wins_fix_counts"], n)
    print_per_invoice(rows)

    if show_diffs:
        print_diffs("Sample fills (examples)", sample_fills[:12])
        print_diffs("Sample fixes (examples)", sample_fixes[:12])

# --------------------------
# Utilities to dig into dicts and map baseline fields
# --------------------------
def _dig(d: dict, dotted: str):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur

def _map_field_to_source(f: str) -> str:
    """
    Maps normalized field path to deterministic baseline path names
    (since baseline parse uses different keys).
    """
    mapping = {
        "vendor.name": "vendor",                   # baseline key: 'vendor'
        "invoice.number": "invoice_number",        # 'invoice_number'
        "invoice.date_iso": "invoice_date",        # 'invoice_date' (string)
        "invoice.currency": "currency",            # 'currency'
        "totals.total": "total",                   # 'total'
        "totals.tax": "tax",                       # sometimes absent in baseline
    }
    return mapping.get(f, f)

# --------------------------
# CLI
# --------------------------
def main():
    ap = argparse.ArgumentParser(description="Score Textract (baseline) vs LLM-normalized outputs.")
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD (defaults to today in TIMEZONE)")
    ap.add_argument("--bucket", help="Processed S3 bucket (PROCESSED_BUCKET env by default)")
    ap.add_argument("--prefix-tpl", default="invoices/processed/{yyyy}/{mm}/{dd}/",
                    help="S3 prefix template (default: invoices/processed/{yyyy}/{mm}/{dd}/)")
    ap.add_argument("--local-dir", help="Scan a local directory instead of S3")
    ap.add_argument("--limit", type=int, help="Limit number of invoices processed")
    ap.add_argument("--show-diffs", action="store_true", help="Print sample baseline→LLM changes")
    ap.add_argument("--no-upload", action="store_true", help="Do not write metrics to S3")
    args = ap.parse_args()

    date_str = args.date
    bucket = args.bucket or os.getenv("PROCESSED_BUCKET")

    if args.local_dir:
        score_local(date_str, args.local_dir, limit=args.limit, show_diffs=args.show_diffs)
        return

    if not bucket:
        raise SystemExit("Missing bucket. Set --bucket or PROCESSED_BUCKET env.")

    score_bucket(
        date_str=date_str,
        bucket=bucket,
        prefix_tpl=args.prefix_tpl,
        limit=args.limit,
        show_diffs=args.show_diffs,
        upload=not args.no_upload
    )

if __name__ == "__main__":
    main()
