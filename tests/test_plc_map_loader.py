"""Test loader/decoder mappe PLC (synthetic public maps)."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plc.plc_map_decoder import decode_variables, format_display_value
from plc.plc_map_loader import (
    MAP_PROFILE_OEM_CNC,
    MAP_PROFILE_PLANT,
    MAP_PROFILE_SIM,
    list_all_db_numbers,
    load_db8_document,
    load_map_document,
    resolve_blocks_for_machine,
    suggested_read_size,
)


def test_load_plant_document():
    doc = load_map_document(MAP_PROFILE_PLANT)
    assert "synthetic" in (doc.get("title") or "").lower() or "demo" in (doc.get("title") or "").lower()
    assert len(doc.get("data_blocks", [])) >= 1


def test_resolve_plant_multifilo_blocks():
    blocks = resolve_blocks_for_machine(MAP_PROFILE_PLANT, "multifilo")
    numbers = [b.number for b in blocks]
    assert 1 in numbers
    assert 2 in numbers
    db1 = next(b for b in blocks if b.number == 1)
    assert db1.size_bytes >= 4
    assert any(v.get("name") == "stato" for v in db1.variables)


def test_resolve_sim_multifilo_has_status():
    blocks = resolve_blocks_for_machine(MAP_PROFILE_SIM, "multifilo")
    db1 = next(b for b in blocks if b.number == 1)
    names = {v["name"] for v in db1.variables}
    assert "stato" in names


def test_decode_sim_db1_buffer():
    blocks = resolve_blocks_for_machine(MAP_PROFILE_SIM, "multifilo")
    db1 = next(b for b in blocks if b.number == 1)
    data = bytes([1, 1, 0, 0, 0, 0, 0])
    decoded = decode_variables(data, db1.variables)
    assert decoded["stato"] == 1
    assert decoded["allarme_attivo"] is True
    assert format_display_value(decoded["emergenza"], "BOOL") == "FALSE"


def test_plant_has_no_oem_db8_extension():
    numbers = list_all_db_numbers(MAP_PROFILE_PLANT, "multifilo")
    assert 8 not in numbers
    with pytest.raises(FileNotFoundError):
        load_db8_document()
    assert suggested_read_size(MAP_PROFILE_PLANT, "multifilo", 1) >= 4


def test_oem_cnc_placeholder_map():
    doc = load_map_document(MAP_PROFILE_OEM_CNC)
    assert doc.get("placeholder") is True
    blocks = resolve_blocks_for_machine(MAP_PROFILE_OEM_CNC, "cnc")
    assert blocks and blocks[0].number == 100
