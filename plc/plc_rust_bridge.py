"""
Bridge verso motore PLC Rust on-demand (rust_engine.PlcEngineSession).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from plc.plc_map_loader import ResolvedDbBlock, find_block_spec


def rust_plc_engine_available() -> bool:
    try:
        import rust_engine

        return hasattr(rust_engine, "PlcEngineSession") and hasattr(
            rust_engine, "plc_engine_available"
        )
    except ImportError:
        return False


def build_rust_poll_plan(
    poll_blocks: List[ResolvedDbBlock],
    explore_db: int,
    explore_size: int,
    map_profile: str,
    machine_id: str,
    *,
    parallel_limit: int = 3,
) -> Dict[str, Any]:
    spec = find_block_spec(map_profile, machine_id, explore_db)
    explore_vars = spec.variables if spec else []
    plan: Dict[str, Any] = {
        "parallel_limit": max(1, parallel_limit),
        "blocks": [
            {
                "db_number": block.number,
                "size_bytes": block.size_bytes,
                "variables": block.variables,
            }
            for block in poll_blocks
        ],
    }
    if explore_size > 0:
        plan["explore"] = {
            "db_number": explore_db,
            "size_bytes": explore_size,
            "variables": explore_vars,
        }
    return plan


def normalize_rust_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Allinea payload Rust a quello atteso dalla UI (explore come tuple)."""
    out = dict(payload)
    explore = out.get("explore")
    if isinstance(explore, dict):
        raw = explore.get("raw")
        if isinstance(raw, (bytes, bytearray)):
            raw_bytes = bytes(raw)
        elif isinstance(raw, list):
            raw_bytes = bytes(int(b) & 0xFF for b in raw)
        else:
            raw_bytes = b""
        out["explore"] = (
            int(explore.get("db_number", 0)),
            raw_bytes,
            explore.get("decoded") or {},
            int(explore.get("size", len(raw_bytes))),
            str(explore.get("source", "rust")),
        )
    blocks = out.get("blocks")
    if isinstance(blocks, dict):
        normalized: Dict[Any, Any] = {}
        for k, v in blocks.items():
            normalized[int(k)] = v
        out["blocks"] = normalized
    return out
