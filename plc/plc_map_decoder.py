"""
Decodifica buffer DB Siemens S7 secondo definizioni mappa (plant / sim / CNC).

NOTA endianness: i PLC Siemens S7 sono BIG-ENDIAN (">h", ">f"), come i client
snap7_*_client e i server sim. Verificato al banco: la decodifica little-endian
produceva valori assurdi (es. 88946642396381184.0 al posto di 2.0 bar).
"""

from __future__ import annotations

import struct
import time
from typing import Any, Dict, List, Optional, Tuple


def _decode_bool(data: bytes, offset: int) -> Optional[bool]:
    if offset >= len(data):
        return None
    return bool(data[offset])


def _decode_byte(data: bytes, offset: int) -> Optional[int]:
    if offset >= len(data):
        return None
    return int(data[offset])


def _decode_int(data: bytes, offset: int) -> Optional[int]:
    if offset + 2 > len(data):
        return None
    return struct.unpack(">h", data[offset : offset + 2])[0]


def _decode_real(data: bytes, offset: int) -> Optional[float]:
    if offset + 4 > len(data):
        return None
    return struct.unpack(">f", data[offset : offset + 4])[0]


def decode_variable(data: bytes, offset: int, var_type: str) -> Any:
    t = var_type.upper()
    if t == "BOOL":
        return _decode_bool(data, offset)
    if t == "BYTE":
        return _decode_byte(data, offset)
    if t == "INT":
        return _decode_int(data, offset)
    if t == "REAL":
        return _decode_real(data, offset)
    return None


def format_display_value(value: Any, var_type: str) -> str:
    if value is None:
        return "—"
    t = var_type.upper()
    if t == "BOOL":
        return "TRUE" if value else "FALSE"
    if t == "BYTE":
        return str(int(value))
    if t == "INT":
        return str(int(value))
    if t == "REAL":
        try:
            f = float(value)
            if f == int(f):
                return str(int(f))
            return f"{f:.3f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def decode_variables(
    data: bytes, variables: List[Dict[str, Any]]
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for var in variables:
        name = var.get("name")
        if not name:
            continue
        offset = int(var.get("offset", 0))
        vtype = str(var.get("type", "BOOL"))
        out[name] = decode_variable(data, offset, vtype)
    return out


def format_hex_dump(data: bytes, *, bytes_per_line: int = 16) -> str:
    if not data:
        return "(vuoto)"
    lines: List[str] = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i : i + bytes_per_line]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:04X}: {hex_part:<{bytes_per_line * 3}}  {ascii_part}")
    return "\n".join(lines)


def diff_highlight_color(
    prev: Any, curr: Any, var_type: str
) -> Optional[str]:
    """Legacy: solo su cambio."""
    if prev is None or prev == curr:
        return None
    t = var_type.upper()
    if t in ("REAL", "INT", "BYTE"):
        try:
            delta = abs(float(curr) - float(prev))
        except (TypeError, ValueError):
            return "#4a4a6a"
        if delta >= 10.0:
            return "#5a2020"
        if delta >= 1.0:
            return "#5a5020"
        return "#204a30"
    return "#2a4a3a"


class DiffTracker:
    """
    Oscilloscopio PLC: stabile → verde tenue, cambio → giallo, burst → rosso.
    """

    STABLE = "#142818"
    CHANGED = "#5a5020"
    RAPID = "#6a2020"
    RAPID_WINDOW_S = 0.35

    def __init__(self) -> None:
        self._prev: Dict[str, Any] = {}
        self._last_change: Dict[str, float] = {}
        self._burst: Dict[str, int] = {}

    def cell_color(self, key: str, curr: Any, var_type: str) -> str:
        now = time.monotonic()
        prev = self._prev.get(key)
        if prev is None:
            self._prev[key] = curr
            return self.STABLE
        if prev == curr:
            return self.STABLE
        last = self._last_change.get(key, 0.0)
        if now - last < self.RAPID_WINDOW_S:
            self._burst[key] = self._burst.get(key, 0) + 1
        else:
            self._burst[key] = 1
        self._last_change[key] = now
        self._prev[key] = curr
        if self._burst.get(key, 0) >= 2:
            return self.RAPID
        t = var_type.upper()
        if t in ("REAL", "INT", "BYTE"):
            try:
                if abs(float(curr) - float(prev)) >= 5.0:
                    return self.RAPID
            except (TypeError, ValueError):
                pass
        return self.CHANGED

    def reset(self) -> None:
        self._prev.clear()
        self._last_change.clear()
        self._burst.clear()


def guess_type_at_offset(data: bytes, offset: int) -> List[Tuple[str, str]]:
    """Suggerimenti reverse-engineering per offset allineato."""
    hints: List[Tuple[str, str]] = []
    if offset + 1 <= len(data):
        b = data[offset]
        hints.append(("BOOL/USINT", f"{b} ({'TRUE' if b else 'FALSE'})"))
    if offset + 2 <= len(data):
        iv = struct.unpack(">h", data[offset : offset + 2])[0]
        hints.append(("INT", str(iv)))
    if offset + 4 <= len(data):
        rv = struct.unpack(">f", data[offset : offset + 4])[0]
        if abs(rv) < 1e12 and (rv == 0 or abs(rv) >= 1e-6):
            hints.append(("REAL", f"{rv:.4g}"))
    return hints


def format_hex_with_interpretation(
    data: bytes, *, bytes_per_line: int = 16, scan_step: int = 4
) -> str:
    """Hex dump + righe suggerimento tipo/valore."""
    base = format_hex_dump(data, bytes_per_line=bytes_per_line)
    if not data:
        return base
    hints_lines: List[str] = ["", "— Interpretazione automatica (allineamento 4) —"]
    max_off = min(len(data), 512)
    for off in range(0, max_off, scan_step):
        guesses = guess_type_at_offset(data, off)
        if not guesses:
            continue
        parts = [f"{name}={val}" for name, val in guesses[:2]]
        hex4 = " ".join(f"{data[off + i]:02X}" for i in range(min(4, len(data) - off)))
        hints_lines.append(f"Offset {off:3d}: {hex4:<11} → " + " | ".join(parts))
    return base + "\n".join(hints_lines)


def flatten_block_variables(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Unisce variables[] e axes[].variables[] in un elenco per tabella UI."""
    rows: List[Dict[str, Any]] = list(block.get("variables") or [])
    for axis in block.get("axes") or []:
        for var in axis.get("variables") or []:
            item = dict(var)
            axis_name = axis.get("name", "")
            if axis_name and "comment_it" not in item:
                item["comment_it"] = f"Asse {axis_name}"
            rows.append(item)
    return rows
