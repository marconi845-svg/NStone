"""Test modulo machine_plc_config."""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.machine_plc_config as mpc


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(mpc, "iter_config_paths", lambda: [cfg])
    monkeypatch.setattr(mpc, "find_config_file", lambda: cfg if cfg.is_file() else None)
    monkeypatch.setattr(mpc, "get_config_path", lambda: cfg)
    return cfg


def test_load_machines_defaults_when_missing(isolated_config):
    machines = mpc.load_machines()
    assert machines["multifilo"]["ip"] == "127.0.0.1"
    assert machines["multifilo"]["port"] == 102
    assert machines["multifilo"]["mode"] == "sim"
    assert machines["multifilo"]["map_profile"] == "sim_v1"
    assert machines["lucidatrice"]["rack"] == 0


def test_save_machine_preserves_other_keys(isolated_config):
    isolated_config.write_text(
        json.dumps({"api_key": "secret", "theme": "viola"}, indent=2),
        encoding="utf-8",
    )
    mpc.save_machine("multifilo", {"ip": "192.168.10.20", "mode": "live"})

    data = json.loads(isolated_config.read_text(encoding="utf-8"))
    assert data["api_key"] == "secret"
    assert data["theme"] == "viola"
    assert data["machines"]["multifilo"]["ip"] == "192.168.10.20"
    assert data["machines"]["multifilo"]["mode"] == "live"
    assert data["machines"]["multifilo"]["port"] == 102


def test_save_machine_unknown_id():
    with pytest.raises(ValueError, match="Macchina sconosciuta"):
        mpc.save_machine("not_a_machine", {"ip": "1.2.3.4"})


def test_get_machine(isolated_config):
    mpc.save_machine("lucidatrice", {"ip": "192.168.10.30", "slot": 1})
    m = mpc.get_machine("lucidatrice")
    assert m["ip"] == "192.168.10.30"
    assert m["port"] == 102


def test_describe_plc_endpoint_live():
    cfg = mpc._normalize_machine(
        {"ip": "192.168.10.20", "port": 102, "rack": 0, "slot": 1, "mode": "live"}
    )
    text = mpc.describe_plc_endpoint(cfg)
    assert "192.168.10.20:102" in text
    assert "[live]" in text
    assert "(locale)" not in text


def test_seed_ethernet_status():
    cfg = mpc.get_machine("multifilo")
    seed = mpc.seed_ethernet_status(cfg, connected=True)
    assert seed["ip"] == cfg["ip"]
    assert seed["connected"] is True
