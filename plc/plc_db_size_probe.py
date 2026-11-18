"""
Rilevamento dimensione DB Siemens S7: block info Snap7 → mappa → probe a chunk.
"""

from __future__ import annotations

import struct
from typing import Any, List, Optional, Tuple

from plc.plc_snap7_reader import read_db_bytes

PROBE_CHUNK = 256
PROBE_MAX = 8192
PROBE_PRESETS = (256, 512, 1024, 2048)


def _snap7_raw_client(plc_client: Any) -> Any:
    return getattr(plc_client, "client", plc_client)


def detect_db_size_from_plc(
    plc_client: Any, db_number: int
) -> Tuple[Optional[int], str]:
    """Prova get_block_info; ritorna (size, source_tag)."""
    raw = _snap7_raw_client(plc_client)
    getter = getattr(raw, "get_block_info", None)
    if not callable(getter):
        return None, "unsupported"
    try:
        import snap7.type as s7type

        info = getter(s7type.Block.DB, int(db_number))
        for attr in ("LoadSize", "MC7Size", "BlkNumber"):
            size = int(getattr(info, attr, 0) or 0)
            if size > 0 and attr != "BlkNumber":
                return size, "block_info"
    except Exception:
        pass
    return None, "block_info_failed"


def probe_db_size_by_read(
    plc_client: Any, db_number: int, *, max_bytes: int = PROBE_MAX
) -> Tuple[int, str]:
    """Legge chunk crescenti fino a errore; ultima lettura OK = size stimata."""
    last_ok = 0
    pos = 0
    while pos < max_bytes:
        chunk = min(PROBE_CHUNK, max_bytes - pos)
        data = read_db_bytes(plc_client, db_number, pos, chunk)
        if data is None or len(data) < chunk:
            break
        last_ok = pos + len(data)
        pos += chunk
    if last_ok > 0:
        return last_ok, "probe_read"
    for preset in PROBE_PRESETS:
        data = read_db_bytes(plc_client, db_number, 0, preset)
        if data is not None and len(data) == preset:
            return preset, "probe_preset"
    return PROBE_PRESETS[0], "probe_fallback"


def resolve_db_read_size(
    plc_client: Any,
    db_number: int,
    *,
    map_size: Optional[int] = None,
    user_size: Optional[int] = None,
    auto_detect: bool = True,
) -> Tuple[int, str]:
    """
    Priorità: user_size esplicito > auto block_info > mappa > probe read > 256.
    """
    if user_size is not None and user_size > 0:
        return int(user_size), "manual"

    if auto_detect and plc_client is not None:
        plc_size, src = detect_db_size_from_plc(plc_client, db_number)
        if plc_size and plc_size > 0:
            return plc_size, src

    if map_size is not None and map_size > 0:
        return int(map_size), "map"

    if auto_detect and plc_client is not None:
        return probe_db_size_by_read(plc_client, db_number)

    return 256, "default"
