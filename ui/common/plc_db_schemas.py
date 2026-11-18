"""
Schema campi DB1/DB2 per pannello diagnostica Snap7 (sim multifilo / lucidatrice).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# key, etichetta, offset, unità, formatter opzionale
SchemaRow = Dict[str, Any]

_MULTIFILO_STATO = {0: "Idle", 1: "Run", 2: "Alarm"}


def _fmt_bool(value: Any) -> str:
    if value is None:
        return "—"
    return "TRUE" if value else "FALSE"


def _fmt_float(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


MULTIFILO_DB1: List[SchemaRow] = [
    {
        "key": "stato",
        "label": "stato",
        "offset": 0,
        "unit": "",
        "format": lambda v: _MULTIFILO_STATO.get(int(v), str(v)) if v is not None else "—",
    },
    {"key": "allarme_attivo", "label": "allarme_attivo", "offset": 1, "unit": "", "format": _fmt_bool},
    {"key": "emergenza", "label": "emergenza", "offset": 2, "unit": "", "format": _fmt_bool},
    {"key": "porte_aperte", "label": "porte_aperte", "offset": 3, "unit": "", "format": _fmt_bool},
]

MULTIFILO_DB2: List[SchemaRow] = [
    {"key": "velocita_filo", "label": "velocita_filo", "offset": 0, "unit": "m/s", "format": lambda v: _fmt_float(v, 3)},
    {"key": "tensione_filo", "label": "tensione_filo", "offset": 4, "unit": "N", "format": _fmt_float},
    {"key": "pressione_acqua", "label": "pressione_acqua", "offset": 8, "unit": "bar", "format": _fmt_float},
    {"key": "assorbimento_motore", "label": "assorbimento_motore", "offset": 12, "unit": "A", "format": _fmt_float},
    {"key": "metri", "label": "metri", "offset": 16, "unit": "m", "format": _fmt_float},
    {"key": "spreco", "label": "spreco", "offset": 20, "unit": "%", "format": _fmt_float},
    {"key": "deviazione", "label": "deviazione", "offset": 24, "unit": "mm", "format": _fmt_float},
]

_LUCIDATRICE_STATO = {
    0: "Idle",
    1: "Run",
    2: "Alarm",
    3: "Testine_Error",
    4: "Nastro_Error",
}

LUCIDATRICE_DB1: List[SchemaRow] = [
    {
        "key": "stato",
        "label": "stato",
        "offset": 0,
        "unit": "",
        "format": lambda v: _LUCIDATRICE_STATO.get(int(v), str(v)) if v is not None else "—",
    },
    {"key": "allarme_attivo", "label": "allarme_attivo", "offset": 1, "unit": "", "format": _fmt_bool},
    {"key": "emergenza", "label": "emergenza", "offset": 2, "unit": "", "format": _fmt_bool},
    {"key": "pressione_fuori_range", "label": "pressione_fuori_range", "offset": 3, "unit": "", "format": _fmt_bool},
    {"key": "assorbimento_anomalo", "label": "assorbimento_anomalo", "offset": 4, "unit": "", "format": _fmt_bool},
    {"key": "encoder_trave_error", "label": "encoder_trave_error", "offset": 5, "unit": "", "format": _fmt_bool},
    {"key": "finecorsa_attivo", "label": "finecorsa_attivo", "offset": 6, "unit": "", "format": _fmt_bool},
]

LUCIDATRICE_DB2: List[SchemaRow] = [
    {"key": "posizione_trave", "label": "posizione_trave", "offset": 0, "unit": "mm", "format": _fmt_float},
    {"key": "velocita_nastro", "label": "velocita_nastro", "offset": 4, "unit": "m/min", "format": _fmt_float},
    {"key": "pressione_testine", "label": "pressione_testine", "offset": 8, "unit": "bar", "format": _fmt_float},
    {"key": "assorbimento_motore_principale", "label": "assorbimento_motore_principale", "offset": 12, "unit": "A", "format": _fmt_float},
    {"key": "assorbimento_motore_nastro", "label": "assorbimento_motore_nastro", "offset": 16, "unit": "A", "format": _fmt_float},
    {"key": "metri_lavorati", "label": "metri_lavorati", "offset": 20, "unit": "m", "format": _fmt_float},
    {"key": "qualita_superficie", "label": "qualita_superficie", "offset": 24, "unit": "%", "format": _fmt_float},
    {"key": "assorbimento_testine", "label": "assorbimento_testine", "offset": 28, "unit": "A", "format": _fmt_float},
    {"key": "velocita_trave", "label": "velocita_trave", "offset": 32, "unit": "mm/s", "format": _fmt_float},
    {"key": "produzione_oraria", "label": "produzione_oraria", "offset": 36, "unit": "m/h", "format": _fmt_float},
    {"key": "contatore_pezzi", "label": "contatore_pezzi", "offset": 40, "unit": "pz", "format": _fmt_float},
]

SCHEMAS: Dict[str, Dict[str, List[SchemaRow]]] = {
    "multifilo": {"db1": MULTIFILO_DB1, "db2": MULTIFILO_DB2},
    "lucidatrice": {"db1": LUCIDATRICE_DB1, "db2": LUCIDATRICE_DB2},
}


def get_schema(machine_id: str) -> Dict[str, List[SchemaRow]]:
    if machine_id not in SCHEMAS:
        raise ValueError(f"Schema DB non definito per {machine_id!r}")
    return SCHEMAS[machine_id]


def format_field(row: SchemaRow, data: Optional[Dict[str, Any]]) -> str:
    if not data:
        return "—"
    value = data.get(row["key"])
    fmt: Optional[Callable[[Any], str]] = row.get("format")
    if fmt:
        return fmt(value)
    if value is None:
        return "—"
    return str(value)
