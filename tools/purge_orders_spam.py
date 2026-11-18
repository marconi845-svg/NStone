"""Rimuove ordini-spazzatura (Amazon, job alert) dal DB. Uso: python tools/purge_orders_spam.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from modules.orders_database import delete_orders_not_visible_in_table, init_database

    init_database()
    n = delete_orders_not_visible_in_table()
    print(f"Eliminati {n} ordini non validi per la tabella Ordini.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
