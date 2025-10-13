# tools/render_report.py
import os, sys, csv, json, datetime
from zoneinfo import ZoneInfo
import boto3
from io import StringIO
from pathlib import Path

REGION = os.getenv("AWS_REGION", "us-east-1")
TZ     = os.getenv("TIMEZONE", "America/Chicago")
BUCKET = os.environ["PROCESSED_BUCKET"]  # required
s3 = boto3.client("s3", region_name=REGION)

FIELDS = [
    "vendor.name",
    "invoice.number",
    "invoice.date_iso",
    "invoice.currency",
    "totals.total",
    "totals.tax",
]

def _today_parts():
    now = datetime.datetime.now(ZoneInfo(TZ))
    return f"{now.year:04d}", f"{now.month:02d}", f"{now.day:02d}"

def _keys_for_date(yyyy, mm, dd):
    base = f"metrics/{yyyy}/{mm}/{dd}/"
    return (base + "aggregate.json", base + "score.csv", base + "report.html")

def _get_s3_json(bucket, key):
    b = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(b)

def _get_s3_text(bucket, key):
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")

def _rows_from_csv(text):
    f = StringIO(text)
    r = csv.DictReader(f)
    return list(r)

def _bar(pct: float) -> str:
    pct = max(0.0, min(1.0, float(pct or 0.0)))
    width = int(pct * 100)
    return f'''
      <div class="bar">
        <div class="fill" style="width:{width}%"></div>
        <div class="label">{width}%</div>
      </div>
    '''

def _small_bar(n: int, total: int) -> str:
    if total <= 0:
        return '<div class="bar"><div class="label">0</div></div>'
    pct = n / total
    return _bar(pct)

def build_html(date_str, agg: dict, score_rows: list) -> str:
    n = agg.get("count_scored", 0)
    avg_cov = agg.get("avg_coverage_delta", 0.0)
    pct_sum = agg.get("pct_sum_matches_total", 0.0)
    pct_near_total = agg.get("pct_near1pct_total", 0.0)
    pct_near_tax = agg.get("pct_near1pct_tax", 0.0)
    wins_fill = agg.get("wins_fill_counts", {})
    wins_fix  = agg.get("wins_fix_counts", {})

    # Sort “top wins” by field
    top_fill = sorted(((f, wins_fill.get(f, 0)) for f in FIELDS), key=lambda x: x[1], reverse=True)
    top_fix  = sorted(((f, wins_fix.get(f, 0)) for f in FIELDS), key=lambda x: x[1], reverse=True)

    # Simple CSS/HTML—no external deps
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Invoice LLM Metrics — {date_str}</title>
<style>
  body {{ font: 14px/1.45 system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 24px; color:#222; }}
  h1 {{ margin: 0 0 4px; }}
  .muted {{ color:#666; }}
  .kpis {{ display:grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap:16px; margin: 16px 0 24px; }}
  .card {{ border:1px solid #eee; border-radius:12px; padding:16px; box-shadow:0 1px 2px rgba(0,0,0,0.04); }}
  .big {{ font-size: 28px; font-weight: 700; }}
  .bar {{ position: relative; background:#f2f2f2; border-radius:8px; height:16px; overflow:hidden; }}
  .fill {{ background:#4f46e5; height:100%; }}
  .label {{ position:absolute; top:-24px; right:0; font-size:12px; color:#444; }}
  table {{ border-collapse: collapse; width:100%; }}
  th, td {{ padding:8px 10px; border-bottom:1px solid #eee; text-align:left; }}
  .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:16px; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }}
  .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; background:#eef; color:#334; font-size:12px; margin-left:6px; }}
</style>
</head>
<body>
  <h1>Invoice LLM Metrics</h1>
  <div class="muted">{date_str}</div>

  <div class="kpis">
    <div class="card">
      <div>Total invoices scored</div>
      <div class="big">{n}</div>
      <div class="muted">Only invoices with both Textract + LLM were counted</div>
    </div>
    <div class="card">
      <div>Avg fields gained (coverage Δ)</div>
      <div class="big">{avg_cov:.2f}</div>
      <div class="muted">How many fields the LLM filled per invoice (avg)</div>
    </div>
    <div class="card">
      <div>Line items reconcile to total</div>
      {_bar(pct_sum)}
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>Numeric sanity</h3>
      <table>
        <tr><th>Metric</th><th>Share within ±1%</th></tr>
        <tr><td>totals.total</td><td>{int((pct_near_total or 0)*100)}%</td></tr>
        <tr><td>totals.tax</td><td>{int((pct_near_tax or 0)*100)}%</td></tr>
      </table>
    </div>
    <div class="card">
      <h3>Fields compared</h3>
      <div class="mono">{", ".join(FIELDS)}</div>
    </div>
  </div>

  <div class="grid" style="margin-top:24px;">
    <div class="card">
      <h3>Top fills <span class="pill">baseline empty → LLM filled</span></h3>
      <table>
        <tr><th>Field</th><th>Count</th><th>Share</th></tr>"""
    for f, c in top_fill:
        share = 0 if n == 0 else c / n
        html += f"""
        <tr><td>{f}</td><td>{c}</td><td>{_small_bar(c, n)}</td></tr>"""
    html += """
      </table>
    </div>
    <div class="card">
      <h3>Top fixes <span class="pill">baseline present → LLM changed</span></h3>
      <table>
        <tr><th>Field</th><th>Count</th><th>Share</th></tr>"""
    for f, c in top_fix:
        share = 0 if n == 0 else c / n
        html += f"""
        <tr><td>{f}</td><td>{c}</td><td>{_small_bar(c, n)}</td></tr>"""
    html += """
      </table>
    </div>
  </div>

  <div class="card" style="margin-top:24px;">
    <h3>Per-invoice summary</h3>
    <table>
      <tr>
        <th class="mono">key</th>
        <th>cov Δ</th>
        <th>sum≈total?</th>
        <th>near@1% total</th>
        <th>near@1% tax</th>
      </tr>"""
    for r in score_rows:
        html += f"""
      <tr>
        <td class="mono">{r.get('key','')}</td>
        <td>{r.get('coverage_delta','')}</td>
        <td>{'✅' if str(r.get('sum_matches_total','')).lower()=='true' else '—'}</td>
        <td>{'✅' if str(r.get('near1pct_total','')).lower()=='true' else '—'}</td>
        <td>{'✅' if str(r.get('near1pct_tax','')).lower()=='true' else '—'}</td>
      </tr>"""
    html += """
    </table>
  </div>

  <p class="muted" style="margin-top:16px;">This report compares Textract (baseline) vs. LLM-normalized output saved under <span class="mono">invoices/processed/YYYY/MM/DD/**/parsed.json</span>.</p>
</body>
</html>"""
    return html

def main(date_str=None):
    if date_str:
        yyyy, mm, dd = date_str.split("-")
    else:
        yyyy, mm, dd = _today_parts()

    agg_key, csv_key, report_key = _keys_for_date(yyyy, mm, dd)

    # Load inputs
    agg = _get_s3_json(BUCKET, agg_key)
    csv_text = _get_s3_text(BUCKET, csv_key)
    rows = _rows_from_csv(csv_text)

    # Build + write HTML
    html = build_html(f"{yyyy}-{mm}-{dd}", agg, rows)
    s3.put_object(
        Bucket=BUCKET,
        Key=report_key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )
    print(f"Wrote s3://{BUCKET}/{report_key}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
