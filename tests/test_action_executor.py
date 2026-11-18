"""Test action_executor e policy con approvazione operatore."""

from core.agents_config import _normalize_autonomy, load_command_center_settings
from core.autonomy_policy import Action, ActionContext, AutonomyPolicy, reload_policy
from core.action_executor import process_operator_approval


def test_plc_write_after_human_approval_level1():
    reload_policy()
    base = load_command_center_settings()
    base["autonomy"] = _normalize_autonomy(
        {"level": 1, "max_level": 4, "plant_auto_plc_write": False}
    )
    policy = AutonomyPolicy(base)
    ctx = ActionContext(machine_id="multifilo", plc_mode="sim", human_approved=True)
    r = policy.allow(Action.PLC_WRITE, ctx)
    assert r.allowed


def test_process_approval_without_parent_still_queues(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        '{"autonomy":{"level":1,"max_level":4},"agents":{},"commercial":{}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("core.machine_plc_config.get_config_path", lambda: cfg)
    db = tmp_path / "t.db"
    monkeypatch.setattr("modules.action_store.DEFAULT_DB_PATH", db)
    monkeypatch.setattr("modules.action_store._db_path", lambda: db)
    reload_policy()

    result = process_operator_approval(
        "multifilo",
        {"action": "start", "parameter": "N/A", "value": "N/A"},
        parent_window=None,
    )
    assert result.success
    assert result.action_id is not None
