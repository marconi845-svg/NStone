"""
Tracking posizioni materiali (scan DataMatrix + GPS) in data/nstonellm.db.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from modules.orders_database import get_database_path
except ImportError:
    get_database_path = None  # type: ignore


def _db_path() -> Path:
    if get_database_path is not None:
        return get_database_path()
    return Path(__file__).resolve().parent.parent / "data" / "nstonellm.db"


def normalize_block_uid(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("#"):
        text = text[1:].strip()
    return text


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")


def init_logistics_tables(db_path: Optional[Path] = None) -> None:
    path = db_path or _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS material_assets (
            block_uid TEXT PRIMARY KEY,
            materiale TEXT,
            order_id TEXT,
            stock_product_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS material_location_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_uid TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            accuracy_m REAL,
            altitude_m REAL,
            zone_label TEXT,
            source TEXT NOT NULL DEFAULT 'scan',
            operator_id TEXT,
            device_id TEXT,
            raw_payload TEXT,
            scanned_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (block_uid) REFERENCES material_assets(block_uid)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mle_block_uid
        ON material_location_events(block_uid)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mle_scanned_at
        ON material_location_events(scanned_at DESC)
        """
    )
    conn.commit()
    conn.close()


def _parse_iso_timestamp(value: Any) -> str:
    if value is None or value == "":
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value).strip()
    if text.endswith("Z"):
        return text
    if "+" in text[10:] or text.count("-") > 2:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_material_asset(
    block_uid: str,
    *,
    materiale: Optional[str] = None,
    order_id: Optional[str] = None,
    stock_product_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> None:
    uid = normalize_block_uid(block_uid)
    if not uid:
        raise ValueError("block_uid obbligatorio")
    init_logistics_tables(db_path)
    path = db_path or _db_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    conn.execute(
        """
        INSERT INTO material_assets (block_uid, materiale, order_id, stock_product_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(block_uid) DO UPDATE SET
            materiale = COALESCE(excluded.materiale, material_assets.materiale),
            order_id = COALESCE(excluded.order_id, material_assets.order_id),
            stock_product_id = COALESCE(
                excluded.stock_product_id, material_assets.stock_product_id
            ),
            updated_at = CURRENT_TIMESTAMP
        """,
        (uid, materiale, order_id, stock_product_id),
    )
    conn.commit()
    conn.close()


def record_location_scan(
    *,
    block_uid: str,
    lat: float,
    lon: float,
    accuracy_m: Optional[float] = None,
    altitude_m: Optional[float] = None,
    zone_label: Optional[str] = None,
    source: str = "scan",
    operator_id: Optional[str] = None,
    device_id: Optional[str] = None,
    materiale: Optional[str] = None,
    order_id: Optional[str] = None,
    scanned_at: Optional[str] = None,
    raw_payload: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    uid = normalize_block_uid(block_uid)
    if not uid:
        raise ValueError("block_uid obbligatorio")
    if not (-90.0 <= float(lat) <= 90.0):
        raise ValueError("lat non valida")
    if not (-180.0 <= float(lon) <= 180.0):
        raise ValueError("lon non valida")

    upsert_material_asset(
        uid,
        materiale=materiale,
        order_id=order_id,
        db_path=db_path,
    )
    ts = _parse_iso_timestamp(scanned_at)
    init_logistics_tables(db_path)
    path = db_path or _db_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    cursor = conn.execute(
        """
        INSERT INTO material_location_events (
            block_uid, lat, lon, accuracy_m, altitude_m, zone_label,
            source, operator_id, device_id, raw_payload, scanned_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uid,
            float(lat),
            float(lon),
            accuracy_m,
            altitude_m,
            zone_label,
            (source or "scan").strip()[:32],
            operator_id,
            device_id,
            raw_payload,
            ts,
        ),
    )
    event_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    logger.info("Scan logistico registrato block_uid=%s event_id=%s", uid, event_id)
    return {"event_id": event_id, "block_uid": uid, "scanned_at": ts}


def get_latest_positions(
    *,
    block_uid: Optional[str] = None,
    limit: int = 500,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    init_logistics_tables(db_path)
    path = db_path or _db_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)

    params: List[Any] = []
    uid_filter = ""
    if block_uid:
        uid_filter = "AND e.block_uid = ?"
        params.append(normalize_block_uid(block_uid))

    params.append(max(1, min(int(limit), 2000)))

    rows = conn.execute(
        f"""
        SELECT
            e.id AS event_id,
            e.block_uid,
            a.materiale,
            a.order_id,
            e.lat,
            e.lon,
            e.accuracy_m,
            e.zone_label,
            e.operator_id,
            e.scanned_at,
            e.source
        FROM material_location_events e
        INNER JOIN (
            SELECT block_uid, MAX(id) AS max_id
            FROM material_location_events
            GROUP BY block_uid
        ) last ON e.id = last.max_id
        LEFT JOIN material_assets a ON a.block_uid = e.block_uid
        WHERE 1=1 {uid_filter}
        ORDER BY e.scanned_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "event_id": row["event_id"],
                "block_uid": row["block_uid"],
                "materiale": row["materiale"],
                "order_id": row["order_id"],
                "lat": row["lat"],
                "lon": row["lon"],
                "accuracy_m": row["accuracy_m"],
                "zone_label": row["zone_label"],
                "operator_id": row["operator_id"],
                "scanned_at": row["scanned_at"],
                "source": row["source"],
            }
        )
    return out


def get_location_history(
    block_uid: str,
    *,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    uid = normalize_block_uid(block_uid)
    if not uid:
        return []
    init_logistics_tables(db_path)
    path = db_path or _db_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    rows = conn.execute(
        """
        SELECT id AS event_id, block_uid, lat, lon, accuracy_m, zone_label,
               operator_id, scanned_at, source
        FROM material_location_events
        WHERE block_uid = ?
        ORDER BY scanned_at DESC
        LIMIT ?
        """,
        (uid, max(1, min(int(limit), 500))),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_logistics_settings() -> Dict[str, Any]:
    defaults = {
        "api_key": "",
        "map_poll_seconds": 8,
        "default_map_center": [45.46, 9.19],
        "default_map_zoom": 13,
    }
    try:
        from core.machine_plc_config import load_config

        cfg = load_config().get("logistics") or {}
        if not isinstance(cfg, dict):
            return defaults
        center = cfg.get("default_map_center", defaults["default_map_center"])
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            center = defaults["default_map_center"]
        return {
            "api_key": str(cfg.get("api_key") or "").strip(),
            "map_poll_seconds": int(cfg.get("map_poll_seconds", defaults["map_poll_seconds"])),
            "default_map_center": [float(center[0]), float(center[1])],
            "default_map_zoom": int(cfg.get("default_map_zoom", defaults["default_map_zoom"])),
        }
    except Exception:
        return defaults


def verify_api_key(provided: Optional[str]) -> bool:
    settings = get_logistics_settings()
    expected = settings["api_key"]
    if not expected:
        return True
    return bool(provided) and provided.strip() == expected


STOCK_POSITION_KEYS = (
    "block_uid",
    "materiale",
    "order_id",
    "zone_label",
    "lat",
    "lon",
    "accuracy_m",
    "operator_id",
    "notes",
)


def _logistics_tables_exist(db_path: Path) -> bool:
    if not db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='material_assets'"
        )
        ok = cur.fetchone()[0] > 0
        conn.close()
        return ok
    except sqlite3.Error:
        return False


def is_logistics_editable(db_path: Optional[Path] = None) -> bool:
    """Modifica abilitata se esiste data/nstonellm.db con tabelle logistiche."""
    path = db_path or _db_path()
    init_logistics_tables(path)
    return _logistics_tables_exist(path)


def get_logistics_info(db_path: Optional[Path] = None) -> Dict[str, Any]:
    path = db_path or _db_path()
    init_logistics_tables(path)
    records = list_stock_position_records(db_path=path)
    return {
        "source": "sqlite",
        "path": str(path),
        "count": len(records),
        "editable": is_logistics_editable(path),
    }


def list_stock_position_records(
    *,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Tutti i material_assets con ultima posizione (se presente).
    """
    init_logistics_tables(db_path)
    path = db_path or _db_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    rows = conn.execute(
        """
        SELECT
            a.block_uid,
            a.materiale,
            a.order_id,
            a.stock_product_id,
            a.notes,
            e.id AS event_id,
            e.lat,
            e.lon,
            e.accuracy_m,
            e.zone_label,
            e.operator_id,
            e.scanned_at,
            e.source
        FROM material_assets a
        LEFT JOIN (
            SELECT block_uid, MAX(id) AS max_id
            FROM material_location_events
            GROUP BY block_uid
        ) last ON last.block_uid = a.block_uid
        LEFT JOIN material_location_events e ON e.id = last.max_id
        ORDER BY COALESCE(e.scanned_at, a.updated_at) DESC, a.block_uid ASC
        """
    ).fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "block_uid": row["block_uid"],
                "materiale": row["materiale"],
                "order_id": row["order_id"],
                "stock_product_id": row["stock_product_id"],
                "notes": row["notes"],
                "event_id": row["event_id"],
                "lat": row["lat"],
                "lon": row["lon"],
                "accuracy_m": row["accuracy_m"],
                "zone_label": row["zone_label"],
                "operator_id": row["operator_id"],
                "scanned_at": row["scanned_at"],
                "source": row["source"],
            }
        )
    return out


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def insert_stock_position(
    data: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    uid = normalize_block_uid(data.get("block_uid"))
    if not uid:
        return {"ok": False, "error": "Blocco obbligatorio"}

    path = db_path or _db_path()
    init_logistics_tables(path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    exists = conn.execute(
        "SELECT 1 FROM material_assets WHERE block_uid = ? LIMIT 1", (uid,)
    ).fetchone()
    conn.close()
    if exists:
        return {"ok": False, "error": f"Il blocco {uid} esiste già"}

    try:
        stock_id = data.get("stock_product_id")
        upsert_material_asset(
            uid,
            materiale=(data.get("materiale") or "").strip() or None,
            order_id=(data.get("order_id") or "").strip() or None,
            stock_product_id=int(stock_id) if stock_id not in (None, "") else None,
            db_path=path,
        )
        notes = (data.get("notes") or "").strip()
        if notes:
            conn = sqlite3.connect(str(path), timeout=5.0)
            conn.execute(
                "UPDATE material_assets SET notes = ? WHERE block_uid = ?",
                (notes, uid),
            )
            conn.commit()
            conn.close()

        lat = _optional_float(data.get("lat"))
        lon = _optional_float(data.get("lon"))
        if lat is not None and lon is not None:
            record_location_scan(
                block_uid=uid,
                lat=lat,
                lon=lon,
                accuracy_m=_optional_float(data.get("accuracy_m")),
                zone_label=(data.get("zone_label") or "").strip() or None,
                operator_id=(data.get("operator_id") or "").strip() or None,
                materiale=(data.get("materiale") or "").strip() or None,
                order_id=(data.get("order_id") or "").strip() or None,
                source="manual",
                db_path=path,
            )
        return {"ok": True, "block_uid": uid}
    except (ValueError, sqlite3.Error) as exc:
        logger.error("insert_stock_position: %s", exc)
        return {"ok": False, "error": str(exc)}


def update_stock_position(
    block_uid: str,
    data: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    uid = normalize_block_uid(block_uid)
    if not uid:
        return {"ok": False, "error": "Blocco non valido"}

    path = db_path or _db_path()
    init_logistics_tables(path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    _configure_connection(conn)
    exists = conn.execute(
        "SELECT 1 FROM material_assets WHERE block_uid = ? LIMIT 1", (uid,)
    ).fetchone()
    conn.close()
    if not exists:
        return {"ok": False, "error": f"Blocco {uid} non trovato"}

    try:
        stock_id = data.get("stock_product_id")
        upsert_material_asset(
            uid,
            materiale=(data.get("materiale") or "").strip() or None,
            order_id=(data.get("order_id") or "").strip() or None,
            stock_product_id=int(stock_id) if stock_id not in (None, "") else None,
            db_path=path,
        )
        notes = (data.get("notes") or "").strip()
        conn = sqlite3.connect(str(path), timeout=5.0)
        conn.execute(
            "UPDATE material_assets SET notes = ?, updated_at = CURRENT_TIMESTAMP WHERE block_uid = ?",
            (notes or None, uid),
        )
        conn.commit()
        conn.close()

        lat = _optional_float(data.get("lat"))
        lon = _optional_float(data.get("lon"))
        if lat is not None and lon is not None:
            record_location_scan(
                block_uid=uid,
                lat=lat,
                lon=lon,
                accuracy_m=_optional_float(data.get("accuracy_m")),
                zone_label=(data.get("zone_label") or "").strip() or None,
                operator_id=(data.get("operator_id") or "").strip() or None,
                materiale=(data.get("materiale") or "").strip() or None,
                order_id=(data.get("order_id") or "").strip() or None,
                source="manual",
                db_path=path,
            )
        return {"ok": True, "block_uid": uid}
    except (ValueError, sqlite3.Error) as exc:
        logger.error("update_stock_position: %s", exc)
        return {"ok": False, "error": str(exc)}


def delete_stock_position(
    block_uid: str,
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    uid = normalize_block_uid(block_uid)
    if not uid:
        return {"ok": False, "error": "Blocco non valido"}

    path = db_path or _db_path()
    init_logistics_tables(path)
    try:
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        conn.execute(
            "DELETE FROM material_location_events WHERE block_uid = ?", (uid,)
        )
        cur = conn.execute("DELETE FROM material_assets WHERE block_uid = ?", (uid,))
        conn.commit()
        conn.close()
        if cur.rowcount == 0:
            return {"ok": False, "error": f"Blocco {uid} non trovato"}
        return {"ok": True, "block_uid": uid}
    except sqlite3.Error as exc:
        logger.error("delete_stock_position: %s", exc)
        return {"ok": False, "error": str(exc)}
