"""
Registro compliance AI: profilo titolare, checklist, presa visione lavoratori.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.ai_compliance_catalog import REQUIREMENTS, CheckStatus

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"

PROFILE_ID = 1

TABLE_PROFILE = """
CREATE TABLE IF NOT EXISTS compliance_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    employer_name TEXT NOT NULL DEFAULT '',
    employer_vat TEXT NOT NULL DEFAULT '',
    dpo_name TEXT NOT NULL DEFAULT '',
    dpo_email TEXT NOT NULL DEFAULT '',
    workplace_site TEXT NOT NULL DEFAULT '',
    ai_system_name TEXT NOT NULL DEFAULT 'NStone',
    ai_system_version TEXT NOT NULL DEFAULT '',
    legal_rep_name TEXT NOT NULL DEFAULT '',
    processing_purposes TEXT NOT NULL DEFAULT '',
    legal_basis TEXT NOT NULL DEFAULT 'Legittimo interesse / esecuzione contratto (art. 6 GDPR)',
    retention_days INTEGER NOT NULL DEFAULT 365,
    llm_provider_note TEXT NOT NULL DEFAULT '',
    worker_notice_version TEXT NOT NULL DEFAULT '1.0',
    worker_notice_published_at TEXT NOT NULL DEFAULT '',
    dpia_completed INTEGER NOT NULL DEFAULT 0,
    dpia_reviewed_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT
)
"""

TABLE_CHECKLIST = """
CREATE TABLE IF NOT EXISTS compliance_checklist (
    req_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'open',
    evidence_note TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    updated_by TEXT NOT NULL DEFAULT ''
)
"""

TABLE_ACK = """
CREATE TABLE IF NOT EXISTS compliance_worker_ack (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_name TEXT NOT NULL,
    worker_role TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    notice_version TEXT NOT NULL,
    acknowledged_at TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'in_app',
    notes TEXT NOT NULL DEFAULT ''
)
"""


def get_database_path() -> Path:
    return DEFAULT_DB_PATH


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_compliance_tables(*, db_path: Optional[Path] = None) -> Path:
    path = db_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        _configure_connection(conn)
        conn.execute(TABLE_PROFILE)
        conn.execute(TABLE_CHECKLIST)
        conn.execute(TABLE_ACK)
        conn.execute(
            """
            INSERT OR IGNORE INTO compliance_profile (id) VALUES (?)
            """,
            (PROFILE_ID,),
        )
        for req in REQUIREMENTS:
            conn.execute(
                """
                INSERT OR IGNORE INTO compliance_checklist (req_id, status)
                VALUES (?, 'open')
                """,
                (req.req_id,),
            )
        conn.commit()
    return path


def load_compliance_profile(*, db_path: Optional[Path] = None) -> Dict[str, Any]:
    path = ensure_compliance_tables(db_path=db_path)
    with sqlite3.connect(path) as conn:
        _configure_connection(conn)
        row = conn.execute(
            "SELECT * FROM compliance_profile WHERE id = ?",
            (PROFILE_ID,),
        ).fetchone()
    if not row:
        return {}
    return dict(row)


def save_compliance_profile(fields: Dict[str, Any], *, db_path: Optional[Path] = None) -> None:
    path = ensure_compliance_tables(db_path=db_path)
    allowed = {
        "employer_name",
        "employer_vat",
        "dpo_name",
        "dpo_email",
        "workplace_site",
        "ai_system_name",
        "ai_system_version",
        "legal_rep_name",
        "processing_purposes",
        "legal_basis",
        "retention_days",
        "llm_provider_note",
        "worker_notice_version",
        "worker_notice_published_at",
        "dpia_completed",
        "dpia_reviewed_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now_iso()
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values())
    with sqlite3.connect(path) as conn:
        _configure_connection(conn)
        conn.execute(
            f"UPDATE compliance_profile SET {cols} WHERE id = ?",
            (*vals, PROFILE_ID),
        )
        conn.commit()


def publish_worker_notice(*, version: str, db_path: Optional[Path] = None) -> None:
    save_compliance_profile(
        {
            "worker_notice_version": version.strip() or "1.0",
            "worker_notice_published_at": _now_iso(),
        },
        db_path=db_path,
    )


def load_checklist_items(*, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = ensure_compliance_tables(db_path=db_path)
    with sqlite3.connect(path) as conn:
        _configure_connection(conn)
        rows = conn.execute(
            "SELECT * FROM compliance_checklist ORDER BY req_id"
        ).fetchall()
    return [dict(r) for r in rows]


def update_checklist_item(
    req_id: str,
    status: CheckStatus,
    evidence_note: str = "",
    updated_by: str = "",
    *,
    db_path: Optional[Path] = None,
) -> None:
    path = ensure_compliance_tables(db_path=db_path)
    with sqlite3.connect(path) as conn:
        _configure_connection(conn)
        conn.execute(
            """
            UPDATE compliance_checklist
            SET status = ?, evidence_note = ?, updated_at = ?, updated_by = ?
            WHERE req_id = ?
            """,
            (status, evidence_note.strip(), _now_iso(), updated_by.strip(), req_id),
        )
        conn.commit()


def insert_worker_acknowledgment(
    worker_name: str,
    notice_version: str,
    *,
    worker_role: str = "",
    user_id: Optional[int] = None,
    method: str = "in_app",
    notes: str = "",
    db_path: Optional[Path] = None,
) -> int:
    path = ensure_compliance_tables(db_path=db_path)
    name = (worker_name or "").strip()
    if not name:
        raise ValueError("worker_name required")
    with sqlite3.connect(path) as conn:
        _configure_connection(conn)
        cur = conn.execute(
            """
            INSERT INTO compliance_worker_ack
            (worker_name, worker_role, user_id, notice_version, acknowledged_at, method, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                worker_role.strip(),
                user_id,
                notice_version.strip() or "1.0",
                _now_iso(),
                method.strip() or "in_app",
                notes.strip(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_worker_acknowledgments(
    limit: int = 100,
    *,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    path = ensure_compliance_tables(db_path=db_path)
    with sqlite3.connect(path) as conn:
        _configure_connection(conn)
        rows = conn.execute(
            """
            SELECT * FROM compliance_worker_ack
            ORDER BY id DESC LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
    return [dict(r) for r in rows]
