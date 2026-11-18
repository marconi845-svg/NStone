"""
Email thread turns for quotation cases (incoming_request).
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.incoming_requests_db import ensure_incoming_request_table, get_database_path

logger = logging.getLogger(__name__)

TURN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS quotation_email_turn (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    message_id TEXT,
    in_reply_to TEXT,
    email_references TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'email',
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES incoming_request(id)
)
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_qet_case_id ON quotation_email_turn(case_id)",
    "CREATE INDEX IF NOT EXISTS idx_qet_message_id ON quotation_email_turn(message_id)",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _configure(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row


def ensure_quotation_email_tables(*, db_path: Optional[Path] = None) -> Path:
    path = ensure_incoming_request_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure(conn)
    try:
        conn.execute(TURN_TABLE_SQL)
        for stmt in INDEX_SQL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    return path


def _row_to_turn(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "direction": row["direction"],
        "message_id": row["message_id"],
        "in_reply_to": row["in_reply_to"],
        "email_references": row["email_references"],
        "subject": row["subject"],
        "body": row["body"],
        "source": row["source"],
        "created_at": row["created_at"],
    }


def insert_turn(
    *,
    case_id: str,
    direction: str,
    body: str,
    subject: str = "",
    message_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    email_references: Optional[str] = None,
    source: str = "email",
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = ensure_quotation_email_tables(db_path=db_path)
    turn_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure(conn)
    try:
        conn.execute(
            """
            INSERT INTO quotation_email_turn (
                id, case_id, direction, message_id, in_reply_to,
                email_references, subject, body, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                case_id,
                direction,
                message_id,
                in_reply_to,
                email_references,
                subject,
                body,
                source,
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "id": turn_id, "message_id": message_id}


def list_turns_for_case(
    case_id: str,
    *,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    path = ensure_quotation_email_tables(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure(conn)
    try:
        rows = conn.execute(
            """
            SELECT id, case_id, direction, message_id, in_reply_to,
                   email_references, subject, body, source, created_at
            FROM quotation_email_turn
            WHERE case_id = ?
            ORDER BY created_at ASC
            """,
            (case_id,),
        ).fetchall()
        return [_row_to_turn(row) for row in rows]
    finally:
        conn.close()


def turn_exists_by_message_id(
    message_id: str,
    *,
    db_path: Optional[Path] = None,
) -> bool:
    mid = (message_id or "").strip()
    if not mid:
        return False
    path = ensure_quotation_email_tables(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure(conn)
    try:
        row = conn.execute(
            "SELECT 1 FROM quotation_email_turn WHERE message_id = ? LIMIT 1",
            (mid,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def find_case_id_by_message_id(
    message_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[str]:
    mid = (message_id or "").strip().strip("<>").lower()
    if not mid:
        return None
    path = ensure_quotation_email_tables(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure(conn)
    try:
        row = conn.execute(
            """
            SELECT case_id FROM quotation_email_turn
            WHERE lower(replace(replace(message_id, '<', ''), '>', '')) = ?
            LIMIT 1
            """,
            (mid,),
        ).fetchone()
        return row["case_id"] if row else None
    finally:
        conn.close()


def find_case_id_by_token_prefix(
    token8: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[str]:
    prefix = (token8 or "").strip().lower()
    if len(prefix) != 8:
        return None
    path = ensure_incoming_request_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure(conn)
    try:
        row = conn.execute(
            """
            SELECT id FROM incoming_request
            WHERE lower(substr(replace(id, '-', ''), 1, 8)) = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (prefix,),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def find_open_case_for_email(
    client_email: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[str]:
    email = (client_email or "").strip().lower()
    if not email or "@" not in email:
        return None
    path = ensure_incoming_request_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure(conn)
    try:
        row = conn.execute(
            """
            SELECT id FROM incoming_request
            WHERE lower(email) = ?
              AND stato IN ('OFFERTA_INVIATA', 'IN_CONVERSAZIONE', 'ELABORATA')
              AND COALESCE(email_inviata, 0) = 1
            ORDER BY COALESCE(data_invio_email, timestamp) DESC
            LIMIT 1
            """,
            (email,),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_all_outbound_message_ids(
    case_id: str,
    *,
    db_path: Optional[Path] = None,
) -> List[str]:
    turns = list_turns_for_case(case_id, db_path=db_path)
    return [
        t["message_id"]
        for t in turns
        if t.get("direction") == "outbound" and t.get("message_id")
    ]
