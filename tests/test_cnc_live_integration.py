"""Test percorso CNC live: config, mappa oem_cnc_v1, decode→status, fail-closed."""

import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from machines.cnc_adapter import create_cnc_adapter
from machines.cnc_live_integration import (
    CNCLiveStatus,
    LiveMachineState,
    apply_decoded_values,
    build_live_status,
)
from core.machine_plc_config import MACHINE_CNC, MACHINE_IDS, _normalize_machine
from plc.plc_map_loader import (
    MAP_PROFILE_OEM_CNC,
    default_map_profile,
    load_map_document,
    normalize_map_profile,
    resolve_blocks_for_machine,
)


# ---------- Config macchina 'cnc' ----------

def test_cnc_in_machine_ids():
    assert MACHINE_CNC in MACHINE_IDS


def test_cnc_live_defaults_to_oem_map():
    settings = _normalize_machine({"mode": "live"}, MACHINE_CNC)
    assert settings["mode"] == "live"
    assert settings["map_profile"] == MAP_PROFILE_OEM_CNC


def test_cnc_sim_defaults_to_sim_map():
    settings = _normalize_machine({"mode": "sim"}, MACHINE_CNC)
    assert settings["map_profile"] == "sim_v1"


def test_multifilo_live_still_defaults_to_plant():
    settings = _normalize_machine({"mode": "live"}, "multifilo")
    assert settings["map_profile"] == "plant_v1"


# ---------- Profilo mappa oem_cnc_v1 ----------

def test_default_map_profile_cnc_live():
    assert default_map_profile("live", "cnc") == MAP_PROFILE_OEM_CNC
    assert default_map_profile("live", "multifilo") == "plant_v1"
    assert default_map_profile("sim", "cnc") == "sim_v1"


def test_normalize_map_profile_aliases():
    assert normalize_map_profile("oem", "live", "cnc") == MAP_PROFILE_OEM_CNC
    assert normalize_map_profile("plant_cnc", "live") == MAP_PROFILE_OEM_CNC
    assert normalize_map_profile("oem_cnc_v1", "sim") == MAP_PROFILE_OEM_CNC


def test_oem_cnc_map_loads_and_is_placeholder():
    doc = load_map_document(MAP_PROFILE_OEM_CNC)
    assert doc.get("placeholder") is True
    blocks = resolve_blocks_for_machine(MAP_PROFILE_OEM_CNC, "cnc")
    assert len(blocks) == 1
    assert blocks[0].number == 100
    roles = {v.get("role") for v in blocks[0].variables}
    assert "machine_state" in roles
    assert "alarm_code" in roles


# ---------- Decode → status (puro, senza PLC) ----------

class _FakeBlock:
    def __init__(self, number, variables, size_bytes=64):
        self.number = number
        self.variables = variables
        self.size_bytes = size_bytes
        self.direction = "plc_to_sw"


def _oem_like_variables():
    return [
        {"offset": 0, "type": "BYTE", "name": "stato", "role": "machine_state",
         "state_map": {"0": "STOP", "1": "RUN", "2": "HOLD", "3": "ERROR"}},
        {"offset": 2, "type": "INT", "name": "allarme", "role": "alarm_code"},
        {"offset": 4, "type": "REAL", "name": "mandrino", "role": "spindle_speed"},
        {"offset": 8, "type": "REAL", "name": "feed", "role": "feed_rate"},
        {"offset": 12, "type": "REAL", "name": "x", "role": "axis_x"},
        {"offset": 16, "type": "INT", "name": "utensile", "role": "tool_number"},
    ]


def _build_buffer():
    # Big-endian: byte order Siemens S7 (come server sim e PLC reali)
    buf = bytearray(20)
    buf[0] = 1  # RUN
    struct.pack_into(">h", buf, 2, 42)      # allarme
    struct.pack_into(">f", buf, 4, 8500.0)  # mandrino RPM
    struct.pack_into(">f", buf, 8, 1200.5)  # feed
    struct.pack_into(">f", buf, 12, 315.25) # asse X
    struct.pack_into(">h", buf, 16, 7)      # utensile
    return bytes(buf)


def test_build_live_status_decodes_roles():
    block = _FakeBlock(100, _oem_like_variables(), size_bytes=20)
    status = build_live_status(
        [block], {100: _build_buffer()},
        plc_ip="192.168.0.10", plc_port=102, latency_ms=3.4,
    )
    assert status.machine_state is LiveMachineState.RUN
    assert status.alarm_code == 42
    assert status.alarm_message  # generato dal codice, mai vuoto con allarme attivo
    assert abs(status.spindle_speed - 8500.0) < 0.01
    assert abs(status.feed_rate - 1200.5) < 0.01
    assert abs(status.position.x - 315.25) < 0.01
    assert status.tool_number == 7
    assert status.plc_connected is True
    assert status.plc_ip == "192.168.0.10"
    assert status.plc_latency == 3.4


