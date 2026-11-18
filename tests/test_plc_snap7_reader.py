"""Test lettura DB chunked e helper decoder."""

import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plc.plc_map_decoder import DiffTracker, diff_highlight_color, format_hex_dump
from plc.plc_map_decoder import format_hex_with_interpretation
from plc.plc_snap7_reader import read_db_chunked


class _FakeClient:
    def __init__(self, fail_at: int = -1):
        self.calls = []
        self._fail_at = fail_at

    def _read_bytes(self, db_number: int, offset: int, size: int):
        self.calls.append((db_number, offset, size))
        if self._fail_at == len(self.calls):
            return None
        return bytearray((offset + i) % 256 for i in range(size))


def test_read_db_chunked_single_call_under_limit():
    client = _FakeClient()
    data = read_db_chunked(client, 1, 100, chunk_size=240)
    assert data is not None
    assert len(data) == 100
    assert len(client.calls) == 1
    assert client.calls[0] == (1, 0, 100)


def test_read_db_chunked_multiple_calls():
    client = _FakeClient()
    data = read_db_chunked(client, 2, 500, chunk_size=240)
    assert data is not None
    assert len(data) == 500
    assert len(client.calls) == 3
    assert client.calls[0][1] == 0 and client.calls[0][2] == 240
    assert client.calls[1][1] == 240 and client.calls[1][2] == 240
    assert client.calls[2][1] == 480 and client.calls[2][2] == 20


def test_read_db_chunked_failure_returns_none():
    client = _FakeClient(fail_at=2)
    assert read_db_chunked(client, 1, 400, chunk_size=240) is None


def test_format_hex_dump_and_diff_colors():
    dump = format_hex_dump(bytes([0, 1, 255]))
    assert "0000:" in dump
    assert "00 01 FF" in dump
    assert diff_highlight_color(1.0, 1.0, "REAL") is None
    assert diff_highlight_color(1.0, 15.0, "REAL") == "#5a2020"
    assert diff_highlight_color(True, False, "BOOL") == "#2a4a3a"


def test_diff_tracker_colors():
    dt = DiffTracker()
    assert dt.cell_color("a", 1.0, "REAL") == DiffTracker.STABLE
    c1 = dt.cell_color("a", 2.0, "REAL")
    assert c1 == DiffTracker.CHANGED
    c2 = dt.cell_color("a", 3.0, "REAL")
    assert c2 in (DiffTracker.CHANGED, DiffTracker.RAPID)


def test_hex_interpretation_contains_real_hint():
    data = struct.pack(">f", 1.0)
    text = format_hex_with_interpretation(data + b"\x00" * 12)
    assert "REAL" in text or "Offset" in text
