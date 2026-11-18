"""
Configurazione pricing (scarto %, regole globali) da config.json.
"""
from __future__ import annotations

from typing import Any, Dict


_DEFAULT_PRICING: Dict[str, Any] = {
    "scarto_pct_default": 8.0,
    "scarto_pct_marmo": 8.0,
    "scarto_pct_granito": 5.0,
    "scarto_pct_travertino": 7.0,
    "scarto_pct_quarzo": 5.0,
    "min_labor_charge_eur": 0.0,
}


def load_pricing_config() -> Dict[str, Any]:
    cfg = dict(_DEFAULT_PRICING)
    try:
        from core.machine_plc_config import load_config

        raw = load_config().get("pricing") or {}
        if isinstance(raw, dict):
            for key in _DEFAULT_PRICING:
                if key in raw and raw[key] is not None:
                    try:
                        cfg[key] = float(raw[key])
                    except (TypeError, ValueError):
                        cfg[key] = raw[key]
    except Exception:
        pass
    return cfg


def waste_pct_for_material(material_name: str, material_type: str = "") -> float:
    """Scarto % in base al tipo materiale (listino lastra)."""
    cfg = load_pricing_config()
    name = (material_name or "").lower()
    mtype = (material_type or "").lower()

    if "granit" in name or "granit" in mtype:
        return float(cfg.get("scarto_pct_granito", 5.0))
    if "travertin" in name or "travertin" in mtype:
        return float(cfg.get("scarto_pct_travertino", 7.0))
    if "quarz" in name or "quarz" in mtype:
        return float(cfg.get("scarto_pct_quarzo", 5.0))
    if any(
        k in name or k in mtype
        for k in ("marmo", "marble", "carrara", "calacatta", "statuario", "bardiglio")
    ):
        return float(cfg.get("scarto_pct_marmo", 8.0))

    return float(cfg.get("scarto_pct_default", 8.0))
