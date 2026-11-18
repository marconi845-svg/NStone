"""
Application users and active session (SQLite + config.json session block).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"

ROLE_ADMINISTRATOR = "administrator"
ROLE_OPERATOR = "operator"
VALID_ROLES = (ROLE_ADMINISTRATOR, ROLE_OPERATOR)

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
)
"""


class AppUserError(Exception):
    pass


def get_database_path() -> Path:
    return DEFAULT_DB_PATH


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _row_to_user(row: sqlite3.Row) -> Dict[str, Any]:
    role = (row["role"] or ROLE_OPERATOR).strip().lower()
    if role not in VALID_ROLES:
        role = ROLE_OPERATOR
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "display_name": row["display_name"],
        "role": role,
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
        "is_administrator": role == ROLE_ADMINISTRATOR,
    }


def _load_session_user_id() -> Optional[int]:
    try:
        from core.machine_plc_config import load_config

        raw = (load_config().get("session") or {}).get("current_user_id")
        if raw is None or raw == "":
            return None
        return int(raw)
    except (TypeError, ValueError, ImportError):
        return None


def _save_session_user_id(user_id: Optional[int]) -> None:
    from core.machine_plc_config import save_config

    payload: Dict[str, Any] = {"session": {}}
    if user_id is not None:
        payload["session"]["current_user_id"] = int(user_id)
    else:
        payload["session"]["current_user_id"] = None
    save_config(payload)


def ensure_app_user_table(*, db_path: Optional[Path] = None) -> Path:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        conn.execute(TABLE_SQL)
        count = conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0]
        if count == 0:
            now = _now_iso()
            conn.execute(
                """
                INSERT INTO app_user (username, display_name, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                ("administrator", "Administrator", ROLE_ADMINISTRATOR, now, now),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def is_app_users_editable(*, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    if not path.exists():
        return False
    try:
        ensure_app_user_table(db_path=path)
        return True
    except sqlite3.Error:
        return False


def load_app_users(
    *,
    active_only: bool = False,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    path = ensure_app_user_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        sql = """
            SELECT id, username, display_name, role, is_active, created_at, updated_at
            FROM app_user
        """
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY display_name COLLATE NOCASE, username COLLATE NOCASE"
        rows = conn.execute(sql).fetchall()
        return [_row_to_user(row) for row in rows]
    finally:
        conn.close()


def get_app_user_by_id(
    user_id: int,
    *,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    path = ensure_app_user_table(db_path=db_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    try:
        row = conn.execute(
            """
            SELECT id, username, display_name, role, is_active, created_at, updated_at
            FROM app_user WHERE id = ?
            """,
            (int(user_id),),
        ).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def get_current_user(*, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    uid = _load_session_user_id()
    if uid is not None:
        user = get_app_user_by_id(uid, db_path=db_path)
        if user and user["is_active"]:
            return user
    active = load_app_users(active_only=True, db_path=db_path)
    if not active:
        return None
    set_current_user(active[0]["id"], db_path=db_path)
    return active[0]


def set_current_user(user_id: int, *, db_path: Optional[Path] = None) -> Dict[str, Any]:
    try:
        uid = int(user_id)
        user = get_app_user_by_id(uid, db_path=db_path)
        if not user:
            raise AppUserError(f"User id={uid} not found")
        if not user["is_active"]:
            raise AppUserError("Cannot set an inactive user as active session")
        _save_session_user_id(uid)
        return {"ok": True, "user": user}
    except AppUserError as exc:
        return {"ok": False, "error": str(exc)}


def current_user_banner_text(*, db_path: Optional[Path] = None) -> str:
    user = get_current_user(db_path=db_path)
    if not user:
        return "👤 No active user"
    role_label = "Administrator" if user["is_administrator"] else "Operator"
    return f"👤 Active user: {user['display_name']} ({role_label})"


def _validate_username(username: str) -> str:
    clean = (username or "").strip()
    if len(clean) < 2:
        raise AppUserError("Username must be at least 2 characters")
    if " " in clean:
        raise AppUserError("Username cannot contain spaces")
    return clean


def _validate_display_name(display_name: str) -> str:
    clean = (display_name or "").strip()
    if len(clean) < 2:
        raise AppUserError("Display name must be at least 2 characters")
    return clean


def _validate_role(role: str) -> str:
    clean = (role or ROLE_OPERATOR).strip().lower()
    if clean not in VALID_ROLES:
        raise AppUserError("Role must be administrator or operator")
    return clean


def insert_app_user(
    username: str,
    display_name: str,
    *,
    role: str = ROLE_OPERATOR,
    is_active: bool = True,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        uname = _validate_username(username)
        dname = _validate_display_name(display_name)
        r = _validate_role(role)
        path = ensure_app_user_table(db_path=db_path)
        now = _now_iso()
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            cursor = conn.execute(
                """
                INSERT INTO app_user (username, display_name, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uname, dname, r, int(is_active), now, now),
            )
            conn.commit()
            new_id = int(cursor.lastrowid)
        finally:
            conn.close()
        return {"ok": True, "id": new_id}
    except AppUserError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": f"Username '{username}' already exists"}
    except sqlite3.Error as exc:
        logger.error("insert app_user failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def update_app_user(
    user_id: int,
    *,
    username: str,
    display_name: str,
    role: str,
    is_active: bool,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        uid = int(user_id)
        uname = _validate_username(username)
        dname = _validate_display_name(display_name)
        r = _validate_role(role)
        path = ensure_app_user_table(db_path=db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            existing = conn.execute("SELECT id FROM app_user WHERE id = ?", (uid,)).fetchone()
            if not existing:
                raise AppUserError(f"User id={uid} not found")
            conn.execute(
                """
                UPDATE app_user
                SET username = ?, display_name = ?, role = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (uname, dname, r, int(is_active), _now_iso(), uid),
            )
            conn.commit()
        finally:
            conn.close()
        current_id = _load_session_user_id()
        if current_id == uid and not is_active:
            active = load_app_users(active_only=True, db_path=db_path)
            if active:
                set_current_user(active[0]["id"], db_path=db_path)
        return {"ok": True, "id": uid}
    except AppUserError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": f"Username '{username}' already exists"}
    except sqlite3.Error as exc:
        logger.error("update app_user failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def delete_app_user(user_id: int, *, db_path: Optional[Path] = None) -> Dict[str, Any]:
    try:
        uid = int(user_id)
        path = ensure_app_user_table(db_path=db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            total = conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0]
            if total <= 1:
                raise AppUserError("Cannot delete the last user in the system")
            row = conn.execute("SELECT id FROM app_user WHERE id = ?", (uid,)).fetchone()
            if not row:
                raise AppUserError(f"User id={uid} not found")
            conn.execute("DELETE FROM app_user WHERE id = ?", (uid,))
            conn.commit()
        finally:
            conn.close()
        if _load_session_user_id() == uid:
            active = load_app_users(active_only=True, db_path=db_path)
            if active:
                set_current_user(active[0]["id"], db_path=db_path)
            else:
                _save_session_user_id(None)
        return {"ok": True, "id": uid}
    except AppUserError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.Error as exc:
        logger.error("delete app_user failed: %s", exc)
        return {"ok": False, "error": str(exc)}
