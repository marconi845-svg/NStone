"""
Diagnostica connessione PLC: ping, latenza lettura, CPU RUN/STOP, errori Snap7.
"""

from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PlcConnectionStats:
    ping_ok: Optional[bool] = None
    ping_ms: Optional[float] = None
    read_latency_ms: Optional[float] = None
    cpu_state: str = "—"
    snap7_connected: bool = False
    last_error: str = ""
    retry_count: int = 0
    plc_order_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ping_ok": self.ping_ok,
            "ping_ms": self.ping_ms,
            "read_latency_ms": self.read_latency_ms,
            "cpu_state": self.cpu_state,
            "snap7_connected": self.snap7_connected,
            "last_error": self.last_error,
            "retry_count": self.retry_count,
            "plc_order_code": self.plc_order_code,
        }


def ping_host(ip: str, timeout_ms: int = 800) -> Tuple[Optional[bool], Optional[float]]:
    if not ip:
        return None, None
    flag = "-n" if platform.system().lower() == "windows" else "-c"
    try:
        t0 = time.perf_counter()
        proc = subprocess.run(
            ["ping", flag, "1", "-w", str(timeout_ms), ip],
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout_ms / 1000.0 + 0.5),
        )
        elapsed = (time.perf_counter() - t0) * 1000.0
        return proc.returncode == 0, round(elapsed, 1)
    except Exception:
        return False, None


def _snap7_raw(plc_client: Any) -> Any:
    return getattr(plc_client, "client", plc_client)


def read_cpu_state(plc_client: Any) -> str:
    raw = _snap7_raw(plc_client)
    try:
        if hasattr(raw, "get_cpu_state"):
            state = raw.get_cpu_state()
            if isinstance(state, bytes):
                state = state.decode(errors="replace")
            return str(state).strip() or "—"
    except Exception:
        pass
    return "—"


def read_order_code(plc_client: Any) -> str:
    raw = _snap7_raw(plc_client)
    try:
        if hasattr(raw, "get_cpu_info"):
            info = raw.get_cpu_info()
            code = getattr(info, "ModuleTypeName", None) or getattr(info, "ASName", None)
            if code:
                return str(code).strip()
    except Exception:
        pass
    return ""


def measure_read_latency_ms(
    plc_client: Any, db_number: int = 1, size: int = 4
) -> Optional[float]:
    from plc.plc_snap7_reader import read_db_bytes

    t0 = time.perf_counter()
    data = read_db_bytes(plc_client, db_number, 0, size)
    if data is None:
        return None
    return round((time.perf_counter() - t0) * 1000.0, 2)


def collect_connection_stats(
    plc_client: Any,
    ip: str,
    *,
    retry_count: int = 0,
    last_error: str = "",
    probe_db: int = 1,
) -> PlcConnectionStats:
    stats = PlcConnectionStats(retry_count=retry_count, last_error=last_error or "")
    stats.ping_ok, stats.ping_ms = ping_host(ip)
    connected = False
    try:
        connected = bool(
            getattr(plc_client, "is_connected", lambda: False)()
        )
    except Exception:
        pass
    stats.snap7_connected = connected
    if connected:
        stats.cpu_state = read_cpu_state(plc_client)
        stats.plc_order_code = read_order_code(plc_client)
        stats.read_latency_ms = measure_read_latency_ms(plc_client, probe_db, 4)
    return stats
