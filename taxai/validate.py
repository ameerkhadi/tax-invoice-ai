"""Data-quality and VAT validation rules. Each rule returns issues as (invoice_id, rule, severity, detail)."""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from .config import VAT_RATES, ROUNDING_TOLERANCE, LARGE_INVOICE_Z

REQUIRED = ["invoice_id", "supplier_id", "supplier_org_no", "invoice_date", "net_amount", "vat_amount", "total_amount"]


def luhn_ok(digits: str) -> bool:
    """Luhn mod-10 check, used for Swedish organisation/personal numbers (10 digits)."""
    d = [int(c) for c in digits if c.isdigit()]
    if len(d) != 10:
        return False
    total = 0
    for i, x in enumerate(d):
        y = x * (2 if i % 2 == 0 else 1)
        total += y - 9 if y > 9 else y
    return total % 10 == 0


def validate(rows: list[dict]) -> list[tuple]:
    issues: list[tuple] = []
    by_key = defaultdict(list)
    by_supplier = defaultdict(list)
    for r in rows:
        iid = r["invoice_id"]
        missing = [f for f in REQUIRED if not str(r.get(f, "")).strip()]
        if missing:
            issues.append((iid, "missing_field", "high", ", ".join(missing)))
        org = r.get("supplier_org_no", "")
        if org and not luhn_ok(org):
            issues.append((iid, "invalid_org_number", "high", f"{org} fails Luhn check"))
        try:
            net, vat, tot = float(r["net_amount"]), float(r["vat_amount"]), float(r["total_amount"])
        except (TypeError, ValueError):
            issues.append((iid, "non_numeric_amount", "high", "amount fields not numeric"))
            continue
        rate = VAT_RATES.get(r.get("vat_class", ""), None)
        if rate is None:
            issues.append((iid, "unknown_vat_class", "medium", r.get("vat_class", "")))
        else:
            expected = round(net * rate, 2)
            diff = vat - expected
            if abs(diff) > ROUNDING_TOLERANCE:
                implied = vat / net if net else 0
                wrong_rate = next((k for k, v in VAT_RATES.items()
                                   if v and k != r.get("vat_class") and abs(implied - v) < 0.002), None)
                detail = (f"VAT {vat:.2f} looks like {wrong_rate} rate; expected {expected:.2f} ({r['vat_class']})"
                          if wrong_rate else f"VAT {vat:.2f} vs expected {expected:.2f} (diff {diff:+.2f})")
                issues.append((iid, "vat_mismatch", "high", detail))
        if abs(net + vat - tot) > 0.01:
            issues.append((iid, "total_mismatch", "medium", f"net+vat={net + vat:.2f} total={tot:.2f}"))
        by_key[(r.get("supplier_id"), r.get("invoice_date"), r.get("net_amount"), r.get("vat_amount"))].append(iid)
        by_supplier[r.get("supplier_id")].append((iid, net))
    for key, ids in by_key.items():
        for dup in ids[1:]:
            issues.append((dup, "possible_duplicate", "high", f"same supplier/date/amounts as {ids[0]}"))
    for sid, items in by_supplier.items():
        amounts = [a for _, a in items]
        if len(amounts) < 8:
            continue
        m = median(amounts)
        mad = median(abs(a - m) for a in amounts) * 1.4826 or 1.0
        for iid, a in items:
            if (a - m) / mad > LARGE_INVOICE_Z * 3:  # conservative: only flag extreme outliers
                issues.append((iid, "unusually_large", "low", f"net {a:,.0f} vs supplier median {m:,.0f}"))
    return issues
