"""
Configurazione PLC macchine (Multifilo, Lucidatrice, CNC) in config.json.

Percorso file unificato per dev, PyInstaller e fallback legacy (Settings).
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MACHINE_MULTIFILO = "multifilo"
MACHINE_LUCIDATRICE = "lucidatrice"
MACHINE_CNC = "cnc"
MACHINE_IDS = (MACHINE_MULTIFILO, MACHINE_LUCIDATRICE, MACHINE_CNC)

Mode = Literal["sim", "live"]
MapProfile = Literal["sim_v1", "plant_v1", "oem_cnc_v1"]


class MachinePlcSettings(TypedDict):
    ip: str
    port: int
    rack: int
    slot: int
    mode: Mode
    map_profile: str


DEFAULT_MACHINE: MachinePlcSettings = {
    "ip": "127.0.0.1",
    "port": 102,
    "rack": 0,
    "slot": 1,
    "mode": "sim",
    "map_profile": "sim_v1",
}

DEFAULT_MACHINES: Dict[str, MachinePlcSettings] = {
    MACHINE_MULTIFILO: deepcopy(DEFAULT_MACHINE),
    MACHINE_LUCIDATRICE: deepcopy(DEFAULT_MACHINE),
    MACHINE_CNC: deepcopy(DEFAULT_MACHINE),
}


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def iter_config_paths() -> List[Path]:
    """Percorsi candidati, in ordine di priorità (senza duplicati)."""
    seen: set[str] = set()
    ordered: List[Path] = []

    def add(path: Path) -> None:
        key = str(path.resolve()) if path.exists() or path.parent.exists() else str(path)
        if key not in seen:
            seen.add(key)
            ordered.append(path)

    if _is_frozen():
        exe_dir = Path(sys.executable).parent
        add(exe_dir / "config.json")
        add(exe_dir / "_internal" / "config.json")
    else:
        add(PROJECT_ROOT / "config.json")
        cwd = Path.cwd()
        if cwd.name == "fastapi_backend":
            add(cwd.parent / "config.json")
        add(cwd / "config.json")
        # Legacy: Settings salva qui
        add(PROJECT_ROOT / "ui" / "windows" / "common" / "config.json")

    return ordered


LEGACY_CONFIG_PATH = PROJECT_ROOT / "ui" / "windows" / "common" / "config.json"


def find_config_file() -> Optional[Path]:
    """Primo config.json esistente tra i candidati."""
    for path in iter_config_paths():
        if path.is_file():
            return path
    return None


def get_config_path() -> Path:
    """Percorso canonico per scrittura (sempre un solo config.json attivo)."""
    if _is_frozen():
        exe_dir = Path(sys.executable).parent
        for candidate in (exe_dir / "config.json", exe_dir / "_internal" / "config.json"):
            if candidate.is_file():
                return candidate
        return exe_dir / "config.json"
    return PROJECT_ROOT / "config.json"


def _read_config_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_config() -> Dict[str, Any]:
    """
    Carica config.json canonico e integra chiavi mancanti dal file legacy Settings.
    """
    data = _read_config_file(get_config_path())
    legacy = _read_config_file(LEGACY_CONFIG_PATH)
    if not legacy:
        return data

    legacy_key = (legacy.get("api_key") or "").strip()
    if legacy_key and not (data.get("api_key") or "").strip():
        data["api_key"] = legacy_key

    for key in ("theme", "model", "temperature", "language"):
        if key not in data and key in legacy:
            data[key] = legacy[key]

    legacy_gmail = legacy.get("gmail")
    if isinstance(legacy_gmail, dict):
        current_gmail = data.get("gmail") if isinstance(data.get("gmail"), dict) else {}
        merged_gmail = dict(legacy_gmail)
        merged_gmail.update(current_gmail)
        if merged_gmail.get("email") or merged_gmail.get("app_password"):
            data["gmail"] = merged_gmail

    return data


def save_config(updates: Dict[str, Any]) -> Path:
    """
    Unisce updates nel config esistente e salva su get_config_path().

    Returns:
        Percorso del file scritto.
    """
    path = get_config_path()
    merged = load_config()
    merged.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    return path


def _normalize_mode(value: Any) -> Mode:
    if isinstance(value, str) and value.lower() == "live":
        return "live"
    return "sim"


def _normalize_machine(
    partial: Optional[Dict[str, Any]], machine_id: str = ""
) -> MachinePlcSettings:
    base: MachinePlcSettings = deepcopy(DEFAULT_MACHINE)
    if not partial:
        if machine_id:
            base["map_profile"] = _fallback_map_profile(base["mode"], machine_id)
        return base

    if "ip" in partial and isinstance(partial["ip"], str) and partial["ip"].strip():
        base["ip"] = partial["ip"].strip()

    if "port" in partial:
        try:
            port = int(partial["port"])
            if 1 <= port <= 65535:
                base["port"] = port
        except (TypeError, ValueError):
            pass

    for key in ("rack", "slot"):
        if key in partial:
            try:
                base[key] = int(partial[key])  # type: ignore[literal-required]
            except (TypeError, ValueError):
                pass

    base["mode"] = _normalize_mode(partial.get("mode"))
    try:
        from plc.plc_map_loader import normalize_map_profile

        base["map_profile"] = normalize_map_profile(
            partial.get("map_profile"), base["mode"], machine_id
        )
    except ImportError:
        base["map_profile"] = _fallback_map_profile(base["mode"], machine_id)
    return base


def _fallback_map_profile(mode: str, machine_id: str) -> str:
    if mode != "live":
        return "sim_v1"
    return "oem_cnc_v1" if machine_id == MACHINE_CNC else "plant_v1"


def load_machines() -> Dict[str, MachinePlcSettings]:
    """Legge la sezione machines con default per ogni macchina nota."""
    config = load_config()
    raw = config.get("machines")
    if not isinstance(raw, dict):
        raw = {}

    return {
        machine_id: _normalize_machine(
            raw.get(machine_id) if isinstance(raw.get(machine_id), dict) else None,
            machine_id,
        )
        for machine_id in MACHINE_IDS
    }


def save_machine(machine_id: str, settings: Dict[str, Any]) -> Path:
    """
    Aggiorna una macchina nella sezione machines senza cancellare altre chiavi (api_key, theme, …).

    Args:
        machine_id: 'multifilo', 'lucidatrice' o 'cnc'
        settings: campi parziali (ip, port, rack, slot, mode)

    Raises:
        ValueError: machine_id non riconosciuto
    """
    if machine_id not in MACHINE_IDS:
        raise ValueError(
            f"Macchina sconosciuta: {machine_id!r}. Valori ammessi: {', '.join(MACHINE_IDS)}"
        )

    config = load_config()
    machines = config.get("machines")
    if not isinstance(machines, dict):
        machines = {}

    current = machines.get(machine_id)
    if isinstance(current, dict):
        merged_input = {**current, **settings}
    else:
        merged_input = dict(settings)

    machines[machine_id] = _normalize_machine(merged_input, machine_id)
    config["machines"] = machines
    return save_config(config)


def get_machine(machine_id: str) -> MachinePlcSettings:
    """Impostazioni di una singola macchina."""
    machines = load_machines()
    if machine_id not in machines:
        raise ValueError(
            f"Macchina sconosciuta: {machine_id!r}. Valori ammessi: {', '.join(MACHINE_IDS)}"
        )
    return machines[machine_id]


def describe_plc_endpoint(settings: MachinePlcSettings) -> str:
    """Riga leggibile IP/porta/rack/slot/mode per UI Gestione macchine."""
    ip = settings["ip"]
    mode_it = "simulazione" if settings["mode"] == "sim" else "live"
    local = " (locale)" if ip in ("127.0.0.1", "localhost", "::1") else ""
    profile = settings.get("map_profile", "sim_v1")
    return (
        f"IP: {ip}:{settings['port']}  "
        f"rack={settings['rack']}  slot={settings['slot']}  "
        f"[{mode_it}]{local}  mappa: {profile}"
    )


def seed_ethernet_status(
    settings: MachinePlcSettings, *, connected: bool = False
) -> Dict[str, Any]:
    """Stato iniziale per EthernetStatusWidget da config macchina."""
    return {
        "connected": connected,
        "state": "Connesso" if connected else "Disconnesso",
        "ip": settings["ip"],
        "port": settings["port"],
        "latency_ms": 0,
        "last_packet_time": None,
        "total_packets": 0,
        "failed_packets": 0,
        "error_count": 0,
        "last_error": None,
    }
