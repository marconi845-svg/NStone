"""Agentic Calling — FreeSWITCH + local Ollama voice extensions (LAN SIP)."""
from __future__ import annotations

import json
import socket
import subprocess
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.machine_plc_config import load_config, save_config

EXTENSION_MANAGEMENT = "management"
EXTENSION_COMMERCIAL = "commercial"
EXTENSION_PRODUCTION = "production"

DEFAULT_AGENTIC_CALLING: Dict[str, Any] = {
    "enabled": True,
    "mode": "lan",
    "sip_server": "127.0.0.1",
    "sip_port": 5060,
    "freeswitch_path": "",
    "stt_engine": "whisper",
    "tts_engine": "piper",
    "voice_bridge_host": "127.0.0.1",
    "voice_bridge_port": 8765,
    "voice_bridge_auto_start": True,
    "whisper_path": "",
    "whisper_model": "",
    "whisper_timeout_seconds": 90,
    "piper_path": "",
    "piper_voice": "",
    "piper_timeout_seconds": 60,
    "recordings_dir": "",
    "extensions": {
        EXTENSION_MANAGEMENT: {
            "number": "1000",
            "label": "Management",
            "role": "Policy, agents, system autonomy, office overview",
            "nstone_modules": ["Agents Command Center", "Settings", "Privacy"],
        },
        EXTENSION_COMMERCIAL: {
            "number": "2000",
            "label": "Commercial",
            "role": "Quotations, incoming requests, customer follow-up",
            "nstone_modules": ["Quotations Hub", "Orders intake", "WhatsApp"],
        },
        EXTENSION_PRODUCTION: {
            "number": "3000",
            "label": "Production",
            "role": "Production orders, machine status, shop-floor queries",
            "nstone_modules": ["Order Center", "Production Order Center", "Machines"],
        },
    },
}

CALL_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "agentic_calling_log.json"


@dataclass
class ServiceStatus:
    online: bool
    detail: str


def load_agentic_calling_config() -> Dict[str, Any]:
    cfg = load_config()
    raw = cfg.get("agentic_calling")
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_AGENTIC_CALLING)
    merged = deepcopy(DEFAULT_AGENTIC_CALLING)
    for key, value in raw.items():
        if key == "extensions" and isinstance(value, dict):
            for ext_key, ext_val in value.items():
                if ext_key in merged["extensions"] and isinstance(ext_val, dict):
                    merged["extensions"][ext_key].update(ext_val)
        else:
            merged[key] = value
    return merged


def save_agentic_calling_config(updates: Dict[str, Any]) -> Path:
    cfg = load_config()
    current = load_agentic_calling_config()
    current.update(updates)
    cfg["agentic_calling"] = current
    return save_config(cfg)


def get_extension(cfg: Dict[str, Any], key: str) -> Dict[str, Any]:
    extensions = cfg.get("extensions") or {}
    base = DEFAULT_AGENTIC_CALLING["extensions"][key]
    ext = extensions.get(key) if isinstance(extensions, dict) else None
    if isinstance(ext, dict):
        return {**base, **ext}
    return dict(base)


def sip_dial_uri(cfg: Dict[str, Any], extension_number: str) -> str:
    host = str(cfg.get("sip_server") or "127.0.0.1")
    port = int(cfg.get("sip_port") or 5060)
    if port == 5060:
        return f"sip:{extension_number}@{host}"
    return f"sip:{extension_number}@{host}:{port}"


def check_ollama_status() -> ServiceStatus:
    try:
        from llm.llm_service import load_llm_config

        cfg = load_llm_config()
        provider = str(cfg.get("provider") or "ollama").lower()
        if provider != "ollama":
            return ServiceStatus(False, f"Provider: {provider} (voice stack expects Ollama)")
        ollama_cfg = cfg.get("ollama") or {}
        base = str(ollama_cfg.get("base_url") or "http://127.0.0.1:11434")
        model = str(ollama_cfg.get("model") or "—")
        req = urllib.request.Request(f"{base.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status != 200:
                return ServiceStatus(False, f"HTTP {resp.status}")
        return ServiceStatus(True, f"{model} @ {base}")
    except urllib.error.URLError:
        return ServiceStatus(False, "Ollama not reachable on localhost")
    except Exception as exc:
        return ServiceStatus(False, str(exc)[:120])


def check_sip_port(cfg: Dict[str, Any]) -> ServiceStatus:
    host = str(cfg.get("sip_server") or "127.0.0.1")
    port = int(cfg.get("sip_port") or 5060)
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return ServiceStatus(True, f"SIP {host}:{port} open (FreeSWITCH expected)")
    except OSError:
        return ServiceStatus(
            False,
            f"No listener on {host}:{port} — start FreeSWITCH on LAN",
        )


def probe_freeswitch_cli(cfg: Dict[str, Any]) -> ServiceStatus:
    path = (cfg.get("freeswitch_path") or "").strip()
    candidates: List[str] = []
    if path:
        candidates.append(path)
    candidates.extend(["fs_cli", "freeswitch"])
    for cmd in candidates:
        try:
            result = subprocess.run(
                [cmd, "-x", "status"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            out = (result.stdout or result.stderr or "").strip()
            if result.returncode == 0 and out:
                first = out.splitlines()[0][:80]
                return ServiceStatus(True, first)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    sip = check_sip_port(cfg)
    if sip.online:
        return sip
    return ServiceStatus(False, "FreeSWITCH CLI not found — configure path or SIP port")


def load_call_log(limit: int = 50) -> List[Dict[str, Any]]:
    if not CALL_LOG_PATH.is_file():
        return []
    try:
        data = json.loads(CALL_LOG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[-limit:]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def append_call_log(entry: Dict[str, Any]) -> None:
    CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = load_call_log(limit=500)
    entry.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    rows.append(entry)
    CALL_LOG_PATH.write_text(json.dumps(rows[-500:], indent=2), encoding="utf-8")
