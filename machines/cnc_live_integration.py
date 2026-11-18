"""
Integrazione CNC LIVE via Snap7 (lettura read-only guidata dalla mappa DB).

Stesso contratto di segnali/status di cnc_simulator_integration, così la
finestra CNC può usare sim e live in modo intercambiabile:
  - status_updated(object)      -> CNCLiveStatus (stessi campi letti dalla UI)
  - connection_changed(bool)    -> stato connessione REALE (fail-closed)
  - diagnostics_updated(dict)   -> ping / latenza / CPU RUN-STOP

Principi:
  - Nessun dato inventato: campo non mappato = default onesto ("n/d", 0).
  - Mappa placeholder (oem_cnc_v1 non compilata): connessione e diagnostica
    funzionano, ma NON si leggono DB (evita valori spazzatura da offset finti).
  - Nessuna scrittura PLC: send_* sono fail-closed e passano da autonomy_policy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

RECONNECT_DELAY_S = 3.0
DIAGNOSTICS_EVERY_S = 5.0


class LiveMachineState(Enum):
    """Stati con gli stessi .value confrontati dalla UI CNC."""
    RUN = "RUN"
    STOP = "STOP"
    HOLD = "HOLD"
    ERROR = "ERROR"
    READY = "READY"
    UNKNOWN = "UNKNOWN"


_DEFAULT_STATE_MAP = {0: LiveMachineState.STOP, 1: LiveMachineState.RUN,
                      2: LiveMachineState.HOLD, 3: LiveMachineState.ERROR}


@dataclass
class LiveAxisPosition:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0


@dataclass
class CNCLiveStatus:
    """
    Contratto UI identico a CNCSimulatorStatus: la finestra CNC legge questi
    campi. I campi "gestionali" (materiale, pezzi, …) esistono solo nel
    simulatore: qui restano default onesti finché non arrivano da una fonte vera.
    """
    source: str = "live"
    map_placeholder: bool = False

    machine_state: LiveMachineState = LiveMachineState.UNKNOWN
    program_name: str = "n/d"
    current_line: int = 0
    current_block: str = ""
    total_lines: int = 0

    position: LiveAxisPosition = field(default_factory=LiveAxisPosition)

    spindle_speed: float = 0.0
    spindle_speed_override: float = 0.0
    spindle_load: float = 0.0
    spindle_temperature: float = 0.0

    feed_rate: float = 0.0
    feed_rate_override: float = 0.0
    feed_rate_programmed: float = 0.0

    tool_number: int = 0
    tool_load: float = 0.0
    tool_length_offset: float = 0.0
    tool_radius_offset: float = 0.0

    alarm_code: int = 0
    alarm_message: str = ""

    plc_connected: bool = False
    plc_ip: str = ""
    plc_port: int = 102
    plc_latency: float = 0.0

    # Campi solo-simulatore (casellario pezzi / commessa): default onesti.
    materiale: str = "n/d"
    quantita_lastre: int = 0
    spessore: float = 0.0
    finitura: str = "n/d"
    cliente_commessa: str = "n/d"
    avanzamento: float = 0.0
    tempo_stimato: int = 0
    tempo_rimanente: int = 0
    dimensioni_l: float = 0.0
    dimensioni_h: float = 0.0
    dimensioni_p: float = 0.0
    pezzi_totali: int = 0
    pezzi_completati: int = 0
    pezzi_in_lavorazione: int = 0
    avanzamento_pezzo: float = 0.0
    avanzamento_lotto: float = 0.0

    # Valori raw decodificati dalla mappa (nome variabile -> valore).
    raw_values: Dict[str, Any] = field(default_factory=dict)


def _decode_state(value: Any, var_spec: Dict[str, Any]) -> LiveMachineState:
    if value is None:
        return LiveMachineState.UNKNOWN
    try:
        code = int(value)
    except (TypeError, ValueError):
        return LiveMachineState.UNKNOWN
    custom = var_spec.get("state_map")
    if isinstance(custom, dict):
        name = custom.get(str(code))
        if isinstance(name, str):
            try:
                return LiveMachineState[name.upper()]
            except KeyError:
                return LiveMachineState.UNKNOWN
        return LiveMachineState.UNKNOWN
    return _DEFAULT_STATE_MAP.get(code, LiveMachineState.UNKNOWN)


def apply_decoded_values(
    status: CNCLiveStatus,
    variables: List[Dict[str, Any]],
    values: Dict[str, Any],
) -> CNCLiveStatus:
    """
    Applica i valori decodificati allo status secondo il campo 'role' della
    mappa. Valori None (fuori buffer / lettura fallita) NON sovrascrivono i
    default: mai mostrare un numero che non è stato letto davvero.
    """
    for var in variables:
        name = var.get("name")
        role = var.get("role")
        if not name or not role:
            continue
        value = values.get(name)
        status.raw_values[name] = value
        if value is None and role != "machine_state":
            continue

        if role == "machine_state":
            status.machine_state = _decode_state(value, var)
        elif role == "alarm_code":
            status.alarm_code = int(value)
            if status.alarm_code > 0 and not status.alarm_message:
                status.alarm_message = f"Codice allarme PLC {status.alarm_code}"
        elif role == "spindle_speed":
            status.spindle_speed = float(value)
        elif role == "spindle_load":
            status.spindle_load = float(value)
        elif role == "spindle_temperature":
            status.spindle_temperature = float(value)
        elif role == "feed_rate":
            status.feed_rate = float(value)
        elif role == "feed_rate_override":
            status.feed_rate_override = float(value)
        elif role == "axis_x":
            status.position.x = float(value)
        elif role == "axis_y":
            status.position.y = float(value)
        elif role == "axis_z":
            status.position.z = float(value)
        elif role == "tool_number":
            status.tool_number = int(value)
        elif role == "tool_load":
            status.tool_load = float(value)
        elif role == "current_line":
            status.current_line = int(value)
    return status


def build_live_status(
    blocks: List[Any],
    buffers: Dict[int, Optional[bytes]],
    *,
    plc_ip: str = "",
    plc_port: int = 102,
    latency_ms: float = 0.0,
    map_placeholder: bool = False,
) -> CNCLiveStatus:
    """Costruisce lo status da blocchi risolti + buffer letti (puro, testabile)."""
    from plc.plc_map_decoder import decode_variables

    status = CNCLiveStatus(
        plc_connected=True,
        plc_ip=plc_ip,
        plc_port=plc_port,
        plc_latency=latency_ms,
        map_placeholder=map_placeholder,
    )
    if map_placeholder:
        status.program_name = "n/d (mappa DB da compilare)"
        return status

    for block in blocks:
        data = buffers.get(block.number)
        if data is None:
            continue
        values = decode_variables(bytes(data), block.variables)
        apply_decoded_values(status, block.variables, values)
    return status


class CNCLiveWorker(QThread):
    """Poll Snap7 read-only del PLC CNC, con riconnessione e diagnostica."""

    status_updated = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)
    diagnostics_updated = pyqtSignal(dict)

    def __init__(self, settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.settings = dict(settings)
        self.running = False
        self._connected = False
        self._retry_count = 0
        self._last_error = ""

    def _emit_connection(self, connected: bool) -> None:
        if connected != self._connected:
            self._connected = connected
            self.connection_changed.emit(connected)

    def run(self):
        self.running = True
        interval_ms = 200
        try:
            # Trasporto S7 condiviso (gestisce anche il bootstrap snap7.dll
            # negli eseguibili PyInstaller). I metodi usati sono generici:
            # connect / is_connected / _read_bytes / disconnect.
            from plc.snap7_multifilo_client import MultifiloPLCClient as S7Client
            from plc.plc_snap7_reader import read_db_chunked
            from plc.plc_map_loader import (
                load_map_document,
                resolve_blocks_for_machine,
            )
            from plc.plc_connection_diagnostics import collect_connection_stats
        except ImportError as e:
            self._last_error = f"Dipendenze live non disponibili: {e}"
            print(f"⚠ CNC live: {self._last_error}")
            self._emit_connection(False)
            return

        ip = str(self.settings.get("ip", "127.0.0.1"))
        port = int(self.settings.get("port", 102))
        rack = int(self.settings.get("rack", 0))
        slot = int(self.settings.get("slot", 1))
        profile = str(self.settings.get("map_profile", "oem_cnc_v1"))

        try:
            doc = load_map_document(profile)
            map_placeholder = bool(doc.get("placeholder"))
            blocks = [
                b
                for b in resolve_blocks_for_machine(profile, "cnc")
                if b.direction != "sw_to_plc"
            ]
            poll = [b.poll_interval_ms for b in blocks if b.poll_interval_ms]
            if poll:
                interval_ms = max(100, min(poll))
        except (OSError, ValueError) as e:
            self._last_error = f"Mappa {profile!r} non caricabile: {e}"
            print(f"⚠ CNC live: {self._last_error}")
            self._emit_connection(False)
            return

        client = S7Client(ip=ip, rack=rack, slot=slot)
        last_diag = 0.0

        while self.running:
            if not client.is_connected():
                self._emit_connection(False)
                if not client.connect():
                    self._retry_count += 1
                    self._last_error = f"Connessione fallita a {ip}:{port}"
                    # Diagnostica anche da disconnessi: il ping dice se il
                    # problema è rete o protocollo S7 (PUT/GET, rack/slot).
                    stats = collect_connection_stats(
                        client, ip,
                        retry_count=self._retry_count,
                        last_error=self._last_error,
                    )
                    self.diagnostics_updated.emit(stats.to_dict())
                    self._sleep_interruptible(RECONNECT_DELAY_S)
                    continue
                self._retry_count = 0
                self._last_error = ""
                self._emit_connection(True)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] CNC live connesso a {ip} (mappa {profile})")

            buffers: Dict[int, Optional[bytes]] = {}
            latency_ms = 0.0
            read_failed = False

            if not map_placeholder:
                t0 = time.perf_counter()
                for block in blocks:
                    data = read_db_chunked(client, block.number, block.size_bytes)
                    buffers[block.number] = data
                    if data is None:
                        read_failed = True
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            if read_failed and not client.is_connected():
                self._last_error = "Lettura DB fallita: connessione persa"
                self._emit_connection(False)
                continue

            status = build_live_status(
                blocks,
                buffers,
                plc_ip=ip,
                plc_port=port,
                latency_ms=latency_ms,
                map_placeholder=map_placeholder,
            )
            self.status_updated.emit(status)

            now = time.monotonic()
            if now - last_diag >= DIAGNOSTICS_EVERY_S:
                last_diag = now
                stats = collect_connection_stats(
                    client, ip,
                    retry_count=self._retry_count,
                    last_error=self._last_error,
                    probe_db=blocks[0].number if (blocks and not map_placeholder) else 1,
                )
                self.diagnostics_updated.emit(stats.to_dict())

            self.msleep(interval_ms)

        try:
            client.disconnect()
        except Exception:
            pass
        self._emit_connection(False)

    def _sleep_interruptible(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while self.running and time.monotonic() < deadline:
            self.msleep(100)

    def stop(self):
        self.running = False
        self.wait(2000)


class CNCLiveUpdater(QObject):
    """
    Stessa interfaccia di CNCSimulatorUpdater, ma verso PLC reale.
    I comandi sono FAIL-CLOSED: nessuna scrittura implementata e in ogni caso
    bloccati da autonomy_policy (pilota read-only).
    """

    status_updated = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)
    diagnostics_updated = pyqtSignal(dict)

    def __init__(self, settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.settings = dict(settings)
        self.worker: Optional[CNCLiveWorker] = None
        self._last_status: Optional[CNCLiveStatus] = None

    def start(self, interval_ms: int = 200):
        if self.worker is not None:
            return
        self.worker = CNCLiveWorker(self.settings, parent=self)
        self.worker.status_updated.connect(self._on_status)
        self.worker.connection_changed.connect(self.connection_changed.emit)
        self.worker.diagnostics_updated.connect(self.diagnostics_updated.emit)
        self.worker.start()
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] CNC LIVE avviato "
            f"({self.settings.get('ip')}:{self.settings.get('port')} "
            f"mappa {self.settings.get('map_profile')})"
        )

    def _on_status(self, status):
        self._last_status = status
        self.status_updated.emit(status)

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.worker = None

    def _deny_command(self, name: str) -> bool:
        reason = "scrittura PLC non implementata (pilota read-only)"
        try:
            from core.autonomy_policy import Action, ActionContext, get_policy

            result = get_policy().allow(
                Action.PLC_WRITE,
                ActionContext(
                    machine_id="cnc",
                    plc_mode="live",
                    plc_ip=str(self.settings.get("ip", "")),
                ),
            )
            if not result.allowed:
                reason = result.reason
        except ImportError:
            pass
        print(f"⛔ CNC live: comando {name} rifiutato — {reason}")
        return False

    def send_start(self) -> bool:
        return self._deny_command("Start")

    def send_stop(self) -> bool:
        return self._deny_command("Stop")

    def send_hold(self) -> bool:
        return self._deny_command("Hold")

    def send_reset(self) -> bool:
        return self._deny_command("Reset")

    def get_current_status(self) -> Optional[CNCLiveStatus]:
        return self._last_status

    def is_connected(self) -> bool:
        return self.worker is not None and self.worker._connected
