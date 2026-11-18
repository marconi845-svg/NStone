"""
Caricamento profili mappa DB (synthetic plant / CNC + sim locale).

Public tree ships only NStone-authored demo maps under plc_maps/.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MAP_PROFILE_PLANT = "plant_v1"
MAP_PROFILE_SIM = "sim_v1"
MAP_PROFILE_OEM_CNC = "oem_cnc_v1"
MAP_PROFILES = (MAP_PROFILE_PLANT, MAP_PROFILE_SIM, MAP_PROFILE_OEM_CNC)

_MAP_DIR = PROJECT_ROOT / "plc_maps"
_PLANT_JSON = _MAP_DIR / "plant_v1.json"
_SIM_JSON = _MAP_DIR / "sim_v1.json"
_OEM_CNC_JSON = _MAP_DIR / "oem_cnc_v1.json"

_CACHE: Dict[str, Dict[str, Any]] = {}

SIZE_PRESETS = (256, 512, 1024, 2048)
DEFAULT_EXPLORE_SIZE = 256


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_map_json_path(profile_id: str) -> Path:
    mapping = {
        MAP_PROFILE_PLANT: ("plant_v1.json", _PLANT_JSON),
        MAP_PROFILE_SIM: ("sim_v1.json", _SIM_JSON),
        MAP_PROFILE_OEM_CNC: ("oem_cnc_v1.json", _OEM_CNC_JSON),
    }
    if profile_id not in mapping:
        raise ValueError(f"Profilo mappa sconosciuto: {profile_id!r}")
    fname, default = mapping[profile_id]
    if _is_frozen():
        exe = Path(sys.executable).parent
        for candidate in (
            exe / "plc_maps" / fname,
            exe / "_internal" / "plc_maps" / fname,
            exe / fname,
        ):
            if candidate.is_file():
                return candidate
    return default


def load_map_document(profile_id: str) -> Dict[str, Any]:
    if profile_id in _CACHE:
        return _CACHE[profile_id]
    path = resolve_map_json_path(profile_id)
    if not path.is_file():
        raise FileNotFoundError(f"Mappa non trovata: {path}")
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"JSON mappa non valido: {path}")
    _CACHE[profile_id] = doc
    return doc


def default_map_profile(mode: str, machine_id: str = "") -> str:
    if mode != "live":
        return MAP_PROFILE_SIM
    if machine_id == "cnc":
        return MAP_PROFILE_OEM_CNC
    return MAP_PROFILE_PLANT


def normalize_map_profile(value: Any, mode: str = "sim", machine_id: str = "") -> str:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in MAP_PROFILES:
            return v
        if v in ("plant", "live_map", "plant_map"):
            return MAP_PROFILE_PLANT
        if v in ("sim", "simulator", "local"):
            return MAP_PROFILE_SIM
        if v in ("oem", "cnc", "oem_cnc", "plant_cnc"):
            return MAP_PROFILE_OEM_CNC
    return default_map_profile(mode, machine_id)


@dataclass
class ResolvedDbBlock:
    number: int
    symbolic_name: str
    size_bytes: int
    direction: str
    poll_interval_ms: Optional[int]
    variables: List[Dict[str, Any]] = field(default_factory=list)
    title: str = ""

    def tab_title(self) -> str:
        return f"DB{self.number} — {self.symbolic_name}"


def _block_by_number(doc: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    blocks: Dict[int, Dict[str, Any]] = {}
    for block in doc.get("data_blocks") or []:
        try:
            num = int(block.get("number"))
        except (TypeError, ValueError):
            continue
        blocks[num] = block
    return blocks


def resolve_blocks_for_machine(profile_id: str, machine_id: str) -> List[ResolvedDbBlock]:
    doc = load_map_document(profile_id)
    by_num = _block_by_number(doc)
    profiles = doc.get("machine_profiles") or {}
    machine_cfg = profiles.get(machine_id) if isinstance(profiles, dict) else {}
    if not isinstance(machine_cfg, dict):
        machine_cfg = {}

    wanted = machine_cfg.get("blocks") or machine_cfg.get("priority_dbs")
    if isinstance(wanted, list) and wanted:
        numbers = [int(n) for n in wanted]
    else:
        numbers = sorted(by_num.keys())

    overrides = machine_cfg.get("block_overrides") or {}
    var_filter = machine_cfg.get("variable_filter") or {}
    resolved: List[ResolvedDbBlock] = []
    for db_num in numbers:
        raw = by_num.get(db_num)
        if not raw:
            continue
        size = int(raw.get("size_bytes", DEFAULT_EXPLORE_SIZE))
        ov = overrides.get(str(db_num)) or overrides.get(db_num)
        if isinstance(ov, dict) and "size_bytes" in ov:
            size = int(ov["size_bytes"])
        allowed = var_filter.get(str(db_num))
        variables = flatten_variables_for_block(raw, allowed)
        resolved.append(
            ResolvedDbBlock(
                number=db_num,
                symbolic_name=str(raw.get("symbolic_name", f"DB{db_num}")),
                size_bytes=size,
                direction=str(raw.get("direction", "plc_to_sw")),
                poll_interval_ms=raw.get("poll_interval_ms"),
                variables=variables,
            )
        )
    return resolved


def list_all_db_numbers(profile_id: str, machine_id: str) -> List[int]:
    return sorted({b.number for b in resolve_blocks_for_machine(profile_id, machine_id)})


def find_block_spec(
    profile_id: str, machine_id: str, db_number: int
) -> Optional[ResolvedDbBlock]:
    for block in resolve_blocks_for_machine(profile_id, machine_id):
        if block.number == db_number:
            return block
    doc = load_map_document(profile_id)
    raw = _block_by_number(doc).get(db_number)
    if not raw:
        return None
    return ResolvedDbBlock(
        number=db_number,
        symbolic_name=str(raw.get("symbolic_name", f"DB{db_number}")),
        size_bytes=int(raw.get("size_bytes", DEFAULT_EXPLORE_SIZE)),
        direction=str(raw.get("direction", "plc_to_sw")),
        poll_interval_ms=raw.get("poll_interval_ms"),
        variables=flatten_variables_for_block(raw, None),
    )


def suggested_read_size(
    profile_id: str, machine_id: str, db_number: int, preset: Optional[int] = None
) -> int:
    if preset is not None and preset > 0:
        return int(preset)
    spec = find_block_spec(profile_id, machine_id, db_number)
    if spec is not None:
        return spec.size_bytes
    return DEFAULT_EXPLORE_SIZE


def flatten_variables_for_block(
    block: Dict[str, Any],
    allowed_names: Optional[Any],
) -> List[Dict[str, Any]]:
    from plc.plc_map_decoder import flatten_block_variables

    rows = flatten_block_variables(block)
    if allowed_names is None:
        return rows
    if not isinstance(allowed_names, list):
        return rows
    allowed = set(allowed_names)
    return [r for r in rows if r.get("name") in allowed]


def describe_map_profile(profile_id: str) -> str:
    try:
        doc = load_map_document(profile_id)
        title = doc.get("title") or profile_id
        ver = doc.get("version", "?")
        return f"{title} (v{ver})"
    except (OSError, ValueError, json.JSONDecodeError):
        return profile_id


_MACHINE_DISPLAY: Dict[str, Dict[str, str]] = {
    "multifilo": {
        "model": "Multifilo (demo)",
        "manufacturer": "NStone demo",
        "plc": "Snap7 simulator",
    },
    "lucidatrice": {
        "model": "Polisher (demo)",
        "manufacturer": "NStone demo",
        "plc": "Snap7 simulator",
    },
    "cnc": {
        "model": "CNC (demo placeholder)",
        "manufacturer": "NStone demo",
        "plc": "Snap7 simulator",
    },
}


def build_machine_debug_banner(
    profile_id: str, machine_id: str, plc_settings: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    meta = dict(_MACHINE_DISPLAY.get(machine_id, {}))
    try:
        doc = load_map_document(profile_id)
        profiles = doc.get("machine_profiles") or {}
        mp = profiles.get(machine_id) if isinstance(profiles, dict) else None
        if isinstance(mp, dict):
            for k in ("model", "manufacturer", "plc"):
                if k in mp:
                    meta[k] = str(mp[k])
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    dbs = list_all_db_numbers(profile_id, machine_id)
    meta["map_profile"] = profile_id
    meta["dbs"] = ", ".join(f"DB{n}" for n in dbs) or "—"
    if plc_settings:
        meta["endpoint"] = (
            f"{plc_settings.get('ip', '?')}:{plc_settings.get('port', 102)} "
            f"R{plc_settings.get('rack', 0)}/S{plc_settings.get('slot', 1)}"
        )
    return meta


def iter_full_map_documentation(
    profile_id: str, machine_id: str
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for db_num in list_all_db_numbers(profile_id, machine_id):
        spec = find_block_spec(profile_id, machine_id, db_num)
        if spec is None:
            continue
        for var in spec.variables:
            rows.append(
                {
                    "db": db_num,
                    "offset": var.get("offset"),
                    "name": var.get("name"),
                    "type": var.get("type"),
                    "unit": var.get("unit", ""),
                    "description": var.get("comment_it") or var.get("comment") or "",
                }
            )
    return rows


# Back-compat aliases used by older tests / UI (DB8 OEM extension removed from public tree)
def load_db8_document() -> Dict[str, Any]:
    raise FileNotFoundError("DB8 OEM extension is not shipped in the public tree")


def resolve_db8_block() -> ResolvedDbBlock:
    raise FileNotFoundError("DB8 OEM extension is not shipped in the public tree")