def test_build_live_status_placeholder_never_decodes():
    block = _FakeBlock(100, _oem_like_variables(), size_bytes=20)
    status = build_live_status(
        [block], {100: _build_buffer()}, map_placeholder=True,
    )
    # Con mappa placeholder nessun valore viene applicato: default onesti
    assert status.machine_state is LiveMachineState.UNKNOWN
    assert status.spindle_speed == 0.0
    assert "mappa DB da compilare" in status.program_name


def test_apply_decoded_values_ignores_none():
    status = CNCLiveStatus()
    status.spindle_speed = 0.0
    variables = [{"offset": 0, "type": "REAL", "name": "mandrino", "role": "spindle_speed"}]
    apply_decoded_values(status, variables, {"mandrino": None})
    assert status.spindle_speed == 0.0  # None non sovrascrive


def test_unknown_state_code_maps_to_unknown():
    status = CNCLiveStatus()
    variables = [{"offset": 0, "type": "BYTE", "name": "stato", "role": "machine_state"}]
    apply_decoded_values(status, variables, {"stato": 99})
    assert status.machine_state is LiveMachineState.UNKNOWN


def test_live_status_has_ui_contract_fields():
    """Campi letti da gestione_cnc_window: se manca uno, la UI esplode."""
    status = CNCLiveStatus()
    for attr in (
        "machine_state", "program_name", "current_line", "total_lines",
        "current_block", "position", "spindle_speed", "spindle_speed_override",
        "spindle_load", "spindle_temperature", "feed_rate", "feed_rate_override",
        "feed_rate_programmed", "tool_number", "tool_load", "tool_length_offset",
        "tool_radius_offset", "alarm_code", "alarm_message", "plc_connected",
        "plc_ip", "plc_port", "plc_latency", "materiale", "spessore",
        "dimensioni_l", "dimensioni_h", "dimensioni_p", "pezzi_totali",
        "pezzi_completati", "pezzi_in_lavorazione", "avanzamento_pezzo",
        "avanzamento_lotto",
    ):
        assert hasattr(status, attr), f"campo mancante nel contratto UI: {attr}"
    assert isinstance(status.machine_state.value, str)


# ---------- Cross-check deterministici ----------

def test_cross_checks_ready_with_spindle_running():
    from ui.windows.machines.gestione_cnc_window import compute_status_cross_checks
    status = CNCLiveStatus()
    status.machine_state = LiveMachineState.READY
    status.spindle_speed = 8000.0
    flags = compute_status_cross_checks(status)
    assert any("outside RUN" in f for f in flags)


def test_cross_checks_run_with_zero_spindle_and_feed():
    from ui.windows.machines.gestione_cnc_window import compute_status_cross_checks
    status = CNCLiveStatus()
    status.machine_state = LiveMachineState.RUN
    status.spindle_speed = 0.0
    status.feed_rate = 0.0
    flags = compute_status_cross_checks(status)
    assert any("spindle at 0" in f.lower() for f in flags)
    assert any("feed rate is 0" in f.lower() for f in flags)


def test_cross_checks_clean_run_has_no_flags():
    from ui.windows.machines.gestione_cnc_window import compute_status_cross_checks
    status = CNCLiveStatus()
    status.machine_state = LiveMachineState.RUN
    status.spindle_speed = 8000.0
    status.feed_rate = 500.0
    status.feed_rate_programmed = 500.0
    flags = compute_status_cross_checks(status)
    assert flags == []


def test_cross_checks_alarm_without_error_state():
    from ui.windows.machines.gestione_cnc_window import compute_status_cross_checks
    status = CNCLiveStatus()
    status.machine_state = LiveMachineState.RUN
    status.spindle_speed = 5000.0
    status.feed_rate = 400.0
    status.alarm_code = 12
    flags = compute_status_cross_checks(status)
    assert any("Alarm code 12" in f for f in flags)


# ---------- Adapter legacy fail-closed ----------

def test_cnc_adapter_refuses_connection():
    adapter = create_cnc_adapter("GENERIC_PLC")
    assert adapter.connected is False
    assert adapter.last_error
    assert adapter.connect() is False
    assert adapter.read_status() is None
