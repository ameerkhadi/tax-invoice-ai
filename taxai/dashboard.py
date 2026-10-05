"""Static BI dashboard (HTML + Chart.js), the same views a Power BI report would show."""
from __future__ import annotations

import html
import json
import os
import sqlite3

from .agent import ask
from .config import OUT_DIR


def build(db_path: str = os.path.join(OUT_DIR, "tax.db"), out: str = os.path.join(OUT_DIR, "dashboard.html")) -> str:
    con = sqlite3.connect(db_path)
    q = lambda s: con.execute(s).fetchall()
    n, net, vat = q("SELECT COUNT(*), SUM(net_amount), SUM(vat_amount) FROM invoice")[0]
    flagged = q("SELECT COUNT(DISTINCT invoice_id) FROM issue")[0][0]
    high = q("SELECT COUNT(*) FROM issue WHERE severity='high'")[0][0]
    months = q("SELECT month, ROUND(SUM(vat),0) FROM vat_by_month GROUP BY month ORDER BY month")
    classes = q("SELECT vat_class, ROUND(SUM(vat),0) FROM vat_by_month GROUP BY vat_class ORDER BY 2 DESC")
    rules = q("SELECT rule, COUNT(*) FROM issue GROUP BY rule ORDER BY 2 DESC")
    con.close()
    qa = ask("Which invoices have wrong VAT?", db_path)
    qa_rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in qa["rows"][:6])
    qa_head = "".join(f"<th>{c}</th>" for c in qa["columns"])
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>VAT Review Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f6f9;color:#1d2433;margin:22px}}h1{{color:#0b3c6e;margin:0}}
.sub{{color:#5b6573;margin:4px 0 16px}}.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}
.k{{background:#fff;border-radius:10px;padding:12px 14px;border:1px solid #e3e1da}}.k b{{font-size:22px;display:block;color:#0b3c6e}}
.grid{{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:12px;margin-top:12px}}.c{{background:#fff;border-radius:10px;padding:12px;border:1px solid #e3e1da}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}td,th{{border-bottom:1px solid #eee;padding:5px;text-align:left}}
code{{background:#eef2f7;padding:2px 6px;border-radius:4px;font-size:12px}}.warn{{color:#b23b3b}}</style></head><body>
<h1>VAT Review Dashboard</h1><div class="sub">Synthetic supplier invoices 2026 · Python ETL + rule engine + SQL model ·
Excel export · AI assistant with auditable SQL · rates are configurable examples, not tax advice</div>
<div class="kpis"><div class="k">Invoices<b>{n:,}</b></div><div class="k">Net amount (SEK)<b>{net:,.0f}</b></div>
<div class="k">VAT (SEK)<b>{vat:,.0f}</b></div><div class="k">Invoices flagged<b class="warn">{flagged}</b></div>
<div class="k">High-severity issues<b class="warn">{high}</b></div></div>
<div class="grid"><div class="c"><b>VAT per month (SEK)</b><canvas id="m"></canvas></div>
<div class="c"><b>VAT by class</b><canvas id="v"></canvas></div><div class="c"><b>Issues by rule</b><canvas id="r"></canvas></div></div>
<div class="c" style="margin-top:12px"><b>Ask the data:</b> “{html.escape(qa['question'])}” → {html.escape(qa['answer_title'])}
({len(qa['rows'])} rows)<br><code>{html.escape(qa['sql'])}</code><table><tr>{qa_head}</tr>{qa_rows}</table></div>
<script>
const M={json.dumps(months)},V={json.dumps(classes)},R={json.dumps(rules)};
new Chart(m,{{type:'bar',data:{{labels:M.map(x=>x[0]),datasets:[{{data:M.map(x=>x[1]),backgroundColor:'#0b3c6e'}}]}},options:{{plugins:{{legend:{{display:false}}}}}}}});
new Chart(v,{{type:'doughnut',data:{{labels:V.map(x=>x[0]),datasets:[{{data:V.map(x=>x[1]),backgroundColor:['#0b3c6e','#5b8cc8','#e9a23b','#c9d3de']}}]}}}});
new Chart(r,{{type:'bar',data:{{labels:R.map(x=>x[0]),datasets:[{{data:R.map(x=>x[1]),backgroundColor:'#b23b3b'}}]}},options:{{indexAxis:'y',plugins:{{legend:{{display:false}}}}}}}});
</script></body></html>"""
    open(out, "w", encoding="utf-8").write(page)
    return out


if __name__ == "__main__":
    print(build())
