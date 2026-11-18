"""
Section access passwords stored in SQLite (data/nstonellm.db → section_password).

Manages PIN protection for restricted UI sections and administrator bypass.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agents_config import hash_pin, verify_pin

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"

SECTION_AGENTS_COMMAND_CENTER = "agents_command_center"
SECTION_ADVANCED_DATASET_OPTIONS = "advanced_dataset_options"
SECTION_ADMINISTRATOR_BYPASS = "administrator_bypass"

DEFAULT_ROWS = (
    {
        "section_key": SECTION_AGENTS_COMMAND_CENTER,
        "display_name": "Agents Command Center",
    },
    {
        "section_key": SECTION_ADVANCED_DATASET_OPTIONS,
        "display_name": "Advanced Dataset Options",
    },
    {
        "section_key": SECTION_ADMINISTRATOR_BYPASS,
        "display_name": "Administrator — disable section passwords",
    },
)

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS section_password (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL DEFAULT '',
    protection_enabled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)
"""


class AccessControlError(Exception):
    pass


def get_database_path() -> Path:
    return DEFAULT_DB_PATH


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "section_key": row["section_key"],
        "display_name": row["display_name"],
        "password_hash": row["password_hash"] or "",
        "protection_enabled": bool(row["protection_enabled"]),
        "updated_at": row["updated_at"] or "",
        "is_admin_bypass": row["section_key"] == SECTION_ADMINISTRATOR_BYPASS,
        "password_set": bool((row["password_hash"] or "").strip()),
    }


def _migrate_legacy_agents_pin(conn: sqlite3.Connection) -> None:
    """Copy config.json admin_pin_hash into DB if the agents row has no password yet."""
    try:
        from core.machine_plc_config import load_config

        pin_hash = (load_config().get("autonomy") or {}).get("admin_pin_hash") or ""
        if not pin_hash:
            return
        row = conn.execute(
            "SELECT password_hash, protection_enabled FROM section_password WHERE section_key = ?",
            (SECTION_AGENTS_COMMAND_CENTER,),
        ).fetchone()
        if row and not (row["password_hash"] or "").strip():
            conn.execute(
                """
                UPDATE section_password
                SET password_hash = ?, protection_enabled = 1, updated_at = ?
                WHERE section_key = ?
                """,
                (pin_hash.strip(), _now_iso(), SECTION_AGENTS_COMMAND_CENTER),
            )
    except Exception as exc:
        logger.debug("Legacy PIN migration skipped: %s", exc)


def ensure_section_password_table(*, db_path: Optional[Path] = None) -> Path:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        conn.execute(TABLE_SQL)
        for row in DEFAULT_ROWS:
            conn.execute(
                """
                INSERT OR IGNORE INTO section_password (section_key, display_name)
                VALUES (?, ?)
                """,
                (row["section_key"], row["display_name"]),
            )
        _migrate_legacy_agents_pin(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def is_access_control_editable(*, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    if not path.exists():
        return False
    try:
        ensure_section_password_table(db_path=path)
        return True
    except sqlite3.Error:
        return False


def load_section_password_records(*, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = ensure_section_password_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        rows = conn.execute(
            """
            SELECT id, section_key, display_name, password_hash, protection_enabled, updated_at
            FROM section_password
            ORDER BY
                CASE section_key
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                id
            """,
            (SECTION_AGENTS_COMMAND_CENTER, SECTION_ADVANCED_DATASET_OPTIONS),
        ).fetchall()
        return [_row_to_record(row) for row in rows]
    finally:
        conn.close()


def get_section_record(
    section_key: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    path = ensure_section_password_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        row = conn.execute(
            """
            SELECT id, section_key, display_name, password_hash, protection_enabled, updated_at
            FROM section_password WHERE section_key = ?
            """,
            (section_key,),
        ).fetchone()
        return _row_to_record(row) if row else None
    finally:
        conn.close()


def is_admin_bypass_enabled(*, db_path: Optional[Path] = None) -> bool:
    rec = get_section_record(SECTION_ADMINISTRATOR_BYPASS, db_path=db_path)
    return bool(rec and rec["protection_enabled"])


def section_requires_pin(section_key: str, *, db_path: Optional[Path] = None) -> bool:
    if section_key == SECTION_ADMINISTRATOR_BYPASS:
        return False
    if is_admin_bypass_enabled(db_path=db_path):
        return False
    rec = get_section_record(section_key, db_path=db_path)
    if not rec:
        return False
    return bool(rec["protection_enabled"] and rec["password_hash"])


def verify_section_pin(
    section_key: str,
    pin: str,
    *,
    db_path: Optional[Path] = None,
) -> bool:
    rec = get_section_record(section_key, db_path=db_path)
    if not rec or not (rec["password_hash"] or "").strip():
        return not section_requires_pin(section_key, db_path=db_path)
    return verify_pin(pin, rec["password_hash"])


def update_section_access(
    record_id: int,
    *,
    protection_enabled: bool,
    new_password: str = "",
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        rid = int(record_id)
        path = ensure_section_password_table(db_path=db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            row = conn.execute(
                "SELECT section_key, password_hash FROM section_password WHERE id = ?",
                (rid,),
            ).fetchone()
            if not row:
                raise AccessControlError(f"Record id={rid} not found")

            section_key = row["section_key"]
            password_hash = row["password_hash"] or ""

            if section_key != SECTION_ADMINISTRATOR_BYPASS:
                clean_pin = (new_password or "").strip()
                if clean_pin:
                    password_hash = hash_pin(clean_pin)
                elif protection_enabled and not password_hash:
                    raise AccessControlError(
                        "Set a password before enabling protection for this section."
                    )

            conn.execute(
                """
                UPDATE section_password
                SET protection_enabled = ?, password_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (int(protection_enabled), password_hash, _now_iso(), rid),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "id": rid}
    except AccessControlError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.Error as exc:
        logger.error("section_password update failed: %s", exc)
        return {"ok": False, "error": str(exc)}
