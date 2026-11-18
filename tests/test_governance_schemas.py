"""
Test contratti Pydantic del canale scrittura (governance_schemas).

Copre: intent strict (percorso Pydantic + fallback manuale identico),
esclusione fail-closed delle variabili whitelist incoerenti, contratto
del payload audit per la Governance Console.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import plc.plc_map_loader as plc_map_loader
from core.autonomy_policy import PolicyResult
from core.governance_schemas import (
    WriteDecisionPayload,
    build_map_contract_report,
    validate_intent_dict,
    validate_writable_variable,
)
from plc.plc_write_governor import (
    WritableVar,
    WriteGovernor,
    WriteRequest,
    _validate_intent_manual,
    load_writable_variables,
    parse_model_intent,
)


class AllowAllPolicy:
    def allow(self, action, ctx=None):
        return PolicyResult(True, "test")


# ---------------------------------------------------------------------------
# Intent: percorso Pydantic (via parse_model_intent)
# ---------------------------------------------------------------------------

def test_pydantic_valid_write_intent():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "cmd_feed_override", '
        '"value": 92.0, "reason": "carico alto", "urgency": "high"}'
    )
    assert err == ""
    assert intent == {
        "action": "write", "variable": "cmd_feed_override",
        "value": 92.0, "reason": "carico alto", "urgency": "high",
    }


def test_pydantic_strict_rejects_string_value():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "v", "value": "92", "reason": "x"}'
    )
    assert intent is None and "value" in err


def test_pydantic_rejects_extra_keys():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "v", "value": 92, '
        '"reason": "x", "db_number": 6}'
    )
    assert intent is None and "db_number" in err


def test_pydantic_rejects_empty_reason():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "v", "value": 92, "reason": "   "}'
    )
    assert intent is None and "reason" in err


def test_pydantic_rejects_bad_urgency_and_action():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "v", "value": 1, '
        '"reason": "x", "urgency": "subito"}'
    )
    assert intent is None and "urgency" in err
    intent, err = parse_model_intent('{"action": "cancella_tutto"}')
    assert intent is None and "action" in err


def test_pydantic_action_none_forbids_extras():
    intent, err = parse_model_intent('{"action": "none", "reason": "ok"}')
    assert err == "" and intent["action"] == "none"
    intent, err = parse_model_intent(
        '{"action": "none", "reason": "ok", "variable": "v"}'
    )
    assert intent is None


def test_pydantic_accepts_bool_value():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "cmd_coolant_on", '
        '"value": true, "reason": "temperatura"}'
    )
    assert err == "" and intent["value"] is True


def test_validate_intent_dict_rejects_non_dict():
    intent, err = validate_intent_dict(["not", "a", "dict"])
    assert intent is None


# ---------------------------------------------------------------------------
# Fallback manuale: stessa semantica del percorso Pydantic
# ---------------------------------------------------------------------------

def test_manual_fallback_parity():
    cases = [
        ({"action": "write", "variable": "v", "value": 92.0, "reason": "x"}, True),
        ({"action": "write", "variable": "v", "value": "92", "reason": "x"}, False),
        ({"action": "write", "variable": "v", "value": 92, "reason": "x",
          "extra": 1}, False),
        ({"action": "write", "variable": "v", "value": 92}, False),
        ({"action": "none", "reason": "ok"}, True),
        ({"action": "boh"}, False),
    ]
    for obj, should_pass in cases:
        pyd_intent, _ = validate_intent_dict(dict(obj))
        man_intent, _ = _validate_intent_manual(dict(obj))
        assert (pyd_intent is not None) == should_pass, obj
        assert (man_intent is not None) == should_pass, obj


# ---------------------------------------------------------------------------
# Whitelist: esclusione fail-closed delle variabili incoerenti
# ---------------------------------------------------------------------------

def _base_var(**over):
    var = {
        "offset": 0, "type": "REAL", "name": "ok_var", "writable": True,
        "min": 50.0, "max": 120.0, "max_step": 10.0, "min_delta": 1.0,
        "cooldown_s": 10, "allowed_states": ["RUN"],
    }
    var.update(over)
    return var


def test_validate_writable_variable_catches_incoherence():
    assert validate_writable_variable(_base_var()) == []
    assert validate_writable_variable(_base_var(min=200.0))  # min > max
    assert validate_writable_variable(_base_var(min_delta=15.0))  # > max_step
    assert validate_writable_variable(_base_var(type="WORD"))  # non scrivibile
    assert validate_writable_variable(_base_var(cooldown_s=-1))  # negativo
    assert validate_writable_variable(_base_var(offset=-2))  # offset negativo
    assert validate_writable_variable(_base_var(name="  "))  # nome vuoto
    assert validate_writable_variable(
        _base_var(), block_direction="plc_to_sw"
    )  # scrivibile in blocco read-only


def test_load_writable_variables_excludes_bad_vars():
    doc = {
        "placeholder": False,
        "data_blocks": [
            {
                "number": 60,
                "direction": "sw_to_plc",
                "variables": [
                    _base_var(offset=0, name="buona"),
                    _base_var(offset=4, name="min_maggiore_max", min=500.0),
                    _base_var(offset=8, name="delta_impossibile", min_delta=99.0),
                    _base_var(offset=12, name="tipo_ignoto", type="DWORD"),
                    _base_var(offset=0, name="offset_duplicato"),
                ],
            },
            {
                "number": 61,
                "direction": "plc_to_sw",
                "variables": [
                    _base_var(offset=0, name="scrivibile_in_lettura"),
                ],
            },
        ],
    }
    plc_map_loader._CACHE["test_bad_whitelist"] = doc
    try:
        variables = load_writable_variables("test_bad_whitelist")
        assert [v.name for v in variables] == ["buona"]
    finally:
        plc_map_loader._CACHE.pop("test_bad_whitelist", None)


def test_oem_map_whitelist_still_valid():
    """Public synthetic CNC map ships no writable override whitelist."""
    variables = load_writable_variables("oem_cnc_v1", "cnc")
    assert variables == []


def test_oem_map_contract_report_valid_but_placeholder():
    report = build_map_contract_report("oem_cnc_v1")
    assert report["valid"] is True
    assert report["placeholder"] is True
    assert report["writable_total"] == 0
    assert report["writable_valid"] == 0
    assert report["errors"] == []
    proto = report.get("override_protocol") or {}
    assert proto.get("live_transport_implemented", False) is False


def test_map_contract_report_exposes_fail_closed_errors():
    doc = {
        "schema": "test",
        "version": "1",
        "placeholder": False,
        "data_blocks": [
            {
                "number": 70,
                "direction": "sw_to_plc",
                "variables": [
                    _base_var(offset=0, name="buona"),
                    _base_var(offset=0, name="duplicata"),
                    _base_var(offset=4, name="range_errato", min=500.0),
                ],
            }
        ],
    }
    plc_map_loader._CACHE["test_contract_report"] = doc
    try:
        report = build_map_contract_report("test_contract_report")
        assert report["valid"] is False
        assert report["placeholder"] is False
        assert report["writable_total"] == 3
        assert report["writable_valid"] == 1
        assert report["writable_excluded"] == 2
        messages = " ".join(e["message"] for e in report["errors"])
        assert "duplicato" in messages
        assert "min (500.0) > max (120.0)" in messages
    finally:
        plc_map_loader._CACHE.pop("test_contract_report", None)


# ---------------------------------------------------------------------------
# Payload audit: contratto per la Governance Console
# ---------------------------------------------------------------------------

def test_decision_payload_matches_schema():
    var = WritableVar(
        name="cmd_feed_override", db_number=101, offset=0, var_type="REAL",
        min_value=50.0, max_value=120.0, max_step=10.0,
        allowed_states=("RUN",), step_reference="feed_override",
    )
    gov = WriteGovernor(
        "cnc", variables=[var], placeholder=False,
        policy=AllowAllPolicy(), audit_fn=lambda d: None,
    )
    status = {"machine_state": "RUN", "raw_values": {"feed_override": 100.0}}
    for value in (105.0, 500.0):  # una accettata, una rifiutata
        decision = gov.execute(
            WriteRequest("cnc", "cmd_feed_override", value, "test"),
            current_status=status,
        )
        payload = decision.to_payload()
        validated = WriteDecisionPayload.model_validate(payload)
        assert validated.allowed == decision.allowed
        assert len(validated.checks) == len(decision.checks)
