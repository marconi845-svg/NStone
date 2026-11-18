"""Elimina dalla tabella orders le righe create per errore dal poll IMAP (Indeed, alert, ecc.)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.orders_database import (  # noqa: E402
    delete_orders_not_visible_in_table,
    get_database_path,
    orders_table_visibility_sql,
)


def main() -> int:
    import sqlite3

    db = get_database_path()
    conn = sqlite3.connect(str(db))
    total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    vis = orders_table_visibility_sql()
    visible = conn.execute(f"SELECT COUNT(*) FROM orders WHERE 1=1 {vis}").fetchone()[0]
    conn.close()

    print(f"Prima: {total} righe totali, {visible} visibili in GUI")
    deleted = delete_orders_not_visible_in_table()
    print(f"Eliminate: {deleted}")

    conn = sqlite3.connect(str(db))
    total_after = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    visible_after = conn.execute(f"SELECT COUNT(*) FROM orders WHERE 1=1 {vis}").fetchone()[0]
    conn.close()
    print(f"Dopo: {total_after} righe totali, {visible_after} visibili in GUI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
