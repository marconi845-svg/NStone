"""Test bridge motore Rust PLC."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plc.plc_map_loader import MAP_PROFILE_SIM, resolve_blocks_for_machine
from plc.plc_rust_bridge import (
    build_rust_poll_plan,
    normalize_rust_snapshot,
    rust_plc_engine_available,
)


def test_build_rust_poll_plan():
    blocks = resolve_blocks_for_machine(MAP_PROFILE_SIM, "multifilo")
    plan = build_rust_poll_plan(blocks, 1, 4, MAP_PROFILE_SIM, "multifilo")
    assert "blocks" in plan
    assert len(plan["blocks"]) >= 1
    assert plan["blocks"][0]["db_number"] == 1


def test_normalize_rust_explore():
    snap = {
        "blocks": {"1": {"stato": 1}},
        "explore": {
            "db_number": 1,
            "raw": [1, 0, 0, 0],
            "decoded": {"stato": 1},
            "size": 4,
            "source": "rust",
        },
        "engine": "rust",
    }
    out = normalize_rust_snapshot(snap)
    assert isinstance(out["explore"], tuple)
    assert out["explore"][0] == 1
    assert out["explore"][1] == bytes([1, 0, 0, 0])


def test_rust_availability_is_bool():
    assert isinstance(rust_plc_engine_available(), bool)
