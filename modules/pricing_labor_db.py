"""
Tariffe lavorazione (taglio, lucidatura, CNC) — materiale sempre da online_stock €/mq.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pricing_labor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    machine TEXT,
    unit TEXT NOT NULL,
    rate_eur REAL NOT NULL,
    min_charge_eur REAL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

DEFAULT_LABOR_ROWS = (
    ("taglio_multifilo", "Taglio multifilo", "multifilo", "per_pezzo", 25.0, 50.0),
    ("lucidatura", "Lucidatura superficie", "lucidatrice", "per_mq", 28.0, 0.0),
    ("foro_cnc", "Foro / sagomatura CNC", "cnc", "per_pezzo", 45.0, 0.0),
    ("bordo_lucidato", "Bordo lucidato / smussato", "lucidatrice", "per_ml", 12.0, 0.0),
    ("levigatura", "Levigatura", "lucidatrice", "per_mq", 22.0, 0.0),
)


def get_database_path() -> Path:
    try:
        from modules.orders_database import get_database_path as orders_db

        return orders_db()
    except Exception:
        return DEFAULT_DB_PATH


def ensure_pricing_labor_table(*, db_path: Optional[Path] = None) -> Path:
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute(TABLE_SQL)
        count = conn.execute("SELECT COUNT(*) FROM pricing_labor").fetchone()[0]
        if count == 0:
            for op, label, machine, unit, rate, min_ch in DEFAULT_LABOR_ROWS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO pricing_labor (
                        operation, label, machine, unit, rate_eur, min_charge_eur
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (op, label, machine, unit, rate, min_ch),
                )
        conn.commit()
    finally:
        conn.close()
    return path


def list_labor_rates(*, active_only: bool = True) -> List[Dict[str, Any]]:
    path = ensure_pricing_labor_table()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT operation, label, machine, unit, rate_eur, min_charge_eur
            FROM pricing_labor
        """
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY operation"
        rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_labor_rate(operation: str) -> Optional[Dict[str, Any]]:
    op = (operation or "").strip().lower()
    if not op:
        return None
    path = ensure_pricing_labor_table()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT operation, label, machine, unit, rate_eur, min_charge_eur
            FROM pricing_labor
            WHERE lower(operation) = ? AND is_active = 1
            LIMIT 1
            """,
            (op,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
