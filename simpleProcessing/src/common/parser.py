# src/common/parser.py
def _find(summary_fields, *types):
    for t in types:
        t_upper = t.upper()
        for f in summary_fields:
            if f.get("Type", {}).get("Text", "").upper() == t_upper:
                return f.get("ValueDetection", {}).get("Text")
    return None

def parse_textract_expense(resp: dict) -> dict:
    docs = resp.get("ExpenseDocuments", [])
    if not docs:
        return {"error": "no_document"}

    d0 = docs[0]
    sf = d0.get("SummaryFields", [])

    vendor = _find(sf, "VENDOR_NAME", "SUPPLIER", "SELLER_NAME")
    invoice_number = _find(sf, "INVOICE_RECEIPT_ID", "INVOICE_NUMBER")
    invoice_date = _find(sf, "INVOICE_RECEIPT_DATE", "INVOICE_DATE")
    total = _find(sf, "TOTAL")
    currency = _find(sf, "CURRENCY")

    line_items = []
    for group in d0.get("LineItemGroups", []):
        for li in group.get("LineItems", []):
            row = {"description": None, "qty": None, "unit_price": None, "amount": None}
            for f in li.get("LineItemExpenseFields", []):
                t = f.get("Type", {}).get("Text")
                v = f.get("ValueDetection", {}).get("Text")
                if t == "ITEM":
                    row["description"] = v
                elif t == "QUANTITY":
                    row["qty"] = v
                elif t == "UNIT_PRICE":
                    row["unit_price"] = v
                elif t in ("PRICE", "AMOUNT"):
                    row["amount"] = v
            line_items.append(row)

    return {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "total": total,
        "currency": currency,
        "line_items": line_items,
        "meta": {"source": "textract.analyze_expense"}
    }
