"""
Pannello monitor neural engine (Ollama locale o Gemini cloud).
Aggiornamento on-demand tramite pulsante Refresh (e dopo salvataggio Settings).
Telemetria locale: sparkline + anello VRAM (QPainter, no PyQtGraph).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import deque
from typing import Deque, Optional

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from llm.llm_service import (
    abort_llm_inference,
    load_llm_config,
    probe_gemini_api,
    ui_model_label_from_config,
    unload_ollama_models,
)
from llm.llm_inference_manager import get_inference_manager
from llm.ollama_runtime import get_snapshot, update_cloud_poll, update_poll
from ui.common.neural_telemetry_widgets import TelemetrySparkline, VramRingGauge

_HISTORY_LEN = 48

_STATUS_LABELS = {
    "idle": "Idle",
    "waiting": "Waiting",
    "running": "Running",
}

_STATUS_COLORS = {
    "idle": "#6a6a7a",
    "waiting": "#e6a817",
    "running": "#3ecf6e",
}


class OllamaPollWorker(QThread):
    poll_done = pyqtSignal(bool, list)

    def __init__(self, base_url: str, parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")

    def run(self):
        try:
            req = urllib.request.Request(f"{self.base_url}/api/ps", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("models") or []:
                if isinstance(item, dict) and item.get("name"):
                    models.append(str(item["name"]))
            self.poll_done.emit(True, models)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
            self.poll_done.emit(False, [])


class CloudPollWorker(QThread):
    poll_done = pyqtSignal(bool, str)

    def run(self):
        ok, message = probe_gemini_api()
        self.poll_done.emit(ok, message)


class OllamaMonitorPanel(QWidget):
    """Monitor LLM (locale Ollama o cloud Gemini) — pannello destro main."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._poll_worker = None
        self._last_poll_ok: Optional[bool] = None
        self._last_cloud_message = ""
        self._last_vram_models: list = []
        self._tps_history: Deque[float] = deque(maxlen=_HISTORY_LEN)
        self._jitter_history: Deque[float] = deque(maxlen=_HISTORY_LEN)
        self._warm_pulse = 0.0
        self._init_ui()
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(1200)
        self._telemetry_timer.timeout.connect(self._tick_local_telemetry)
        self._telemetry_timer.start()
        self._refresh_display()

    def refresh_from_config(self) -> None:
        """Dopo salvataggio Settings o cambio provider."""
        self._last_poll_ok = None
        self._last_cloud_message = ""
        self._refresh_display()
        self._on_update_clicked()

    def _on_stop_clicked(self):
        if abort_llm_inference():
            self.hint_label.setText("Stop sent to active inference.")
        else:
            self.hint_label.setText("No active inference to stop.")
        self._refresh_display()

    def _on_unload_clicked(self):
        self.unload_btn.setEnabled(False)
        self.hint_label.setText("Unloading models from VRAM…")
        _unloaded, msg = unload_ollama_models()
        self.unload_btn.setEnabled(True)
        self.hint_label.setText(msg)
        self._on_update_clicked()

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
        self.title_label = QLabel("Neural engine")
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
        self.model_label = QLabel("Model: —")
        self.queue_label = QLabel("Queue: —")
        self.warm_label = QLabel("Warm: —")

        for lbl in (self.status_label, self.model_label, self.queue_label, self.warm_label):
            lbl.setStyleSheet(
                "color: #CCCCCC; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        # Telemetria locale (QPainter)
        self.local_telemetry = QWidget()
        tel_layout = QHBoxLayout(self.local_telemetry)
        tel_layout.setContentsMargins(0, 4, 0, 0)
        tel_layout.setSpacing(10)

        self.vram_gauge = VramRingGauge()
        tel_layout.addWidget(self.vram_gauge, 0, Qt.AlignTop)

        charts_col = QVBoxLayout()
        charts_col.setSpacing(6)
        self.tps_spark = TelemetrySparkline(
            "Tokens/s",
            line_color="#00f2fe",
            fill_top="#00f2fe55",
        )
        self.jitter_spark = TelemetrySparkline(
            "Jitter",
            line_color="#8B5CF6",
            fill_top="#8B5CF655",
        )
        charts_col.addWidget(self.tps_spark)
        charts_col.addWidget(self.jitter_spark)
        tel_layout.addLayout(charts_col, 1)
        layout.addWidget(self.local_telemetry)

        # Fallback cloud (solo testo)
        self.tps_label = QLabel("Tokens/s: —")
        self.jitter_label = QLabel("Latency: —")
        for lbl in (self.tps_label, self.jitter_label):
            lbl.setStyleSheet(
                "color: #CCCCCC; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

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

        self.stop_btn = QPushButton("Stop response")
        self.stop_btn.setStyleSheet(self.update_btn.styleSheet().replace(
            "#2a2a3a", "#4a2a2a"
        ).replace("#3a3a4a", "#5a3a3a"))
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        self.unload_btn = QPushButton("Unload VRAM")
        self.unload_btn.setStyleSheet(self.update_btn.styleSheet())
        self.unload_btn.clicked.connect(self._on_unload_clicked)
        btn_row2.addWidget(self.unload_btn)
        layout.addLayout(btn_row2)

        outer.addWidget(frame)

    def _set_cloud_metrics_visible(self, cloud: bool) -> None:
        self.local_telemetry.setVisible(not cloud)
        self.tps_label.setVisible(cloud)
        self.jitter_label.setVisible(cloud)

    def _current_tps_value(self, snap) -> Optional[float]:
        if snap.status == "running" and snap.live_tokens_per_sec is not None:
            return float(snap.live_tokens_per_sec)
        if snap.tokens_per_sec is not None:
            return float(snap.tokens_per_sec)
        return None

    def _append_telemetry_from_snapshot(self, snap) -> None:
        tps = self._current_tps_value(snap)
        if tps is not None:
            self._tps_history.append(tps)
        if snap.jitter_ms is not None:
            self._jitter_history.append(float(snap.jitter_ms))

    def _update_local_telemetry_widgets(self, snap) -> None:
        offline = self._last_poll_ok is False
        tps = self._current_tps_value(snap)
        if tps is not None:
            tps_display = f"{tps:.1f}"
        elif offline:
            tps_display = "offline"
        else:
            tps_display = "idle"
        self.tps_spark.set_series(list(self._tps_history), tps_display)

        jitter = float(snap.jitter_ms) if snap.jitter_ms is not None else None
        if jitter is not None:
            jitter_display = f"{jitter:.1f} ms"
        elif offline:
            jitter_display = "offline"
        else:
            jitter_display = "idle"
        self.jitter_spark.set_series(list(self._jitter_history), jitter_display)

        loaded = bool(self._last_vram_models) or bool(snap.loaded_in_vram)
        if snap.loaded_in_vram:
            detail = snap.loaded_in_vram[0].split(":")[0][:14]
        elif self._last_vram_models:
            detail = self._last_vram_models[0].split(":")[0][:14]
        elif offline:
            detail = "offline"
        else:
            detail = "idle"
        self.vram_gauge.set_state(loaded, detail, offline=offline)

    def _tick_local_telemetry(self) -> None:
        cfg = load_llm_config()
        if cfg.get("provider", "ollama") == "gemini":
            return
        snap = get_snapshot()
        self._append_telemetry_from_snapshot(snap)
        self.tps_spark.advance_idle()
        self.jitter_spark.advance_idle()
        self.vram_gauge.advance_idle()
        self._update_local_telemetry_widgets(snap)
        self._update_warm_indicator(snap)

    _WARM_COLORS = {
        "off": "#666677",
        "cold": "#6a6a7a",
        "warming": "#e6a817",
        "ready": "#00f2fe",
        "skipped": "#666677",
        "failed": "#e74c3c",
    }

    _WARM_LABELS = {
        "off": "Off",
        "cold": "Cold",
        "warming": "Warming…",
        "ready": "Ready",
        "skipped": "Skipped",
        "failed": "Failed",
    }

    def _update_warm_indicator(self, snap) -> None:
        cfg = load_llm_config()
        if cfg.get("provider", "ollama") == "gemini":
            self.warm_label.setText("Warm: n/a (cloud)")
            self.warm_label.setStyleSheet(
                "color: #888899; font-size: 11px; background: transparent;"
            )
            return

        state = getattr(snap, "warm_state", "cold") or "cold"
        detail = (getattr(snap, "warm_detail", "") or "").strip()
        label = self._WARM_LABELS.get(state, state.title())
        color = self._WARM_COLORS.get(state, "#6a6a7a")

        if state == "warming":
            import math

            self._warm_pulse += 0.14
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._warm_pulse))
            r = int(230 * pulse)
            g = int(168 * pulse)
            color = f"rgb({r},{g},23)"

        text = f"Warm: {label}"
        if detail and state in ("off", "ready", "failed", "cold"):
            short = detail if len(detail) <= 42 else detail[:39] + "…"
            text = f"{text} · {short}"

        self.warm_label.setText(text)
        self.warm_label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: bold; background: transparent;"
        )

    def _ollama_base_url(self) -> str:
        cfg = load_llm_config()
        if cfg.get("provider") != "ollama":
            return ""
        ollama = cfg.get("ollama") or {}
        return str(ollama.get("base_url", "http://127.0.0.1:11434")).rstrip("/")

    def _on_update_clicked(self):
        if self._poll_worker is not None and self._poll_worker.isRunning():
            return

        cfg = load_llm_config()
        provider = cfg.get("provider", "ollama")

        if provider == "gemini":
            self.update_btn.setEnabled(False)
            self.hint_label.setText("Checking Gemini API…")
            worker = CloudPollWorker(self)
            self._poll_worker = worker
            worker.poll_done.connect(self._on_cloud_poll_done)
            worker.finished.connect(self._release_poll_worker)
            worker.start()
            return

        base = self._ollama_base_url()
        if not base:
            self.hint_label.setText("Ollama provider not configured.")
            self._refresh_display()
            return

        self.update_btn.setEnabled(False)
        self.hint_label.setText("Reading Ollama status…")

        worker = OllamaPollWorker(base, self)
        self._poll_worker = worker
        worker.poll_done.connect(self._on_poll_done)
        worker.finished.connect(self._release_poll_worker)
        worker.start()

    def _release_poll_worker(self):
        worker = self._poll_worker
        self._poll_worker = None
        if worker is not None:
            worker.deleteLater()

    def _on_cloud_poll_done(self, reachable: bool, message: str):
        self.update_btn.setEnabled(True)
        self._last_poll_ok = reachable
        self._last_cloud_message = message
        gemini_model = (load_llm_config().get("gemini") or {}).get("model", "")
        update_cloud_poll(reachable=reachable, model=str(gemini_model))
        if reachable:
            self.hint_label.setText(f"Gemini API · {message}")
        else:
            self.hint_label.setText(f"Gemini API · {message}")
        self._refresh_display()

    def _on_poll_done(self, reachable: bool, models: list):
        self.update_btn.setEnabled(True)
        self._last_poll_ok = reachable
        self._last_vram_models = list(models or [])
        update_poll(reachable=reachable, loaded_models=models)
        if reachable and models:
            from llm.ollama_runtime import set_warm_state

            set_warm_state("ready", "model loaded")
        if reachable:
            loaded = ", ".join(models[:2]) if models else "no model loaded in VRAM"
            if len(models) > 2:
                loaded += "…"
            self.hint_label.setText(f"Ollama reachable · VRAM: {loaded}")
        else:
            self.hint_label.setText("Ollama unreachable at 127.0.0.1:11434")
        self._refresh_display()

    def _refresh_display(self):
        snap = get_snapshot()
        cfg = load_llm_config()
        provider = cfg.get("provider", "ollama")
        model_label = ui_model_label_from_config(cfg)

        if provider == "gemini":
            self._set_cloud_metrics_visible(True)
            self.title_label.setText("Neural engine · Cloud")
            self.unload_btn.setVisible(False)
            self.stop_btn.setEnabled(False)
            self.stop_btn.setToolTip("Stop applies to local Ollama streaming only.")

            if self._last_poll_ok is False:
                dot_color = "#e74c3c"
                status_text = "Offline"
            elif snap.status == "running":
                dot_color = _STATUS_COLORS["running"]
                status_text = "Running"
            elif self._last_poll_ok is True:
                dot_color = "#8B5CF6"
                status_text = "Online"
            else:
                dot_color = "#6a6a7a"
                status_text = "Unknown"

            self.status_dot.setStyleSheet(
                f"color: {dot_color}; font-size: 14px; background: transparent;"
            )
            self.status_label.setText(f"Status: {status_text} (Gemini)")
            self.model_label.setText(f"Model: {model_label}")

            if snap.tokens_per_sec is not None:
                self.tps_label.setText(f"Tokens/s: ~{snap.tokens_per_sec:.1f} (last response, est.)")
            else:
                self.tps_label.setText("Tokens/s: — (after first cloud reply)")

            if snap.last_latency_ms is not None:
                self.jitter_label.setText(f"Last response: {snap.last_latency_ms:.0f} ms")
            else:
                self.jitter_label.setText("Last response: —")

            self.queue_label.setText("Queue: n/a (cloud API)")
            self._update_warm_indicator(snap)
            if self._poll_worker is None or not self._poll_worker.isRunning():
                if not self.hint_label.text().startswith("Checking"):
                    if self._last_cloud_message:
                        self.hint_label.setText(f"Gemini · {self._last_cloud_message}")
                    else:
                        self.hint_label.setText("Press Refresh data to verify Gemini API.")
            return

        self._set_cloud_metrics_visible(False)
        self.title_label.setText("Neural engine · Local")
        self.unload_btn.setVisible(True)
        self.stop_btn.setEnabled(True)
        self.stop_btn.setToolTip("")

        if self._last_poll_ok is False:
            status_key = "idle"
            status_text = "Offline"
            dot_color = "#e74c3c"
        else:
            status_key = snap.status
            status_text = _STATUS_LABELS.get(status_key, status_key)
            dot_color = _STATUS_COLORS.get(status_key, "#6a6a7a")

        self.status_dot.setStyleSheet(
            f"color: {dot_color}; font-size: 14px; background: transparent;"
        )
        self.status_label.setText(f"Status: {status_text}")

        model_name = snap.model or (cfg.get("ollama") or {}).get("model", "—")
        if model_label.startswith("Qwen"):
            self.model_label.setText(f"Model: {model_label}")
        else:
            self.model_label.setText(f"Model: {model_name}")

        q = get_inference_manager().queue_stats()
        inf = (cfg.get("inference") or {})
        max_q = inf.get("max_queue", q.get("max_queue", 3))
        self.queue_label.setText(
            f"Queue: {q['active']} active · {q['waiting']} waiting (max {max_q})"
        )

        self._append_telemetry_from_snapshot(snap)
        self._update_local_telemetry_widgets(snap)
        self._update_warm_indicator(snap)

        if snap.warm_state == "ready" and not self.hint_label.text().startswith(
            ("Ollama unreachable", "Reading", "Checking", "Stop sent", "Unloading")
        ):
            if self._last_poll_ok is not False:
                self.hint_label.setText("Model warm — first AI reply should be faster.")
