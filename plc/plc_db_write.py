"""
Scrittura controllata DB6 (comandi) con log e undo.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class WriteLogEntry:
    timestamp: str
    db_number: int
    offset: int
    var_type: str
    name: str
    old_bytes: bytes
    new_bytes: bytes
    success: bool
    message: str


class PlcWriteGuard:
    """Blocca scritture se emergenza attiva (DB1 offset tipico)."""

    EMERGENCY_NAMES = frozenset(
        {"EmergencyStop", "emergenza", "CmdEmergency", "Alarm_Emergency"}
    )

    @staticmethod
    def emergency_active(db1_values: Optional[Dict[str, Any]]) -> bool:
        if not db1_values:
            return False
        for key, val in db1_values.items():
            if key in PlcWriteGuard.EMERGENCY_NAMES and val:
                return True
            if "emerg" in key.lower() and val:
                return True
        return False


def encode_value(var_type: str, value: Any) -> Optional[bytes]:
    t = var_type.upper()
    if t == "BOOL":
        return bytes([1 if value else 0])
    if t == "BYTE":
        return bytes([int(value) & 0xFF])
    if t == "INT":
        # Siemens S7 è big-endian (coerente con plc_map_decoder e client snap7)
        return struct.pack(">h", int(value))
    if t == "REAL":
        return struct.pack(">f", float(value))
    return None


def write_variable(
    plc_client: Any,
    db_number: int,
    offset: int,
    var_type: str,
    value: Any,
    *,
    name: str = "",
) -> Tuple[bool, str, bytes, bytes]:
    writer = getattr(plc_client, "_write_bytes", None)
    reader = getattr(plc_client, "_read_bytes", None)
    if not callable(writer):
        return False, "Client senza scrittura", b"", b""
    payload = encode_value(var_type, value)
    if payload is None:
        return False, f"Tipo non supportato: {var_type}", b"", b""
    old = b""
    if callable(reader):
        prev = reader(db_number, offset, len(payload))
        if prev is not None:
            old = bytes(prev)
    ok = writer(db_number, offset, bytearray(payload))
    msg = "OK" if ok else "Scrittura fallita"
    return ok, msg, old, payload


class PlcWriteJournal:
    def __init__(self, max_entries: int = 50):
        self._entries: List[WriteLogEntry] = []
        self._max = max_entries
        self._undo_stack: List[WriteLogEntry] = []

    def entries(self) -> List[WriteLogEntry]:
        return list(self._entries)

    def push(self, entry: WriteLogEntry) -> None:
        self._entries.insert(0, entry)
        if entry.success:
            self._undo_stack.append(entry)
        if len(self._entries) > self._max:
            self._entries.pop()

    def pop_undo(self) -> Optional[WriteLogEntry]:
        if not self._undo_stack:
            return None
        return self._undo_stack.pop()

    @staticmethod
    def make_entry(
        db_number: int,
        offset: int,
        var_type: str,
        name: str,
        old_bytes: bytes,
        new_bytes: bytes,
        success: bool,
        message: str,
    ) -> WriteLogEntry:
        return WriteLogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            db_number=db_number,
            offset=offset,
            var_type=var_type,
            name=name,
            old_bytes=old_bytes,
            new_bytes=new_bytes,
            success=success,
            message=message,
        )
