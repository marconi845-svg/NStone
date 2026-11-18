"""Test piccolo override CNC: solo SHADOW/BENCH, mai trasporto PLC live."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.autonomy_policy import PolicyResult
from plc.plc_override_protocol import (
    OverrideAck,
    OverrideProtocol,
    OverrideState,
    ProtocolMode,
    SimulatedOverrideTransport,
)
from plc.plc_write_governor import WritableVar, WriteGovernor, WriteRequest


class AllowAllPolicy:
    def allow(self, action, ctx=None):
        return PolicyResult(True, "test")


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


FEED = WritableVar(
    name="cmd_feed_override",
    db_number=101,
    offset=0,
    var_type="REAL",
    unit="%",
    min_value=50.0,
    max_value=120.0,
    max_step=10.0,
    min_delta=1.0,
    cooldown_s=10.0,
    allowed_states=("RUN", "HOLD"),
    step_reference="feed_override",
)

SPINDLE = WritableVar(
    name="cmd_spindle_override",
    db_number=101,
    offset=4,
    var_type="REAL",
    min_value=80.0,
    max_value=110.0,
    max_step=5.0,
    min_delta=1.0,
    allowed_states=("RUN",),
    step_reference="spindle_speed_override",
)


def make_governor(clock=None):
    return WriteGovernor(
        "cnc",
        variables=[FEED, SPINDLE],
        placeholder=False,
        policy=AllowAllPolicy(),
        clock=clock or FakeClock(),
        audit_fn=lambda d: None,
    )


def request(value=95.0, variable="cmd_feed_override"):
    return WriteRequest(
        machine_id="cnc",
        variable=variable,
        value=value,
        reason="bench test",
        source="operator",
    )


def status(feed=100.0):
    return {
        "machine_state": "RUN",
        "raw_values": {
            "feed_override": feed,
            "spindle_speed_override": 100.0,
        },
    }


def make_protocol(mode=ProtocolMode.SHADOW, transport=None, clock=None, audit=None):
    clock = clock or FakeClock()
    return OverrideProtocol(
        make_governor(clock),
        mode=mode,
        transport=transport,
        timeout_s=0.2,
        poll_interval_s=0.05,
        clock=clock,
        sleep=clock.sleep,
        audit_fn=(audit.append if audit is not None else lambda r: None),
    )


def test_default_shadow_approves_without_touching_transport():
    transport = SimulatedOverrideTransport()
    protocol = make_protocol(transport=transport)
    result = protocol.submit(
        request(), current_status=status(), human_approved=True
    )
    assert result.state == OverrideState.SHADOW_APPROVED
    assert result.allowed is True
    assert result.executed is False
    assert transport.requests == []


def test_governor_rejection_stops_before_transport():
    transport = SimulatedOverrideTransport()
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=transport)
    result = protocol.submit(
        request(300.0), current_status=status(), human_approved=True
    )
    assert result.state == OverrideState.REJECTED
    assert "Governor" in result.reason
    assert transport.requests == []


def test_protocol_is_restricted_to_feed_override():
    transport = SimulatedOverrideTransport()
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=transport)
    result = protocol.submit(
        request(95.0, "cmd_spindle_override"),
        current_status=status(),
        human_approved=True,
    )
    assert result.state == OverrideState.REJECTED
    assert "solo cmd_feed_override" in result.reason
    assert transport.requests == []


def test_bench_rejects_live_or_remote_endpoint():
    transport = SimulatedOverrideTransport()
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=transport)
    result = protocol.submit(
        request(),
        current_status=status(),
        human_approved=True,
        plc_mode="live",
        plc_ip="192.168.1.50",
    )
    assert result.state == OverrideState.REJECTED
    assert "BENCH bloccato" in result.reason
    assert transport.requests == []


def test_bench_requires_explicit_transport():
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=None)
    result = protocol.submit(
        request(), current_status=status(), human_approved=True
    )
    assert result.state == OverrideState.TRANSPORT_ERROR


def test_bench_request_ack_readback_verified():
    transport = SimulatedOverrideTransport()
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=transport)
    result = protocol.submit(
        request(95.0), current_status=status(100.0), human_approved=True
    )
    assert result.state == OverrideState.VERIFIED
    assert result.executed is True
    assert result.ack and result.ack.sequence == result.sequence
    assert result.readback_value == 95.0
    assert transport.requests == [
        {
            "sequence": result.sequence,
            "variable": "cmd_feed_override",
            "value": 95.0,
        }
    ]


def test_stale_ack_is_ignored_until_matching_sequence():
    transport = SimulatedOverrideTransport()
    transport.queue_ack(OverrideAck(999, True))
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=transport)
    result = protocol.submit(
        request(), current_status=status(), human_approved=True
    )
    assert result.state == OverrideState.VERIFIED
    assert result.ack.sequence == result.sequence


def test_ack_rejection_is_fail_closed():
    transport = SimulatedOverrideTransport(
        accept=False, error_code=42
    )
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=transport)
    result = protocol.submit(
        request(), current_status=status(), human_approved=True
    )
    assert result.state == OverrideState.ACK_REJECTED
    assert "42" in result.reason
    assert result.executed is False


def test_missing_ack_times_out():
    clock = FakeClock()
    transport = SimulatedOverrideTransport(auto_ack=False)
    protocol = make_protocol(
        mode=ProtocolMode.BENCH, transport=transport, clock=clock
    )
    result = protocol.submit(
        request(), current_status=status(), human_approved=True
    )
    assert result.state == OverrideState.TIMED_OUT
    assert result.elapsed_ms >= 200


def test_readback_mismatch_is_fail_closed():
    transport = SimulatedOverrideTransport(readback_offset=2.0)
    protocol = make_protocol(mode=ProtocolMode.BENCH, transport=transport)
    result = protocol.submit(
        request(95.0), current_status=status(), human_approved=True
    )
    assert result.state == OverrideState.READBACK_MISMATCH
    assert result.readback_value == 97.0
    assert result.executed is False


def test_verified_write_starts_governor_cooldown():
    clock = FakeClock()
    transport = SimulatedOverrideTransport()
    protocol = make_protocol(
        mode=ProtocolMode.BENCH, transport=transport, clock=clock
    )
    first = protocol.submit(
        request(95.0), current_status=status(100.0), human_approved=True
    )
    assert first.state == OverrideState.VERIFIED
    second = protocol.submit(
        request(94.0), current_status=status(95.0), human_approved=True
    )
    assert second.state == OverrideState.REJECTED
    assert "cooldown" in second.reason
    assert len(transport.requests) == 1


def test_sequence_increments_and_every_result_is_audited():
    audit = []
    protocol = make_protocol(audit=audit)
    one = protocol.submit(
        request(95.0), current_status=status(), human_approved=True
    )
    two = protocol.submit(
        request(94.0), current_status=status(), human_approved=True
    )
    assert (one.sequence, two.sequence) == (1, 2)
    assert audit == [one, two]
    assert audit[0].to_payload()["state"] == "shadow_approved"
