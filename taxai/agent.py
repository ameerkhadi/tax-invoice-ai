"""A small 'tax data assistant' agent: plain-language question -> safe SQL -> answer with the query shown.

Two planners:
  * RulePlanner (default, offline, deterministic): maps common review questions to vetted SQL templates.
  * LLMPlanner (optional): if ANTHROPIC_API_KEY is set, an LLM writes SQL from the schema; the SQL then goes
    through the same guardrails (single read-only SELECT, read-only connection, row limit).
Every answer returns the SQL it ran, so a reviewer can audit it.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request

SCHEMA_DOC = """invoice(invoice_id, supplier_id, supplier_name, supplier_org_no, invoice_date, month 'YYYY-MM',
category, vat_class in ('standard','reduced_1','reduced_2','exempt'), net_amount, vat_amount, total_amount)
issue(invoice_id, rule in ('missing_field','invalid_org_number','vat_mismatch','total_mismatch','possible_duplicate',
'unusually_large'), severity in ('high','medium','low'), detail)
view vat_by_month(month, vat_class, net, vat, n)"""

TEMPLATES = [
    (r"(vat|moms).*(month|monthly|per month)|monthly.*vat",
     "VAT per month", "SELECT month, ROUND(SUM(vat),2) AS vat_sek, SUM(n) AS invoices FROM vat_by_month GROUP BY month ORDER BY month"),
    (r"(vat|moms).*(class|rate|category)",
     "VAT by VAT class", "SELECT vat_class, ROUND(SUM(net),2) AS net_sek, ROUND(SUM(vat),2) AS vat_sek FROM vat_by_month GROUP BY vat_class ORDER BY vat_sek DESC"),
    (r"duplicate",
     "Possible duplicate invoices", "SELECT i.invoice_id, i.detail, v.supplier_name, v.total_amount FROM issue i JOIN invoice v USING(invoice_id) WHERE rule='possible_duplicate' ORDER BY v.total_amount DESC"),
    (r"(wrong|incorrect|mismatch|error).*(vat|moms)|vat.*(wrong|error|mismatch)",
     "Invoices with VAT errors", "SELECT i.invoice_id, v.supplier_name, v.vat_class, v.net_amount, v.vat_amount, i.detail FROM issue i JOIN invoice v USING(invoice_id) WHERE rule='vat_mismatch' ORDER BY ABS(v.vat_amount) DESC"),
    (r"(org|organisation|organization).*(number|nr)|luhn",
     "Invalid or missing organisation numbers", "SELECT i.invoice_id, i.rule, i.detail, v.supplier_name FROM issue i LEFT JOIN invoice v USING(invoice_id) WHERE rule IN ('invalid_org_number','missing_field')"),
    (r"(top|largest|biggest).*(supplier|vendor)|supplier.*(spend|most)",
     "Top suppliers by spend", "SELECT supplier_name, COUNT(*) AS invoices, ROUND(SUM(total_amount),2) AS total_sek FROM invoice GROUP BY supplier_id ORDER BY total_sek DESC LIMIT 10"),
    (r"(risk|riskiest|issues).*(supplier|vendor)|supplier.*(risk|issues)",
     "Suppliers with most issues", "SELECT v.supplier_name, COUNT(*) AS issues, SUM(i.severity='high') AS high FROM issue i JOIN invoice v USING(invoice_id) GROUP BY v.supplier_id ORDER BY high DESC, issues DESC LIMIT 10"),
    (r"(summary|overview|how many|total)",
     "Review summary", "SELECT rule, severity, COUNT(*) AS n FROM issue GROUP BY rule, severity ORDER BY n DESC"),
]

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace|vacuum)\b", re.I)


def guard(sql: str, limit: int = 200) -> str:
    s = sql.strip().rstrip(";")
    if ";" in s or not re.match(r"(?is)^\s*(select|with)\b", s) or FORBIDDEN.search(s):
        raise ValueError("only a single read-only SELECT is allowed")
    return s if re.search(r"(?i)\blimit\s+\d+", s) else f"{s} LIMIT {limit}"


class RulePlanner:
    def plan(self, question: str) -> tuple[str, str]:
        q = question.lower()
        for pattern, title, sql in TEMPLATES:
            if re.search(pattern, q):
                return title, sql
        raise LookupError("I can answer questions about VAT per month/class, VAT errors, duplicates, "
                          "organisation numbers, top or risky suppliers, or a review summary.")


class LLMPlanner:
    """Optional: uses Claude to write SQL from the schema. Output is still guarded and audited."""
    def __init__(self, model: str = "claude-sonnet-5-5"):
        self.key, self.model = os.environ.get("ANTHROPIC_API_KEY"), model

    def plan(self, question: str) -> tuple[str, str]:
        body = {"model": self.model, "max_tokens": 400, "messages": [{"role": "user", "content":
                f"SQLite schema:\n{SCHEMA_DOC}\nWrite ONE read-only SQLite SELECT answering: {question}\n"
                "Return only the SQL."}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                                              "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            sql = json.loads(r.read())["content"][0]["text"]
        return "LLM-generated query", re.sub(r"^```\w*|```$", "", sql.strip(), flags=re.M).strip()


def ask(question: str, db_path: str, planner=None) -> dict:
    planner = planner or (LLMPlanner() if os.environ.get("ANTHROPIC_API_KEY") else RulePlanner())
    title, sql = planner.plan(question)
    sql = guard(sql)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # read-only connection
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()
    return {"question": question, "answer_title": title, "sql": sql, "columns": cols, "rows": rows}
