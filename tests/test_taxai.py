import os
import sqlite3

import pytest

from taxai import generate, pipeline
from taxai.agent import ask, guard
from taxai.validate import luhn_ok, validate


def test_luhn():
    assert luhn_ok("5560360793")       # valid example number (Luhn passes)
    assert not luhn_ok("5560360794")
    assert not luhn_ok("123")


def test_vat_rules_detect_wrong_rate_and_duplicates():
    base = dict(invoice_id="A", supplier_id="S1", supplier_name="X", supplier_org_no="556036-0793",
                invoice_date="2026-01-10", category="IT services", vat_class="standard",
                net_amount="1000.00", vat_amount="120.00", total_amount="1120.00", currency="SEK")
    dup = dict(base, invoice_id="B")
    issues = validate([base, dup])
    rules = {(i[0], i[1]) for i in issues}
    assert ("A", "vat_mismatch") in rules and ("B", "possible_duplicate") in rules
    assert "reduced_1" in next(i[3] for i in issues if i[1] == "vat_mismatch")
    # a small arithmetic error must not be reported as the invoice's own rate
    near = dict(base, invoice_id="C", supplier_id="S9", vat_amount="252.00", total_amount="1252.00")
    d = next(i[3] for i in validate([near]) if i[1] == "vat_mismatch")
    assert "looks like" not in d and "diff" in d


def test_pipeline_and_excel(tmp_path):
    csv_path = generate.generate(path=str(tmp_path / "inv.csv"))
    rows = pipeline.load_csv(csv_path)
    db = str(tmp_path / "t.db")
    issues = pipeline.build_db(rows, db)
    assert len(rows) > 600 and len(issues) > 20
    found = {i[1] for i in issues}
    assert {"vat_mismatch", "possible_duplicate", "invalid_org_number", "missing_field"} <= found
    x = pipeline.excel_report(db, str(tmp_path / "r.xlsx"))
    assert os.path.getsize(x) > 5000


def test_agent_answers_and_guardrails(tmp_path):
    csv_path = generate.generate(path=str(tmp_path / "inv.csv"))
    db = str(tmp_path / "t.db")
    pipeline.build_db(pipeline.load_csv(csv_path), db)
    a = ask("Which invoices have wrong VAT?", db)
    assert a["rows"] and "vat_mismatch" in a["sql"]
    assert ask("show VAT per month", db)["columns"][0] == "month"
    with pytest.raises(ValueError):
        guard("DELETE FROM invoice")
    with pytest.raises(ValueError):
        guard("SELECT 1; DROP TABLE invoice")
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM invoice").fetchone()[0] > 0
