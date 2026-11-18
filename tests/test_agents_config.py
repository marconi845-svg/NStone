"""Test configurazione Agents Command Center."""

from core.agents_config import (
    effective_autonomy_level,
    effective_commercial_tone,
    hash_pin,
    load_command_center_settings,
    save_command_center_settings,
    verify_pin,
    _normalize_autonomy,
)
from core.autonomy_policy import Action, ActionContext, AutonomyPolicy, reload_policy


def test_effective_level_capped():
    a = _normalize_autonomy({"level": 4, "max_level": 1})
    assert effective_autonomy_level(a) == 1


def test_pin_hash_verify():
    h = hash_pin("1234")
    assert verify_pin("1234", h)
    assert not verify_pin("0000", h)


def test_policy_plc_write_level0():
    reload_policy()
    policy = AutonomyPolicy(
        {
            "autonomy": _normalize_autonomy({"level": 0, "max_level": 4}),
            "agents": load_command_center_settings()["agents"],
            "commercial": load_command_center_settings()["commercial"],
        }
    )
    r = policy.allow(Action.PLC_WRITE, ActionContext(plc_mode="sim"))
    assert not r.allowed


def test_save_roundtrip(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("core.machine_plc_config.get_config_path", lambda: cfg)
    settings = load_command_center_settings()
    settings["autonomy"]["level"] = 1
    save_command_center_settings(settings)
    loaded = load_command_center_settings()
    assert loaded["autonomy"]["level"] == 1
    assert effective_commercial_tone(loaded["commercial"]) <= loaded["commercial"]["max_tone"]
