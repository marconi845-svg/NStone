#!/usr/bin/env python3
"""Create data/nstonellm.db from SQL schema (+ optional seed). No CSV."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "nstonellm.db"

SCHEMA_FILE = DB_DIR / "schema.sql"
ORDERS_SCHEMA_FILE = DB_DIR / "orders_schema.sql"
SEED_FILE = DB_DIR / "seed.sql"

# Additive columns for core `orders` (orders_schema extension)
ORDERS_EXTRA_COLUMNS = (
    ("email_id", "INTEGER"),
    ("client_email", "TEXT"),
    ("materiale", "TEXT"),
    ("quantita", "REAL"),
    ("email_subject", "TEXT"),
    ("email_body", "TEXT"),
    ("validation_errors", "TEXT"),
)


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _ensure_orders_columns(conn: sqlite3.Connection) -> None:
    cols = _existing_columns(conn, "orders")
    for name, decl in ORDERS_EXTRA_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {decl}")
    # Indexes that need the extended columns
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_email_id ON orders(email_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_client_email ON orders(client_email)"
    )


def init_db(db_path: Path, *, with_seed: bool = True, force: bool = False) -> Path:
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists() and force:
        for suffix in ("", "-wal", "-shm", "-journal"):
            p = Path(str(db_path) + suffix) if suffix else db_path
            if p.exists():
                p.unlink()

    for required in (SCHEMA_FILE, ORDERS_SCHEMA_FILE):
        if not required.exists():
            raise FileNotFoundError(f"Missing SQL schema: {required}")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.executescript(ORDERS_SCHEMA_FILE.read_text(encoding="utf-8"))
        _ensure_orders_columns(conn)
        if with_seed:
            if not SEED_FILE.exists():
                raise FileNotFoundError(f"Missing seed SQL: {SEED_FILE}")
            conn.executescript(SEED_FILE.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize NStone SQLite DB from SQL files"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Output DB path")
    parser.add_argument("--no-seed", action="store_true", help="Apply schema only")
    parser.add_argument("--force", action="store_true", help="Delete existing DB first")
    args = parser.parse_args(argv)

    path = init_db(args.db, with_seed=not args.no_seed, force=args.force)
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
