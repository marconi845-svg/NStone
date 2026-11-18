import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqlite3
from modules.orders_database import (
    get_database_path,
    assign_order_to_machine,
    get_orders_for_machine,
    get_orders_pending_production,
)

db = get_database_path()
conn = sqlite3.connect(str(db))
row = conn.execute(
    "SELECT order_id, status FROM orders ORDER BY id DESC LIMIT 1"
).fetchone()
print("last", row)
if row:
    conn.execute(
        "UPDATE orders SET status='CONFIRMED', machine='' WHERE order_id=?",
        (row[0],),
    )
    conn.commit()
    print("pending", len(get_orders_pending_production()))
    ok, msg = assign_order_to_machine(row[0], "Lucidatrice")
    print("assign", ok, msg)
    print("queue", len(get_orders_for_machine("Lucidatrice")))
conn.close()
