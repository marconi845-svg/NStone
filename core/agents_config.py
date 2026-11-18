"""
Configurazione Agents Command Center: autonomia, agenti produzione, tattiche commerciali.

Persistenza in config.json (merge tramite machine_plc_config).
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Dict, List, Literal, TypedDict

from core.machine_plc_config import load_config, save_config

AutonomyLevel = Literal[0, 1, 2, 3, 4]
CommercialTone = Literal[0, 1, 2, 3, 4]

AUTONOMY_LEVEL_LABELS = {
    0: "Suggestions only",
    1: "Mandatory approval (recommended)",
    2: "Assisted office",
    3: "Lab — simulation only",
    4: "Lab — autonomous (bench only)",
}

COMMERCIAL_TONE_LABELS = {
    0: "Very cautious",
    1: "Professional",
    2: "Proactive",
    3: "Assertive",
    4: "Maximum (lab only)",
}


class AutonomySettings(TypedDict):
    level: int
    max_level: int
    office_auto_email: bool
    office_auto_stock: bool
    plant_auto_plc_write: bool
    plant_sim_only: bool
    require_pin_above: int
    admin_pin_hash: str
    agents_paused: bool


class AgentsRegistrySettings(TypedDict):
    enabled: List[str]
    max_concurrent: int
    max_rounds_per_case: int
    plant_watch_multifilo: bool
    plant_watch_lucidatrice: bool
    plant_watch_cnc: bool
    office_enabled: bool
    plant_enabled: bool
    memory_enabled: bool


class CommercialSettings(TypedDict):
    tone: int
    max_tone: int
    follow_up_days: int
    upsell_enabled: bool
    urgency_phrasing: bool


class CommandCenterSettings(TypedDict):
    autonomy: AutonomySettings
    agents: AgentsRegistrySettings
    commercial: CommercialSettings


DEFAULT_AUTONOMY: AutonomySettings = {
    "level": 0,
    "max_level": 2,
    "office_auto_email": False,
    "office_auto_stock": False,
    "plant_auto_plc_write": False,
    "plant_sim_only": True,
    "require_pin_above": 2,
    "admin_pin_hash": "",
    "agents_paused": False,
}

DEFAULT_AGENTS: AgentsRegistrySettings = {
    "enabled": ["office", "plant"],
    "max_concurrent": 1,
    "max_rounds_per_case": 5,
    "plant_watch_multifilo": True,
    "plant_watch_lucidatrice": True,
    "plant_watch_cnc": False,
    "office_enabled": True,
    "plant_enabled": True,
    "memory_enabled": False,
}

DEFAULT_COMMERCIAL: CommercialSettings = {
    "tone": 1,
    "max_tone": 2,
    "follow_up_days": 3,
    "upsell_enabled": False,
    "urgency_phrasing": False,
}


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _normalize_autonomy(raw: Any) -> AutonomySettings:
    out = deepcopy(DEFAULT_AUTONOMY)
    if not isinstance(raw, dict):
        return out
    out["level"] = _clamp_int(raw.get("level"), 0, 4, out["level"])
    out["max_level"] = _clamp_int(raw.get("max_level"), 0, 4, out["max_level"])
    if out["level"] > out["max_level"]:
        out["level"] = out["max_level"]
    for key in (
        "office_auto_email",
        "office_auto_stock",
        "plant_auto_plc_write",
        "plant_sim_only",
        "agents_paused",
    ):
        if key in raw:
            out[key] = bool(raw[key])
    out["require_pin_above"] = _clamp_int(
        raw.get("require_pin_above"), 0, 4, out["require_pin_above"]
    )
    pin = raw.get("admin_pin_hash")
    if isinstance(pin, str):
        out["admin_pin_hash"] = pin.strip()
    return out


def _normalize_agents(raw: Any) -> AgentsRegistrySettings:
    out = deepcopy(DEFAULT_AGENTS)
    if not isinstance(raw, dict):
        return out
    enabled = raw.get("enabled")
    if isinstance(enabled, list):
        valid = {"office", "plant", "memory"}
        out["enabled"] = [str(x) for x in enabled if str(x) in valid]
    out["max_concurrent"] = _clamp_int(raw.get("max_concurrent"), 1, 4, 1)
    out["max_rounds_per_case"] = _clamp_int(raw.get("max_rounds_per_case"), 1, 20, 5)
    for key in (
        "plant_watch_multifilo",
        "plant_watch_lucidatrice",
        "plant_watch_cnc",
        "office_enabled",
        "plant_enabled",
        "memory_enabled",
    ):
        if key in raw:
            out[key] = bool(raw[key])
    # Allinea enabled[] alle checkbox
    enabled_list: List[str] = []
    if out["office_enabled"]:
        enabled_list.append("office")
    if out["plant_enabled"]:
        enabled_list.append("plant")
    if out["memory_enabled"]:
        enabled_list.append("memory")
    if enabled_list:
        out["enabled"] = enabled_list
    return out


def _normalize_commercial(raw: Any) -> CommercialSettings:
    out = deepcopy(DEFAULT_COMMERCIAL)
    if not isinstance(raw, dict):
        return out
    out["tone"] = _clamp_int(raw.get("tone"), 0, 4, out["tone"])
    out["max_tone"] = _clamp_int(raw.get("max_tone"), 0, 4, out["max_tone"])
    if out["tone"] > out["max_tone"]:
        out["tone"] = out["max_tone"]
    out["follow_up_days"] = _clamp_int(raw.get("follow_up_days"), 1, 30, 3)
    for key in ("upsell_enabled", "urgency_phrasing"):
        if key in raw:
            out[key] = bool(raw[key])
    return out


def load_command_center_settings() -> CommandCenterSettings:
    data = load_config()
    return {
        "autonomy": _normalize_autonomy(data.get("autonomy")),
        "agents": _normalize_agents(data.get("agents")),
        "commercial": _normalize_commercial(data.get("commercial")),
    }


def save_command_center_settings(settings: CommandCenterSettings) -> None:
    data = load_config()
    data["autonomy"] = _normalize_autonomy(settings.get("autonomy"))
    data["agents"] = _normalize_agents(settings.get("agents"))
    data["commercial"] = _normalize_commercial(settings.get("commercial"))
    save_config(data)


def hash_pin(pin: str) -> str:
    clean = (pin or "").strip()
    if not clean:
        return ""
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def verify_pin(pin: str, pin_hash: str) -> bool:
    if not (pin_hash or "").strip():
        return True
    return hash_pin(pin) == pin_hash.strip()


def effective_autonomy_level(autonomy: AutonomySettings) -> int:
    return min(autonomy["level"], autonomy["max_level"])


def effective_commercial_tone(commercial: CommercialSettings) -> int:
    return min(commercial["tone"], commercial["max_tone"])
