"""
Test canale scrittura PLC deterministico (plc_write_governor).

Copre: whitelist da mappa, tipo/range/step/cooldown, emergenza, stati
ammessi, autonomy policy, shadow mode, parsing intent del modello.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import plc.plc_map_loader as plc_map_loader
from core.autonomy_policy import AutonomyPolicy, PolicyResult
from plc.plc_write_governor import (
    WritableVar,
    WriteGovernor,
    WriteRequest,
    build_write_intent_prompt,
    describe_whitelist_for_prompt,
    intent_to_request,
    load_writable_variables,
    map_is_placeholder,
    parse_model_intent,
)


# ---------------------------------------------------------------------------
# Attrezzi
# ---------------------------------------------------------------------------

class AllowAllPolicy:
    def allow(self, action, ctx=None):
        return PolicyResult(True, "test: sempre permesso")


class DenyAllPolicy:
    def allow(self, action, ctx=None):
        return PolicyResult(False, "test: sempre negato")


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakePlcClient:
    """Client con memoria: registra le scritture per verificarle nei test."""

    def __init__(self):
        self.memory = {}
        self.writes = []

    def _read_bytes(self, db, offset, size):
        return self.memory.get((db, offset), b"\x00" * size)

    def _write_bytes(self, db, offset, data):
        self.memory[(db, offset)] = bytes(data)
        self.writes.append((db, offset, bytes(data)))
        return True


FEED_VAR = WritableVar(
    name="cmd_feed_override",
    db_number=101,
    offset=0,
    var_type="REAL",
    unit="%",
    min_value=50.0,
    max_value=120.0,
    max_step=10.0,
    cooldown_s=10.0,
    allowed_states=("RUN", "HOLD"),
    step_reference="feed_override",
)

SPINDLE_VAR = WritableVar(
    name="cmd_spindle_override",
    db_number=101,
    offset=4,
    var_type="REAL",
    unit="%",
    min_value=80.0,
    max_value=110.0,
    max_step=5.0,
    cooldown_s=15.0,
    allowed_states=("RUN",),
    step_reference="",  # nessuna lettura live: riferimento = ultima scrittura
)

BOOL_VAR = WritableVar(
    name="cmd_coolant_on",
    db_number=101,
    offset=8,
    var_type="BOOL",
    allowed_states=("RUN", "HOLD", "READY"),
)


def make_governor(shadow=True, policy=None, clock=None, variables=None,
                  audit_log=None):
    return WriteGovernor(
        "cnc",
        variables=variables or [FEED_VAR, SPINDLE_VAR, BOOL_VAR],
        placeholder=False,
        policy=policy or AllowAllPolicy(),
        shadow=shadow,
        clock=clock or FakeClock(),
        audit_fn=(audit_log.append if audit_log is not None else (lambda d: None)),
    )


def run_status(feed_override=100.0):
    return {
        "machine_state": "RUN",
        "raw_values": {"feed_override": feed_override, "codice_allarme": 0},
    }


def req(variable="cmd_feed_override", value=105.0, reason="test"):
    return WriteRequest(
        machine_id="cnc", variable=variable, value=value, reason=reason
    )


def check(decision, name):
    for c in decision.checks:
        if c.name == name:
            return c
    raise AssertionError(f"check '{name}' non presente in {decision.checks}")


# ---------------------------------------------------------------------------
# Whitelist dalla mappa
# ---------------------------------------------------------------------------

def test_oem_map_declares_writable_vars():
    # Public tree ships a read-only synthetic CNC placeholder (no live override vars).
    variables = load_writable_variables("oem_cnc_v1", "cnc")
    assert variables == []
    assert map_is_placeholder("oem_cnc_v1") is True


def test_oem_map_is_placeholder_so_governor_refuses_everything():
    assert map_is_placeholder("oem_cnc_v1") is True
    gov = WriteGovernor("cnc", profile_id="oem_cnc_v1", policy=AllowAllPolicy())
    decision = gov.evaluate(req(), current_status=run_status())
    assert decision.allowed is False
    assert check(decision, "map_not_placeholder").passed is False


def test_whitelist_from_injected_doc():
    doc = {
        "placeholder": False,
        "data_blocks": [
            {
                "number": 50,
                "direction": "sw_to_plc",
                "variables": [
                    {"offset": 0, "type": "INT", "name": "setpoint",
                     "writable": True, "min": 0, "max": 10},
                    {"offset": 2, "type": "INT", "name": "solo_lettura"},
                ],
            }
        ],
    }
    plc_map_loader._CACHE["test_write_v1"] = doc
    try:
        variables = load_writable_variables("test_write_v1")
        assert [v.name for v in variables] == ["setpoint"]
        assert variables[0].db_number == 50
        assert map_is_placeholder("test_write_v1") is False
    finally:
        plc_map_loader._CACHE.pop("test_write_v1", None)


# ---------------------------------------------------------------------------
# Percorso felice e rifiuti deterministici
# ---------------------------------------------------------------------------

def test_valid_write_allowed():
    gov = make_governor()
    decision = gov.evaluate(req(value=105.0), current_status=run_status(100.0))
    assert decision.allowed is True
    assert all(c.passed for c in decision.checks)


def test_unknown_variable_rejected():
    gov = make_governor()
    decision = gov.evaluate(
        req(variable="velocita_mandrino", value=5000),
        current_status=run_status(),
    )
    assert decision.allowed is False
    assert check(decision, "variable_whitelisted").passed is False


def test_range_boundaries():
    gov = make_governor()
    ok = gov.evaluate(req(value=120.0), current_status=run_status(115.0))
    assert ok.allowed is True  # limite incluso
    too_high = gov.evaluate(req(value=120.5), current_status=run_status(115.0))
    assert too_high.allowed is False
    assert check(too_high, "range").passed is False
    too_low = gov.evaluate(req(value=49.9), current_status=run_status(55.0))
    assert check(too_low, "range").passed is False


def test_no_clamping_out_of_range_is_rejected_not_adjusted():
    gov = make_governor()
    decision = gov.evaluate(req(value=200.0), current_status=run_status())
    assert decision.allowed is False
    assert decision.request.value == 200.0  # mai modificato silenziosamente


def test_max_step_from_live_reference():
    gov = make_governor()
    ok = gov.evaluate(req(value=110.0), current_status=run_status(100.0))
    assert ok.allowed is True  # delta 10 = step massimo
    too_big = gov.evaluate(req(value=111.0), current_status=run_status(100.0))
    assert too_big.allowed is False
    assert check(too_big, "max_step").passed is False


def test_max_step_without_any_reference_rejected():
    gov = make_governor()
    # cmd_spindle_override non ha step_reference e nessuna scrittura precedente
    decision = gov.evaluate(
        req(variable="cmd_spindle_override", value=100.0),
        current_status=run_status(),
    )
    assert decision.allowed is False
    assert check(decision, "max_step").passed is False


def test_max_step_uses_last_accepted_write_as_reference():
    clock = FakeClock()
    gov = make_governor(clock=clock)
    # Prima scrittura accettata (shadow) su feed: fissa il riferimento interno
    first = gov.execute(req(value=105.0), current_status=run_status(100.0))
    assert first.allowed is True
    clock.advance(60)
    # Status senza feed_override live: il riferimento diventa 105 (ultima accettata)
    status_no_ref = {"machine_state": "RUN", "raw_values": {}}
    ok = gov.evaluate(req(value=112.0), current_status=status_no_ref)
    assert ok.allowed is True  # |112-105| = 7 <= 10
    too_big = gov.evaluate(req(value=116.0), current_status=status_no_ref)
    assert too_big.allowed is False  # |116-105| = 11 > 10


def test_no_op_write_rejected():
    """Scrivere il valore già presente è inutile: rifiuto deterministico."""
    gov = make_governor()
    decision = gov.evaluate(req(value=100.0), current_status=run_status(100.0))
    assert decision.allowed is False
    assert check(decision, "no_op").passed is False


def test_min_delta_rejects_insignificant_change():
    var = WritableVar(
        name="cmd_feed_override", db_number=101, offset=0, var_type="REAL",
        unit="%", min_value=50.0, max_value=120.0, max_step=10.0,
        min_delta=1.0, allowed_states=("RUN",), step_reference="feed_override",
    )
    gov = make_governor(variables=[var])
    too_small = gov.evaluate(req(value=100.5), current_status=run_status(100.0))
    assert too_small.allowed is False
    assert check(too_small, "no_op").passed is False
    enough = gov.evaluate(req(value=101.0), current_status=run_status(100.0))
    assert enough.allowed is True  # delta 1.0 = soglia inclusa


def test_no_op_passes_without_reference():
    """Senza riferimento il delta non è verificabile: ci pensa max_step."""
    gov = make_governor()
    decision = gov.evaluate(
        req(variable="cmd_spindle_override", value=100.0),
        current_status=run_status(),
    )
    # max_step boccia (nessun riferimento), no_op non pretende di sapere
    assert check(decision, "no_op").passed is True
    assert check(decision, "max_step").passed is False


def test_value_type_checks():
    gov = make_governor()
    as_string = gov.evaluate(req(value="105"), current_status=run_status())
    assert check(as_string, "value_type").passed is False
    as_bool = gov.evaluate(req(value=True), current_status=run_status())
    assert check(as_bool, "value_type").passed is False
    bool_ok = gov.evaluate(
        req(variable="cmd_coolant_on", value=True), current_status=run_status()
    )
    assert check(bool_ok, "value_type").passed is True
    bool_as_int = gov.evaluate(
        req(variable="cmd_coolant_on", value=1), current_status=run_status()
    )
    assert check(bool_as_int, "value_type").passed is False


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_blocks_rapid_writes():
    clock = FakeClock()
    gov = make_governor(clock=clock)
    first = gov.execute(req(value=105.0), current_status=run_status(100.0))
    assert first.allowed is True

    clock.advance(3)  # < cooldown_s = 10
    second = gov.evaluate(req(value=106.0), current_status=run_status(105.0))
    assert second.allowed is False
    assert check(second, "cooldown").passed is False

    clock.advance(8)  # totale 11s > 10
    third = gov.evaluate(req(value=106.0), current_status=run_status(105.0))
    assert third.allowed is True


def test_rejected_write_does_not_start_cooldown():
    clock = FakeClock()
    gov = make_governor(clock=clock)
    bad = gov.execute(req(value=500.0), current_status=run_status())
    assert bad.allowed is False
    good = gov.evaluate(req(value=105.0), current_status=run_status(100.0))
    assert good.allowed is True  # nessun cooldown ereditato dal rifiuto


# ---------------------------------------------------------------------------
# Stato macchina, emergenza, policy
# ---------------------------------------------------------------------------

def test_no_status_means_no_write():
    gov = make_governor()
    decision = gov.evaluate(req(), current_status=None)
    assert decision.allowed is False
    assert check(decision, "live_status_available").passed is False


def test_unknown_state_means_no_write():
    gov = make_governor()
    decision = gov.evaluate(
        req(), current_status={"machine_state": "UNKNOWN", "raw_values": {}}
    )
    assert decision.allowed is False
    assert check(decision, "live_status_available").passed is False


def test_emergency_blocks_write():
    gov = make_governor()
    status = {
        "machine_state": "RUN",
        "raw_values": {"feed_override": 100.0, "EmergencyStop": 1},
    }
    decision = gov.evaluate(req(value=105.0), current_status=status)
    assert decision.allowed is False
    assert check(decision, "no_emergency").passed is False


def test_error_state_blocks_write():
    gov = make_governor()
    status = {"machine_state": "ERROR", "raw_values": {"feed_override": 100.0}}
    decision = gov.evaluate(req(value=105.0), current_status=status)
    assert decision.allowed is False
    assert check(decision, "no_emergency").passed is False


def test_state_not_in_allowed_states():
    gov = make_governor()
    status = {"machine_state": "READY", "raw_values": {"feed_override": 100.0}}
    decision = gov.evaluate(req(value=105.0), current_status=status)
    assert decision.allowed is False
    assert check(decision, "machine_state_allowed").passed is False


def test_policy_denial_blocks_even_valid_write():
    gov = make_governor(policy=DenyAllPolicy())
    decision = gov.evaluate(req(value=105.0), current_status=run_status(100.0))
    assert decision.allowed is False
    assert check(decision, "autonomy_policy").passed is False


def test_real_policy_level0_denies_model_write():
    settings = {
        "autonomy": {
            "level": 0, "max_level": 2, "agents_paused": False,
            "plant_auto_plc_write": False, "plant_sim_only": True,
            "office_auto_email": False, "office_auto_stock": False,
            "require_pin_above": 2, "admin_pin_hash": "",
        },
        "agents": {"enabled": ["plant"]},
        "commercial": {"tone": 1, "max_tone": 2},
    }
    gov = make_governor(policy=AutonomyPolicy(settings))
    decision = gov.evaluate(req(value=105.0), current_status=run_status(100.0))
    assert decision.allowed is False
    assert check(decision, "autonomy_policy").passed is False


def test_real_policy_level1_allows_with_operator_approval():
    settings = {
        "autonomy": {
            "level": 1, "max_level": 2, "agents_paused": False,
            "plant_auto_plc_write": False, "plant_sim_only": True,
            "office_auto_email": False, "office_auto_stock": False,
            "require_pin_above": 2, "admin_pin_hash": "",
        },
        "agents": {"enabled": ["plant"]},
        "commercial": {"tone": 1, "max_tone": 2},
    }
    gov = make_governor(policy=AutonomyPolicy(settings))
    no_approval = gov.evaluate(req(value=105.0), current_status=run_status(100.0))
    assert no_approval.allowed is False
    approved = gov.evaluate(
        req(value=105.0), current_status=run_status(100.0), human_approved=True
    )
    assert approved.allowed is True


# ---------------------------------------------------------------------------
# Shadow mode / esecuzione
# ---------------------------------------------------------------------------

def test_shadow_mode_never_touches_plc():
    client = FakePlcClient()
    gov = make_governor(shadow=True)
    decision = gov.execute(
        req(value=105.0), client, current_status=run_status(100.0)
    )
    assert decision.allowed is True
    assert decision.executed is False
    assert "SHADOW" in decision.execute_message
    assert client.writes == []  # nessun byte verso il PLC


def test_enforce_mode_writes_to_plc():
    client = FakePlcClient()
    gov = make_governor(shadow=False)
    decision = gov.execute(
        req(value=105.0), client, current_status=run_status(100.0)
    )
    assert decision.allowed is True
    assert decision.executed is True
    assert len(client.writes) == 1
    db, offset, data = client.writes[0]
    assert (db, offset) == (101, 0)
    import struct
    assert struct.unpack(">f", data)[0] == 105.0  # big-endian S7


def test_enforce_mode_without_client_fails_closed():
    gov = make_governor(shadow=False)
    decision = gov.execute(req(value=105.0), None, current_status=run_status(100.0))
    assert decision.allowed is False
    assert decision.executed is False


def test_rejected_write_never_reaches_plc_even_in_enforce():
    client = FakePlcClient()
    gov = make_governor(shadow=False)
    decision = gov.execute(req(value=500.0), client, current_status=run_status())
    assert decision.allowed is False
    assert client.writes == []


def test_every_execute_is_audited_accept_and_reject():
    audit = []
    gov = make_governor(audit_log=audit)
    gov.execute(req(value=105.0), current_status=run_status(100.0))
    gov.execute(req(value=500.0), current_status=run_status(100.0))
    assert len(audit) == 2
    assert audit[0].allowed is True and audit[0].shadow is True
    assert audit[1].allowed is False
    payload = audit[1].to_payload()
    assert payload["request"]["value"] == 500.0
    assert any(c["name"] == "range" and not c["passed"] for c in payload["checks"])


def test_governor_default_is_shadow():
    gov = WriteGovernor("cnc", variables=[FEED_VAR], placeholder=False,
                        policy=AllowAllPolicy())
    assert gov.shadow is True


# ---------------------------------------------------------------------------
# Intent del modello (parsing rigido)
# ---------------------------------------------------------------------------

def test_parse_valid_write_intent():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "cmd_feed_override", '
        '"value": 95.0, "reason": "carico mandrino alto", "urgency": "normal"}'
    )
    assert err == ""
    assert intent == {
        "action": "write", "variable": "cmd_feed_override",
        "value": 95.0, "reason": "carico mandrino alto", "urgency": "normal",
    }


def test_parse_intent_in_code_fences_and_prose():
    text = (
        "Ecco la mia proposta:\n```json\n"
        '{"action": "write", "variable": "cmd_feed_override", '
        '"value": 90, "reason": "vibrazioni"}\n```\nSpero sia utile!'
    )
    intent, err = parse_model_intent(text)
    assert err == ""
    assert intent["value"] == 90
    assert intent["urgency"] == "normal"  # default


def test_parse_action_none():
    intent, err = parse_model_intent('{"action": "none", "reason": "dati ok"}')
    assert err == ""
    assert intent["action"] == "none"


def test_parse_rejects_missing_reason():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "cmd_feed_override", "value": 95}'
    )
    assert intent is None and "reason" in err


def test_parse_rejects_string_value():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "cmd_feed_override", '
        '"value": "95", "reason": "x"}'
    )
    assert intent is None and "value" in err


def test_parse_rejects_unknown_keys():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "cmd_feed_override", "value": 95, '
        '"reason": "x", "db_number": 6}'
    )
    assert intent is None and "db_number" in err


def test_parse_rejects_bad_action_and_garbage():
    intent, err = parse_model_intent('{"action": "delete_everything"}')
    assert intent is None
    intent, err = parse_model_intent("nessun json qui")
    assert intent is None
    intent, err = parse_model_intent("")
    assert intent is None


def test_parse_rejects_invalid_urgency():
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "v", "value": 1, '
        '"reason": "x", "urgency": "adesso"}'
    )
    assert intent is None and "urgency" in err


def test_intent_to_request_and_full_pipeline():
    """Intent modello → request → governor: la catena completa in shadow."""
    text = (
        '{"action": "write", "variable": "cmd_feed_override", '
        '"value": 92.0, "reason": "carico mandrino oltre 85%"}'
    )
    intent, err = parse_model_intent(text)
    assert err == ""
    request = intent_to_request(intent, "cnc")
    assert request.source == "model"
    gov = make_governor()
    decision = gov.execute(request, current_status=run_status(95.0))
    assert decision.allowed is True
    assert decision.executed is False  # shadow: mai scritto davvero


def test_malicious_intent_out_of_whitelist_rejected_by_governor():
    """Anche se il modello 'inventa' una variabile, il governor la ferma."""
    intent, err = parse_model_intent(
        '{"action": "write", "variable": "CmdEmergency", '
        '"value": 1, "reason": "test"}'
    )
    assert err == ""  # sintatticamente valido...
    gov = make_governor()
    decision = gov.execute(
        intent_to_request(intent, "cnc"), current_status=run_status()
    )
    assert decision.allowed is False  # ...ma semanticamente rifiutato


# ---------------------------------------------------------------------------
# Prompt whitelist
# ---------------------------------------------------------------------------

def test_whitelist_prompt_mentions_limits():
    text = describe_whitelist_for_prompt([FEED_VAR])
    assert "cmd_feed_override" in text
    assert "[50.0..120.0]" in text
    assert "step max 10.0" in text
    assert "cooldown 10s" in text
    assert "RUN" in text


def test_whitelist_prompt_mentions_min_delta():
    var = WritableVar(
        name="v", db_number=1, offset=0, var_type="REAL", min_delta=1.0
    )
    text = describe_whitelist_for_prompt([var])
    assert "variazione minima 1.0" in text


def test_build_write_intent_prompt_structure():
    prompt = build_write_intent_prompt("STATO: RUN", "ridurre vibrazioni", [FEED_VAR])
    assert "cmd_feed_override" in prompt
    assert "STATO: RUN" in prompt
    assert '"action": "none"' in prompt
