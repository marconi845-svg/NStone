"""Persistenza coda azioni, audit policy e bus messaggi agenti su nstonellm.db."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"


def _db_path() -> Path:
    return DEFAULT_DB_PATH


def init_action_tables(db_path: Optional[Path] = None) -> None:
    path = db_path or _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                machine_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                parameter TEXT,
                value TEXT,
                payload_json TEXT,
                status TEXT NOT NULL DEFAULT 'approved',
                policy_level INTEGER,
                result_message TEXT,
                executed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomy_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                level INTEGER,
                action TEXT NOT NULL,
                agent TEXT,
                allowed INTEGER NOT NULL,
                reason TEXT,
                correlation_id TEXT,
                payload_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                msg_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                round_no INTEGER DEFAULT 0,
                payload_json TEXT
            )
            """
        )
        conn.commit()


def log_audit(
    action: str,
    allowed: bool,
    reason: str,
    *,
    level: Optional[int] = None,
    agent: str = "",
    correlation_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> None:
    init_action_tables(db_path)
    ts = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path or _db_path()) as conn:
        conn.execute(
            """
            INSERT INTO autonomy_audit
            (ts, level, action, agent, allowed, reason, correlation_id, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                level,
                action,
                agent,
                1 if allowed else 0,
                reason,
                correlation_id,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        conn.commit()


def enqueue_pending_action(
    machine_id: str,
    suggestion: Dict[str, Any],
    *,
    policy_level: int,
    status: str = "approved",
    result_message: str = "",
    db_path: Optional[Path] = None,
) -> int:
    init_action_tables(db_path)
    ts = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path or _db_path()) as conn:
        cur = conn.execute(
            """
            INSERT INTO pending_actions
            (created_at, machine_id, action_type, parameter, value, payload_json,
             status, policy_level, result_message, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                machine_id,
                str(suggestion.get("action", "")),
                str(suggestion.get("parameter", "")),
                str(suggestion.get("value", "")),
                json.dumps(suggestion, ensure_ascii=False),
                status,
                policy_level,
                result_message,
                ts if result_message else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_recent_pending(limit: int = 20, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    init_action_tables(db_path)
    with sqlite3.connect(db_path or _db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM pending_actions
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_recent_audit(limit: int = 30, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    init_action_tables(db_path)
    with sqlite3.connect(db_path or _db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM autonomy_audit
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_audit_for_action_prefix(
    prefix: str, limit: int = 50, db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Righe audit il cui action inizia con prefix (es. 'plc_write')."""
    init_action_tables(db_path)
    with sqlite3.connect(db_path or _db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM autonomy_audit
            WHERE action LIKE ? || '%'
            ORDER BY id DESC LIMIT ?
            """,
            (prefix, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def audit_stats_for_action_prefix(
    prefix: str, db_path: Optional[Path] = None
) -> Dict[str, int]:
    """Conteggi totale/permesse/rifiutate per un prefisso di action."""
    init_action_tables(db_path)
    with sqlite3.connect(db_path or _db_path()) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(allowed), 0) AS allowed
            FROM autonomy_audit
            WHERE action LIKE ? || '%'
            """,
            (prefix,),
        ).fetchone()
    total = int(row[0] or 0)
    allowed = int(row[1] or 0)
    return {"total": total, "allowed": allowed, "rejected": total - allowed}


def post_agent_message(
    *,
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload: Optional[Dict[str, Any]] = None,
    correlation_id: str = "",
    round_no: int = 0,
    status: str = "new",
    db_path: Optional[Path] = None,
) -> int:
    init_action_tables(db_path)
    ts = datetime.now(timezone.utc).isoformat()
    cid = correlation_id or f"{from_agent}-{to_agent}-{ts}"
    with sqlite3.connect(db_path or _db_path()) as conn:
        cur = conn.execute(
            """
            INSERT INTO agent_messages
            (created_at, correlation_id, from_agent, to_agent, msg_type, status, round_no, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                cid,
                from_agent,
                to_agent,
                msg_type,
                status,
                round_no,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_agent_messages(
    *,
    to_agent: Optional[str] = None,
    status: Optional[str] = "new",
    limit: int = 20,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    init_action_tables(db_path)
    with sqlite3.connect(db_path or _db_path()) as conn:
        conn.row_factory = sqlite3.Row
        if to_agent and status:
            rows = conn.execute(
                """
                SELECT * FROM agent_messages
                WHERE to_agent = ? AND status = ?
                ORDER BY id ASC LIMIT ?
                """,
                (to_agent, status, limit),
            ).fetchall()
        elif to_agent:
            rows = conn.execute(
                """
                SELECT * FROM agent_messages
                WHERE to_agent = ?
                ORDER BY id DESC LIMIT ?
                """,
                (to_agent, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM agent_messages
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def mark_agent_message_done(msg_id: int, db_path: Optional[Path] = None) -> None:
    init_action_tables(db_path)
    with sqlite3.connect(db_path or _db_path()) as conn:
        conn.execute(
            "UPDATE agent_messages SET status = 'done' WHERE id = ?",
            (msg_id,),
        )
        conn.commit()


def list_recent_agent_messages(limit: int = 25, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    return list_agent_messages(to_agent=None, status=None, limit=limit, db_path=db_path)
