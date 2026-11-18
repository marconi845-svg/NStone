"""
API REST per scan logistico (smartphone) e lettura posizioni (mappa desktop / PWA).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from modules.logistics_db import (
    get_latest_positions,
    get_location_history,
    get_logistics_settings,
    record_location_scan,
    verify_api_key,
)

router = APIRouter(prefix="/api/logistics", tags=["logistics"])


class ScanPayload(BaseModel):
    block_uid: str = Field(..., min_length=1, max_length=64)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    accuracy_m: Optional[float] = None
    altitude_m: Optional[float] = None
    zone_label: Optional[str] = None
    materiale: Optional[str] = None
    order_id: Optional[str] = None
    operator_id: Optional[str] = None
    device_id: Optional[str] = None
    scanned_at: Optional[str] = None
    datamatrix_raw: Optional[str] = None
    source: str = "scan"


def _check_key(x_logistics_key: Optional[str]) -> None:
    if not verify_api_key(x_logistics_key):
        raise HTTPException(status_code=401, detail="API key logistica non valida")


@router.post("/scan")
async def post_scan(
    body: ScanPayload,
    x_logistics_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    _check_key(x_logistics_key)
    try:
        result = record_location_scan(
            block_uid=body.block_uid,
            lat=body.lat,
            lon=body.lon,
            accuracy_m=body.accuracy_m,
            altitude_m=body.altitude_m,
            zone_label=body.zone_label,
            materiale=body.materiale,
            order_id=body.order_id,
            operator_id=body.operator_id,
            device_id=body.device_id,
            scanned_at=body.scanned_at,
            raw_payload=body.datamatrix_raw,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "success": True,
        "message": "Posizione registrata",
        **result,
    }


@router.get("/positions")
async def get_positions(
    block_uid: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    x_logistics_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    _check_key(x_logistics_key)
    positions = get_latest_positions(block_uid=block_uid, limit=limit)
    return {
        "success": True,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(positions),
        "positions": positions,
    }


@router.get("/history/{block_uid}")
async def get_history(
    block_uid: str,
    limit: int = Query(100, ge=1, le=500),
    x_logistics_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    _check_key(x_logistics_key)
    events = get_location_history(block_uid, limit=limit)
    return {
        "success": True,
        "block_uid": block_uid,
        "count": len(events),
        "events": events,
    }


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    """Impostazioni mappa pubbliche (senza api_key)."""
    s = get_logistics_settings()
    return {
        "success": True,
        "map_poll_seconds": s["map_poll_seconds"],
        "default_map_center": s["default_map_center"],
        "default_map_zoom": s["default_map_zoom"],
        "auth_required": bool(s["api_key"]),
    }
