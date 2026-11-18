import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
c = sqlite3.connect(ROOT / "data" / "nstonellm.db")
c.row_factory = sqlite3.Row

print("=== ULTIMI ORDINI (30 min) ===")
for r in c.execute(
    """
    SELECT order_id, status, materiale, quantita, email_subject, client_email,
           created_at, validation_errors
    FROM orders
    WHERE datetime(created_at) >= datetime('now', '-2 hours')
       OR order_id LIKE '20260609%'
       OR order_id LIKE '20260610%'
    ORDER BY id DESC LIMIT 8
    """
):
    d = dict(r)
    ve = d.pop("validation_errors", None)
    print(d)
    if ve:
        try:
            print("  validation:", json.dumps(json.loads(ve), ensure_ascii=False)[:500])
        except Exception:
            print("  validation:", str(ve)[:500])

print("\n=== EMAIL_LOGS recenti ORDINE ===")
for r in c.execute(
    """
    SELECT id, sender, subject, tipo_email, timestamp, order_id
    FROM email_logs
    WHERE tipo_email = 'ORDINE'
    ORDER BY id DESC LIMIT 5
    """
):
    print(dict(r))

print("\n=== PDF recenti ===")
pdf_dir = ROOT / "logs" / "order_confirmations"
if pdf_dir.exists():
    for p in sorted(pdf_dir.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        print(p.name, p.stat().st_size, "bytes")
