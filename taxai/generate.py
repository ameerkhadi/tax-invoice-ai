"""Generate a reproducible synthetic dataset of supplier invoices with realistic data-quality problems.

All companies and numbers are fictitious. VAT rates are configurable examples (see config.py) and are not tax advice.
"""
from __future__ import annotations

import csv
import os
import random
from datetime import date, timedelta

from .config import VAT_RATES, DATA_DIR
from .validate import luhn_ok

CATEGORIES = {  # category -> VAT class
    "IT services": "standard", "Office supplies": "standard", "Consulting": "standard",
    "Hotel stay": "reduced_1", "Restaurant": "reduced_1", "Food supplies": "reduced_1",
    "Books & journals": "reduced_2", "Passenger transport": "reduced_2",
    "Healthcare": "exempt", "Financial services": "exempt",
}
WORDS = ["Nord", "Vasa", "Fjäll", "Ljus", "Ek", "Sjö", "Berg", "Strand", "Kron", "Polar"]
TYPES = ["Data AB", "Konsult AB", "Logistik AB", "Hotell AB", "Media AB", "Tech AB", "Service AB"]


def org_number(rng: random.Random, valid: bool = True) -> str:
    """10-digit organisation number NNNNNN-NNNN with a Luhn (mod 10) check digit."""
    while True:
        body = [rng.randint(1, 9), rng.randint(0, 9)] + [rng.randint(0, 9) for _ in range(7)]
        body[2] = rng.randint(2, 9)  # third digit >= 2 for legal entities
        for check in range(10):
            digits = "".join(map(str, body)) + str(check)
            if luhn_ok(digits) == valid:
                return f"{digits[:6]}-{digits[6:]}"


def generate(n_invoices: int = 600, n_suppliers: int = 45, seed: int = 7, path: str | None = None) -> str:
    rng = random.Random(seed)
    suppliers = []
    for i in range(n_suppliers):
        name = f"{rng.choice(WORDS)}{rng.choice(WORDS).lower()} {rng.choice(TYPES)}"
        suppliers.append((f"S{i + 1:03d}", name, org_number(rng, valid=rng.random() > 0.05)))
    rows, seen = [], []
    start = date(2026, 1, 1)
    for i in range(n_invoices):
        sid, sname, org = rng.choice(suppliers)
        cat = rng.choice(list(CATEGORIES))
        vclass = CATEGORIES[cat]
        net = round(rng.lognormvariate(8.2, 0.9), 2)            # typical invoice ~ 3-4k SEK
        if rng.random() < 0.01:
            net = round(net * rng.uniform(15, 40), 2)            # rare very large invoice
        rate = VAT_RATES[vclass]
        vat = round(net * rate, 2)
        issue = rng.random()
        if issue < 0.03:
            vat = round(net * rng.choice([r for r in VAT_RATES.values() if r != rate]), 2)  # wrong rate applied
        elif issue < 0.05:
            vat = round(vat + rng.choice([-1, 1]) * rng.uniform(5, 200), 2)                   # arithmetic error
        inv_date = start + timedelta(days=rng.randint(0, 272))
        row = {"invoice_id": f"INV-{2026}{i + 1:05d}", "supplier_id": sid, "supplier_name": sname,
               "supplier_org_no": org, "invoice_date": inv_date.isoformat(), "category": cat,
               "vat_class": vclass, "net_amount": f"{net:.2f}", "vat_amount": f"{vat:.2f}",
               "total_amount": f"{net + vat:.2f}", "currency": "SEK"}
        if rng.random() < 0.015:
            row["supplier_org_no"] = ""                          # missing mandatory field
        rows.append(row)
        seen.append(row)
    for _ in range(int(n_invoices * 0.02)):                     # duplicates re-submitted with a new id
        dup = dict(rng.choice(seen))
        dup["invoice_id"] = f"INV-2026D{rng.randint(1000, 9999)}"
        rows.append(dup)
    rng.shuffle(rows)
    path = path or os.path.join(DATA_DIR, "invoices.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


if __name__ == "__main__":
    print(generate())
