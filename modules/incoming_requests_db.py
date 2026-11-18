"""
Incoming web form requests (Quotations Hub) — SQLite data/nstonellm.db.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"
LEGACY_JSON_PATH = PROJECT_ROOT / "fastapi_backend" / "data" / "messages.json"
_active_db_path: Optional[Path] = None

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS incoming_request (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    nome TEXT NOT NULL,
    email TEXT NOT NULL,
    messaggio TEXT NOT NULL,
    stato TEXT NOT NULL DEFAULT 'NUOVA',
    risposta_gemini TEXT,
    data_elaborazione TEXT,
    email_inviata INTEGER,
    data_invio_email TEXT,
    errore_email TEXT,
    updated_at TEXT
)
"""


class IncomingRequestError(Exception):
    pass


def get_database_path() -> Path:
    return _active_db_path or DEFAULT_DB_PATH


def set_database_path(path: Optional[Path]) -> None:
    global _active_db_path
    _active_db_path = path


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
    msg = {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "nome": row["nome"],
        "email": row["email"],
        "messaggio": row["messaggio"],
        "stato": row["stato"] or "NUOVA",
    }
    if row["risposta_gemini"]:
        msg["risposta_gemini"] = row["risposta_gemini"]
    if row["data_elaborazione"]:
        msg["data_elaborazione"] = row["data_elaborazione"]
    if row["email_inviata"] is not None:
        msg["email_inviata"] = bool(row["email_inviata"])
    if row["data_invio_email"]:
        msg["data_invio_email"] = row["data_invio_email"]
    if row["errore_email"]:
        msg["errore_email"] = row["errore_email"]
    keys = row.keys()
    if "linked_order_id" in keys and row["linked_order_id"]:
        msg["linked_order_id"] = row["linked_order_id"]
    return msg


def _import_legacy_json(conn: sqlite3.Connection) -> int:
    if not LEGACY_JSON_PATH.exists():
        return 0
    try:
        with open(LEGACY_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        messages = data.get("messages", []) if isinstance(data, dict) else []
        imported = 0
        for msg in messages:
            if not isinstance(msg, dict) or not msg.get("id"):
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO incoming_request (
                    id, timestamp, nome, email, messaggio, stato,
                    risposta_gemini, data_elaborazione, email_inviata,
                    data_invio_email, errore_email, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg["id"],
                    msg.get("timestamp") or _now_iso(),
                    msg.get("nome") or "",
                    msg.get("email") or "",
                    msg.get("messaggio") or "",
                    msg.get("stato") or "NUOVA",
                    msg.get("risposta_gemini"),
                    msg.get("data_elaborazione"),
                    int(bool(msg.get("email_inviata"))) if "email_inviata" in msg else None,
                    msg.get("data_invio_email"),
                    msg.get("errore_email"),
                    _now_iso(),
                ),
            )
            imported += 1
        return imported
    except (OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        logger.warning("Legacy messages.json import skipped: %s", exc)
        return 0


def _migrate_incoming_request_table(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(incoming_request)")}
    if "linked_order_id" not in cols:
        conn.execute("ALTER TABLE incoming_request ADD COLUMN linked_order_id TEXT")


def ensure_incoming_request_table(*, db_path: Optional[Path] = None) -> Path:
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        conn.execute(TABLE_SQL)
        _migrate_incoming_request_table(conn)
        count = conn.execute("SELECT COUNT(*) FROM incoming_request").fetchone()[0]
        if count == 0 and path.resolve() == DEFAULT_DB_PATH.resolve():
            _import_legacy_json(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def list_incoming_requests(*, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = ensure_incoming_request_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, nome, email, messaggio, stato,
                   risposta_gemini, data_elaborazione, email_inviata,
                   data_invio_email, errore_email, linked_order_id
            FROM incoming_request
            ORDER BY timestamp DESC
            """
        ).fetchall()
        return [_row_to_message(row) for row in rows]
    finally:
        conn.close()


def get_incoming_request(
    request_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    path = ensure_incoming_request_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        row = conn.execute(
            """
            SELECT id, timestamp, nome, email, messaggio, stato,
                   risposta_gemini, data_elaborazione, email_inviata,
                   data_invio_email, errore_email, linked_order_id
            FROM incoming_request WHERE id = ?
            """,
            (request_id,),
        ).fetchone()
        return _row_to_message(row) if row else None
    finally:
        conn.close()


def insert_incoming_request(
    message: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        path = ensure_incoming_request_table(db_path=db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            conn.execute(
                """
                INSERT INTO incoming_request (
                    id, timestamp, nome, email, messaggio, stato, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message["id"],
                    message.get("timestamp") or _now_iso(),
                    message.get("nome") or "",
                    message.get("email") or "",
                    message.get("messaggio") or "",
                    message.get("stato") or "NUOVA",
                    _now_iso(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "id": message["id"]}
    except sqlite3.Error as exc:
        logger.error("insert incoming_request failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def update_incoming_request(
    request_id: str,
    fields: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    allowed = {
        "nome",
        "email",
        "messaggio",
        "stato",
        "risposta_gemini",
        "data_elaborazione",
        "email_inviata",
        "data_invio_email",
        "errore_email",
        "linked_order_id",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return {"ok": False, "error": "No valid fields to update"}
    try:
        path = ensure_incoming_request_table(db_path=db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            existing = conn.execute(
                "SELECT id FROM incoming_request WHERE id = ?",
                (request_id,),
            ).fetchone()
            if not existing:
                return {"ok": False, "error": f"Request {request_id} not found"}
            set_parts = []
            values: List[Any] = []
            for key, value in updates.items():
                if key == "email_inviata":
                    value = int(bool(value))
                set_parts.append(f"{key} = ?")
                values.append(value)
            set_parts.append("updated_at = ?")
            values.append(_now_iso())
            values.append(request_id)
            conn.execute(
                f"UPDATE incoming_request SET {', '.join(set_parts)} WHERE id = ?",
                values,
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "id": request_id}
    except sqlite3.Error as exc:
        logger.error("update incoming_request failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def delete_incoming_request(
    request_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        path = ensure_incoming_request_table(db_path=db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            cursor = conn.execute(
                "DELETE FROM incoming_request WHERE id = ?",
                (request_id,),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return {"ok": False, "error": f"Request {request_id} not found"}
        finally:
            conn.close()
        return {"ok": True, "id": request_id}
    except sqlite3.Error as exc:
        logger.error("delete incoming_request failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def replace_all_incoming_requests(
    messages: List[Dict[str, Any]],
    *,
    db_path: Optional[Path] = None,
) -> bool:
    """Legacy helper — prefer insert/update/delete."""
    try:
        path = ensure_incoming_request_table(db_path=db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            conn.execute("DELETE FROM incoming_request")
            for msg in messages:
                conn.execute(
                    """
                    INSERT INTO incoming_request (
                        id, timestamp, nome, email, messaggio, stato,
                        risposta_gemini, data_elaborazione, email_inviata,
                        data_invio_email, errore_email, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg["id"],
                        msg.get("timestamp") or _now_iso(),
                        msg.get("nome") or "",
                        msg.get("email") or "",
                        msg.get("messaggio") or "",
                        msg.get("stato") or "NUOVA",
                        msg.get("risposta_gemini"),
                        msg.get("data_elaborazione"),
                        int(bool(msg.get("email_inviata"))) if "email_inviata" in msg else None,
                        msg.get("data_invio_email"),
                        msg.get("errore_email"),
                        _now_iso(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        return True
    except sqlite3.Error as exc:
        logger.error("replace_all incoming_request failed: %s", exc)
        return False
