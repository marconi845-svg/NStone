"""
Registro servizi background (monitor quotation, IMAP, ecc.) per diagnostica e shutdown.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_lock = threading.Lock()
_services: Dict[str, Dict[str, Any]] = {}


def register_service(name: str, description: str = "") -> None:
    with _lock:
        _services.setdefault(
            name,
            {
                "description": description,
                "running": False,
                "last_tick": None,
                "last_error": None,
                "tick_count": 0,
            },
        )


def set_service_running(name: str, running: bool) -> None:
    register_service(name)
    with _lock:
        _services[name]["running"] = running


def record_service_tick(name: str, *, ok: bool = True, error: Optional[str] = None) -> None:
    register_service(name)
    with _lock:
        entry = _services[name]
        entry["last_tick"] = time.time()
        entry["tick_count"] = int(entry.get("tick_count") or 0) + 1
        if ok:
            entry["last_error"] = None
        elif error:
            entry["last_error"] = error


def get_services_snapshot() -> Dict[str, Dict[str, Any]]:
    with _lock:
        return {name: dict(data) for name, data in _services.items()}


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_diagnostics_text() -> str:
    lines = ["Servizi background NSTONELLM", ""]
    snap = get_services_snapshot()
    if not snap:
        lines.append("Nessun servizio registrato ancora.")
        return "\n".join(lines)

    for name, data in sorted(snap.items()):
        desc = data.get("description") or name
        running = "ON" if data.get("running") else "OFF"
        ticks = int(data.get("tick_count") or 0)
        last = _fmt_ts(data.get("last_tick"))
        err = data.get("last_error")
        line = f"• {desc}: {running} · cicli {ticks} · ultimo {last}"
        if err:
            line += f"\n  errore: {err}"
        lines.append(line)

    try:
        import psutil

        proc = psutil.Process()
        mem_mb = proc.memory_info().rss / (1024 * 1024)
        lines.append("")
        lines.append(f"Memoria processo: {mem_mb:.0f} MB")
    except Exception:
        pass

    return "\n".join(lines)


def shutdown_all() -> None:
    """Ferma monitor noti (idempotente)."""
    try:
        from ui.common.gmail_imap_scheduler import stop_gmail_imap_background

        stop_gmail_imap_background()
    except Exception:
        pass
    try:
        from modules.quotation_auto_monitor import stop_quotation_auto_monitor

        stop_quotation_auto_monitor()
        set_service_running("quotation_auto", False)
    except Exception:
        pass
