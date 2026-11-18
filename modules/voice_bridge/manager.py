"""Start/stop standalone voice bridge (thread in NStone process)."""
from __future__ import annotations

import socket
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from modules.agentic_calling import load_agentic_calling_config
from modules.voice_bridge.server import create_server

_lock = threading.Lock()
_server = None
_serve_thread: Optional[threading.Thread] = None
_bound_host = ""
_bound_port = 0


@dataclass
class BridgeStartResult:
    started: bool
    message: str
    host: str = "127.0.0.1"
    port: int = 8765


def is_voice_bridge_running() -> bool:
    thread = _serve_thread
    return thread is not None and thread.is_alive()


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except OSError:
        return False


def check_voice_bridge_health(
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> Tuple[bool, str]:
    cfg = load_agentic_calling_config()
    host = host or str(cfg.get("voice_bridge_host") or "127.0.0.1")
    port = int(port or cfg.get("voice_bridge_port") or 8765)
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            if resp.status == 200:
                return True, f"{host}:{port}"
    except urllib.error.URLError:
        if is_voice_bridge_running():
            return False, f"Starting on {host}:{port}…"
        if _port_open(host, port):
            return False, f"Port {port} busy (not NStone bridge?)"
        return False, "Offline — opens with Agentic Calling"
    except Exception as exc:
        return False, str(exc)[:120]
    return False, "Unknown"


def start_voice_bridge(force: bool = False) -> BridgeStartResult:
    global _server, _serve_thread, _bound_host, _bound_port

    cfg = load_agentic_calling_config()
    if not cfg.get("enabled", True):
        return BridgeStartResult(False, "Agentic Calling disabled in config")

    auto = cfg.get("voice_bridge_auto_start", True)
    if not auto and not force:
        return BridgeStartResult(False, "Auto-start disabled in config")

    host = str(cfg.get("voice_bridge_host") or "127.0.0.1")
    port = int(cfg.get("voice_bridge_port") or 8765)

    if is_voice_bridge_running():
        return BridgeStartResult(True, f"Already running on {host}:{port}", host, port)

    ok, detail = check_voice_bridge_health(host, port)
    if ok and not force:
        return BridgeStartResult(True, f"Health OK ({detail})", host, port)

    if _port_open(host, port) and not ok:
        return BridgeStartResult(
            False,
                f"Port {port} in use - change voice_bridge_port in config.json",
            host,
            port,
        )

    def _run() -> None:
        global _server
        httpd = create_server(host, port)
        with _lock:
            _server = httpd
        httpd.serve_forever(poll_interval=0.5)

    thread = threading.Thread(target=_run, name="NStoneVoiceBridge", daemon=True)
    with _lock:
        _serve_thread = thread
        _bound_host = host
        _bound_port = port
    thread.start()

    for _ in range(30):
        if check_voice_bridge_health(host, port)[0]:
            return BridgeStartResult(True, f"Listening on {host}:{port}", host, port)
        if not is_voice_bridge_running():
            return BridgeStartResult(
                False,
                f"Voice bridge thread exited on {host}:{port}",
                host,
                port,
            )
        threading.Event().wait(0.05)

    return BridgeStartResult(
        False,
        f"Failed to bind {host}:{port}",
        host,
        port,
    )


def stop_voice_bridge() -> None:
    global _server, _serve_thread, _bound_host, _bound_port

    with _lock:
        httpd = _server
        thread = _serve_thread
        _server = None
        _serve_thread = None
        _bound_host = ""
        _bound_port = 0

    if httpd is not None:
        httpd.shutdown()
    if thread is not None:
        thread.join(timeout=3.0)
