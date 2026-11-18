"""
Pannello host hardware — stessa grafica del Neural engine (QPainter).
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.host_hardware import get_hw_info, get_hw_snapshot
from ui.common.neural_telemetry_widgets import TelemetrySparkline, VramRingGauge

_HISTORY_LEN = 48

_STATUS_LABELS = {
    "idle": "Idle",
    "online": "Online",
    "load": "High load",
    "hot": "Thermal alert",
    "offline": "Offline",
}

_STATUS_COLORS = {
    "idle": "#6a6a7a",
    "online": "#3ecf6e",
    "load": "#e6a817",
    "hot": "#e74c3c",
    "offline": "#e74c3c",
}


class HardwareFetchWorker(QThread):
    """Worker in background: non usare il nome 'finished' (conflitto con QThread)."""

    result_ready = pyqtSignal(dict)
    fetch_error = pyqtSignal(str)

    def run(self):
        try:
            self.result_ready.emit(get_hw_info())
        except Exception as exc:
            self.fetch_error.emit(str(exc))


class HardwarePanel(QWidget):
    """Widget host hardware — layout e telemetria speculari a OllamaMonitorPanel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._last_poll_ok: Optional[bool] = None
        self._last_info: Optional[dict] = None
        self._cpu_history: Deque[float] = deque(maxlen=_HISTORY_LEN)
        self._ram_history: Deque[float] = deque(maxlen=_HISTORY_LEN)
        self._init_ui()
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(1200)
        self._telemetry_timer.timeout.connect(self._tick_telemetry)
        self._telemetry_timer.start()
        self._refresh_display()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel("Host hardware")
        self.title_label.setStyleSheet(
            "color: #FFFFFF; font-size: 12px; font-weight: bold; background: transparent;"
        )
        header.addWidget(self.title_label)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(
            f"color: {_STATUS_COLORS['idle']}; font-size: 14px; background: transparent;"
        )
        header.addStretch()
        header.addWidget(self.status_dot)
        layout.addLayout(header)

        self.status_label = QLabel("Status: —")
        self.cpu_label = QLabel("CPU: —")
        self.gpu_label = QLabel("GPU: —")
        for lbl in (self.status_label, self.cpu_label, self.gpu_label):
            lbl.setStyleSheet(
                "color: #CCCCCC; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        self.local_telemetry = QWidget()
        self.local_telemetry.setAutoFillBackground(False)
        self.local_telemetry.setStyleSheet("background: transparent;")
        tel_layout = QHBoxLayout(self.local_telemetry)
        tel_layout.setContentsMargins(0, 4, 0, 0)
        tel_layout.setSpacing(10)

        self.ram_gauge = VramRingGauge(caption="RAM")
        tel_layout.addWidget(self.ram_gauge, 0, Qt.AlignTop)

        charts_col = QVBoxLayout()
        charts_col.setSpacing(6)
        self.cpu_spark = TelemetrySparkline(
            "CPU load",
            line_color="#00f2fe",
            fill_top="#00f2fe55",
        )
        self.ram_spark = TelemetrySparkline(
            "RAM load",
            line_color="#8B5CF6",
            fill_top="#8B5CF655",
        )
        charts_col.addWidget(self.cpu_spark)
        charts_col.addWidget(self.ram_spark)
        tel_layout.addLayout(charts_col, 1)
        layout.addWidget(self.local_telemetry)

        self.hint_label = QLabel("Press Refresh data to update status.")
        self.hint_label.setStyleSheet(
            "color: #888899; font-size: 10px; background: transparent;"
        )
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        btn_row = QHBoxLayout()
        self.update_btn = QPushButton("Refresh data")
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 8px;
                font-size: 11px;
                font-weight: bold;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
            }
            QPushButton:pressed {
                background-color: #1a1a2a;
            }
            QPushButton:disabled {
                color: #666677;
            }
        """)
        self.update_btn.clicked.connect(self._on_update_clicked)
        btn_row.addWidget(self.update_btn)
        layout.addLayout(btn_row)

        outer.addWidget(frame)

    @staticmethod
    def _fmt(value, suffix="", nd="n/d"):
        if value is None:
            return nd
        if isinstance(value, float) and value == int(value):
            return f"{int(value)}{suffix}"
        return f"{value}{suffix}"

    def _status_key(self, info: Optional[dict] = None) -> str:
        if self._last_poll_ok is False:
            return "offline"
        info = info or self._last_info
        if info is None:
            return "idle"
        cpu = info.get("cpu") or {}
        ram = info.get("ram") or {}
        cpu_pct = cpu.get("usage_pct")
        ram_pct = ram.get("used_pct")
        cpu_temp = cpu.get("temp_c")
        gpu = info.get("gpu") or {}
        gpu_temp = gpu.get("temp_c") if gpu.get("available") else None
        if (cpu_temp is not None and cpu_temp >= 90) or (gpu_temp is not None and gpu_temp >= 90):
            return "hot"
        if (cpu_pct is not None and cpu_pct >= 80) or (ram_pct is not None and ram_pct >= 85):
            return "load"
        return "online"

    def _append_telemetry_from_snapshot(self, snap: dict) -> None:
        if snap.get("cpu_usage_pct") is not None:
            self._cpu_history.append(float(snap["cpu_usage_pct"]))
        if snap.get("ram_used_pct") is not None:
            self._ram_history.append(float(snap["ram_used_pct"]))

    def _ring_detail(self, snap: dict, offline: bool) -> str:
        used = snap.get("ram_used_gb")
        total = snap.get("ram_total_gb")
        if used is not None and total is not None:
            return f"{used:.1f}/{total:.0f}G"
        if self._last_info:
            ram = self._last_info.get("ram") or {}
            u, t = ram.get("used_gb"), ram.get("total_gb")
            if u is not None and t is not None:
                return f"{u:.1f}/{t:.0f}G"
        return "offline" if offline else "idle"

    def _has_live_metrics(self, snap: dict) -> bool:
        if snap.get("ok") and snap.get("ram_used_pct") is not None:
            return True
        if self._last_info and self._last_poll_ok is not False:
            return (self._last_info.get("ram") or {}).get("used_pct") is not None
        return False

    def _update_telemetry_widgets(self, snap: Optional[dict] = None) -> None:
        offline = self._last_poll_ok is False
        snap = snap or {}

        cpu_pct = snap.get("cpu_usage_pct")
        if cpu_pct is not None:
            cpu_display = f"{cpu_pct:.1f}"
        elif offline:
            cpu_display = "offline"
        else:
            cpu_display = "idle"
        self.cpu_spark.set_series(list(self._cpu_history), cpu_display)

        ram_pct = snap.get("ram_used_pct")
        if ram_pct is None and self._last_info:
            ram_pct = (self._last_info.get("ram") or {}).get("used_pct")
        if ram_pct is not None:
            ram_display = f"{ram_pct:.1f}"
        elif offline:
            ram_display = "offline"
        else:
            ram_display = "idle"
        self.ram_spark.set_series(list(self._ram_history), ram_display)

        loaded = self._has_live_metrics(snap)
        self.ram_gauge.set_state(
            loaded,
            self._ring_detail(snap, offline),
            offline=offline,
        )

    def _tick_telemetry(self) -> None:
        snap = get_hw_snapshot()
        if snap.get("ok"):
            self._append_telemetry_from_snapshot(snap)
        self.cpu_spark.advance_idle()
        self.ram_spark.advance_idle()
        self.ram_gauge.advance_idle()
        self._update_telemetry_widgets(snap)

    def _apply_status_ui(self, info: Optional[dict] = None) -> None:
        info = info or self._last_info
        status_key = self._status_key(info)
        status_text = _STATUS_LABELS.get(status_key, status_key)
        self.title_label.setText("Host hardware · Local")
        self.status_dot.setStyleSheet(
            f"color: {_STATUS_COLORS.get(status_key, _STATUS_COLORS['idle'])}; "
            "font-size: 14px; background: transparent;"
        )
        self.status_label.setText(f"Status: {status_text}")

    def _apply_info(self, info: dict):
        self._last_info = info
        self._last_poll_ok = True
        cpu = info.get("cpu", {})
        gpu = info.get("gpu", {})
        ram = info.get("ram", {})

        freq = self._fmt(cpu.get("freq_mhz"), " MHz")
        usage = self._fmt(cpu.get("usage_pct"), "%")
        temp = self._fmt(cpu.get("temp_c"), " °C")
        self.cpu_label.setText(f"CPU: {freq} · {usage} · {temp}")

        if gpu.get("available"):
            name = gpu.get("name") or "GPU"
            if len(name) > 22:
                name = name[:20] + "…"
            gfreq = self._fmt(gpu.get("freq_mhz"), " MHz")
            gtemp = self._fmt(gpu.get("temp_c"), " °C")
            self.gpu_label.setText(f"GPU: {name} · {gfreq} · {gtemp}")
        else:
            self.gpu_label.setText("GPU: n/d")

        self._apply_status_ui(info)

        notes = info.get("notes") or []
        self.hint_label.setText(notes[0] if notes else "Host metrics updated.")

        used = ram.get("used_gb")
        total = ram.get("total_gb")
        if cpu.get("usage_pct") is not None:
            self._cpu_history.append(float(cpu["usage_pct"]))
        if ram.get("used_pct") is not None:
            self._ram_history.append(float(ram["used_pct"]))

        snap = {
            "cpu_usage_pct": cpu.get("usage_pct"),
            "ram_used_pct": ram.get("used_pct"),
            "ram_used_gb": used,
            "ram_total_gb": total,
            "ok": True,
        }
        self._update_telemetry_widgets(snap)

    def _refresh_display(self) -> None:
        if self._last_info is None:
            self.title_label.setText("Host hardware · Local")
            self.status_label.setText("Status: —")
            self.cpu_label.setText("CPU: —")
            self.gpu_label.setText("GPU: —")
            self._update_telemetry_widgets({})
            return
        self._apply_info(self._last_info)

    def _release_worker(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def _on_update_clicked(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self.update_btn.setEnabled(False)
        self.hint_label.setText("Reading host metrics…")

        worker = HardwareFetchWorker()
        self._worker = worker
        worker.result_ready.connect(self._on_fetch_finished)
        worker.fetch_error.connect(self._on_fetch_error)
        worker.finished.connect(self._release_worker)
        worker.start()

    def _on_fetch_finished(self, info: dict):
        self.update_btn.setEnabled(True)
        self._apply_info(info)

    def _on_fetch_error(self, message: str):
        self.update_btn.setEnabled(True)
        self._last_poll_ok = False
        self.title_label.setText("Host hardware · Local")
        self.status_dot.setStyleSheet(
            f"color: {_STATUS_COLORS['offline']}; font-size: 14px; background: transparent;"
        )
        self.status_label.setText("Status: Offline")
        self.hint_label.setText(f"Error: {message}")
        self._update_telemetry_widgets({})
