import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "data" / "nstonellm.db"
p = "%ORDINE TEST NSTONELLM%"
conn = sqlite3.connect(str(db))
print("logs", conn.execute(
    "SELECT id, tipo_email, subject FROM email_logs WHERE subject LIKE ? ORDER BY id DESC LIMIT 5",
    (p,),
).fetchall())
print("orders", conn.execute(
    "SELECT order_id, status, email_subject FROM orders WHERE email_subject LIKE ? ORDER BY id DESC LIMIT 5",
    (p,),
).fetchall())
conn.close()
