"""
NStone — Agentic Calling
FreeSWITCH (LAN SIP) + local Ollama voice agents: 1000 / 2000 / 3000
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionDialog
from modules.agentic_calling import (
    EXTENSION_COMMERCIAL,
    EXTENSION_MANAGEMENT,
    EXTENSION_PRODUCTION,
    append_call_log,
    check_ollama_status,
    get_extension,
    load_agentic_calling_config,
    load_call_log,
    probe_freeswitch_cli,
    save_agentic_calling_config,
    sip_dial_uri,
)
from modules.voice_bridge import (
    check_voice_bridge_health,
    start_voice_bridge,
    stop_voice_bridge,
)


class _StatusProbeWorker(QThread):
    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(dict)

    def __init__(self, cfg: Dict) -> None:
        super().__init__()
        self._cfg = cfg

    def run(self) -> None:
        ollama = check_ollama_status()
        fs = probe_freeswitch_cli(self._cfg)
        bridge_ok, bridge_detail = check_voice_bridge_health()
        self.result_ready.emit(
            {
                "ollama_online": ollama.online,
                "ollama_detail": ollama.detail,
                "fs_online": fs.online,
                "fs_detail": fs.detail,
                "bridge_online": bridge_ok,
                "bridge_detail": bridge_detail,
            }
        )


class AgenticCallingWindow(SectionDialog):
    """Voice agent hub — Management / Commercial / Production SIP extensions."""

    _EXT_KEYS = (
        (EXTENSION_MANAGEMENT, "left"),
        (EXTENSION_COMMERCIAL, "center"),
        (EXTENSION_PRODUCTION, "right"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Agentic Calling")
        self.setMinimumSize(1600, 900)
        self.setModal(False)
        self._cfg = load_agentic_calling_config()
        self._status_worker: Optional[_StatusProbeWorker] = None
        self._extension_lists: Dict[str, QListWidget] = {}
        self._stack_labels: Dict[str, QLabel] = {}

        self.init_ui()
        self.apply_stylesheet()
        self.setup_timer()
        self.refresh_call_logs()
        self.refresh_status_async()

    def init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._create_header())
        root.addWidget(self._create_main_section(), 1)
        root.addWidget(self._create_footer())

    def _create_header(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(80)
        frame.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
            """
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 15, 20, 15)

        back = QPushButton("←")
        back.setFixedSize(40, 40)
        back.setStyleSheet(
            """
            QPushButton {
                background-color: #2a2a3a; color: #fff;
                border: 1px solid #3a3a4a; border-radius: 20px;
                font-size: 20px; font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a4a; }
            """
        )
        back.clicked.connect(self.go_back_to_dashboard)
        lay.addWidget(back)

        logo = QLabel("N+")
        logo.setFixedSize(50, 50)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            """
            QLabel {
                background-color: #4a2a6a; color: #fff;
                border: 2px solid #5a3a7a; border-radius: 25px;
                font-size: 18px; font-weight: bold;
            }
            """
        )
        lay.addWidget(logo)

        title = QLabel("Agentic Calling")
        title.setStyleSheet("color: #fff; font-size: 20px; font-weight: bold;")
        lay.addWidget(title)
        lay.addStretch()

        info = QVBoxLayout()
        info.addWidget(
            QLabel("NStone")
        )
        self.datetime_label = QLabel(format_header_datetime())
        info.addWidget(self.datetime_label)
        for i in range(info.count()):
            w = info.itemAt(i).widget()
            if isinstance(w, QLabel):
                w.setStyleSheet("color: #fff; font-size: 10px;")
        lay.addLayout(info)
        return frame

    def _create_main_section(self) -> QWidget:
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(20, 20, 20, 20)
        outer_lay.setSpacing(12)

        title = QLabel("Agentic Calling")
        title.setStyleSheet("color: #fff; font-size: 22px; font-weight: bold;")
        outer_lay.addWidget(title)

        desc = QLabel(
            "LAN voice OS — FreeSWITCH backend · Ollama local brain · "
            "SIP extensions 1000 / 2000 / 3000 (Zoiper, no tunnel, no SIM)"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaa; font-size: 13px;")
        outer_lay.addWidget(desc)

        outer_lay.addWidget(self._create_stack_status_bar())

        columns = QHBoxLayout()
        columns.setSpacing(15)
        columns.addWidget(self._create_extension_column(EXTENSION_MANAGEMENT), 1)
        columns.addWidget(self._create_extension_column(EXTENSION_COMMERCIAL), 1)
        columns.addWidget(self._create_extension_column(EXTENSION_PRODUCTION), 1)
        outer_lay.addLayout(columns, 1)

        pipeline = QGroupBox("Minimal stack (on-prem)")
        pipeline.setStyleSheet(self._group_style())
        pl = QVBoxLayout(pipeline)
        pipeline_text = QLabel(
            "Phone (SIP Wi‑Fi) → FreeSWITCH dialplan → Lua script → "
            "Whisper CLI (STT) → Ollama CLI (LLM) → Piper/Coqui (TTS) → caller\n"
            "Same models and policy as NStone desktop — no external backend, no tunnel."
        )
        pipeline_text.setWordWrap(True)
        pipeline_text.setStyleSheet("color: #ccc; font-size: 12px;")
        pl.addWidget(pipeline_text)
        outer_lay.addWidget(pipeline)
        return outer

    def _create_stack_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            """
            QFrame {
                background-color: #12122a;
                border: 1px solid #3a3a5a;
                border-radius: 8px;
                padding: 8px;
            }
            """
        )
        lay = QHBoxLayout(bar)
        lay.setSpacing(16)

        self.fs_status_label = QLabel("FreeSWITCH: checking…")
        self.ollama_status_label = QLabel("Ollama: checking…")
        self.bridge_status_label = QLabel("Voice Bridge: starting…")
        self.mode_badge = QLabel("MODE: LAN · NO TUNNEL")
        self.mode_badge.setStyleSheet(
            "color: #8f8; font-weight: bold; font-size: 11px;"
        )
        for lbl in (
            self.fs_status_label,
            self.ollama_status_label,
            self.bridge_status_label,
        ):
            lbl.setStyleSheet("color: #ddd; font-size: 12px;")
        lay.addWidget(self.fs_status_label)
        lay.addWidget(self.ollama_status_label)
        lay.addWidget(self.bridge_status_label)
        lay.addWidget(self.mode_badge)
        lay.addStretch()

        lay.addWidget(QLabel("SIP host:"))
        self.sip_host_input = QLineEdit(str(self._cfg.get("sip_server", "127.0.0.1")))
        self.sip_host_input.setFixedWidth(120)
        lay.addWidget(self.sip_host_input)

        lay.addWidget(QLabel("Port:"))
        self.sip_port_spin = QSpinBox()
        self.sip_port_spin.setRange(1, 65535)
        self.sip_port_spin.setValue(int(self._cfg.get("sip_port") or 5060))
        lay.addWidget(self.sip_port_spin)

        save_btn = QPushButton("Save LAN")
        save_btn.clicked.connect(self._save_lan_settings)
        lay.addWidget(save_btn)

        refresh_btn = QPushButton("Refresh status")
        refresh_btn.clicked.connect(self.refresh_status_async)
        lay.addWidget(refresh_btn)
        return bar

    def _create_extension_column(self, ext_key: str) -> QGroupBox:
        ext = get_extension(self._cfg, ext_key)
        number = ext.get("number", "?")
        label = ext.get("label", ext_key.title())
        box = QGroupBox(label)
        box.setStyleSheet(self._group_style())
        lay = QVBoxLayout(box)
        lay.setSpacing(10)

        ext_title = QLabel(f"SIP extension {number}")
        ext_title.setStyleSheet("color: #9cf; font-size: 16px; font-weight: bold;")
        lay.addWidget(ext_title)

        uri = sip_dial_uri(self._cfg, str(number))
        uri_lbl = QLabel(f"Dial: {uri}")
        uri_lbl.setWordWrap(True)
        uri_lbl.setStyleSheet("color: #aaa; font-size: 11px; font-family: Consolas;")
        lay.addWidget(uri_lbl)

        role = QLabel(str(ext.get("role", "")))
        role.setWordWrap(True)
        role.setStyleSheet("color: #ccc; font-size: 12px;")
        lay.addWidget(role)

        modules = ext.get("nstone_modules") or []
        if isinstance(modules, list):
            mod_lbl = QLabel("NStone: " + " · ".join(str(m) for m in modules))
            mod_lbl.setWordWrap(True)
            mod_lbl.setStyleSheet("color: #8a8; font-size: 11px;")
            lay.addWidget(mod_lbl)

        stack_lbl = QLabel("Stack: SIP → Whisper → Ollama → TTS")
        stack_lbl.setStyleSheet("color: #666; font-size: 10px;")
        self._stack_labels[ext_key] = stack_lbl
        lay.addWidget(stack_lbl)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy SIP URI")
        copy_btn.clicked.connect(lambda _=False, u=uri: self._copy_text(u))
        btn_row.addWidget(copy_btn)

        test_btn = QPushButton("Log test call")
        test_btn.clicked.connect(
            lambda _=False, k=ext_key, n=number: self._log_test_call(k, n)
        )
        btn_row.addWidget(test_btn)
        lay.addLayout(btn_row)

        lay.addWidget(QLabel("Recent voice activity"))
        call_list = QListWidget()
        call_list.setStyleSheet(
            """
            QListWidget {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                color: #eee; font-size: 11px;
            }
            """
        )
        self._extension_lists[ext_key] = call_list
        lay.addWidget(call_list, 1)

        if ext_key == EXTENSION_MANAGEMENT:
            note = QTextEdit()
            note.setReadOnly(True)
            note.setMaximumHeight(72)
            note.setPlainText(
                "Management agent: autonomy policy, user banner, system overview."
            )
            lay.addWidget(note)
        return box

    def _create_footer(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(40)
        frame.setStyleSheet(
            "QFrame { background-color: #0a0a15; border-top: 1px solid #2a1a3a; }"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 0, 20, 0)
        footer = QLabel("NStone")
        footer.setStyleSheet("color: #888; font-size: 10px;")
        lay.addWidget(footer)
        lay.addStretch()
        return frame

    @staticmethod
    def _group_style() -> str:
        return """
            QGroupBox {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                margin-top: 12px;
                padding: 14px;
                font-size: 15px;
                font-weight: bold;
                color: #e8e8e8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
            }
            QPushButton {
                background-color: #2a2a3a;
                color: #fff;
                border: 1px solid #4a4a5a;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3a3a4a; }
            QLineEdit, QSpinBox {
                background-color: #1a1a2a;
                color: #fff;
                border: 1px solid #4a4a5a;
                padding: 4px;
            }
        """

    def setup_timer(self) -> None:
        self.datetime_timer = QTimer(self)
        self.datetime_timer.timeout.connect(self._update_datetime)
        self.manage_section_timer(self.datetime_timer, 1000)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status_async)
        self.manage_section_timer(self.status_timer, 15000)

    def on_section_shown(self) -> None:
        self._cfg = load_agentic_calling_config()
        self._start_voice_bridge()
        self.refresh_call_logs()
        self.refresh_status_async()

    def on_section_hidden(self) -> None:
        # Voice Bridge resta attivo (avviato con NStone) anche tornando al dashboard.
        pass

    def closeEvent(self, event) -> None:
        stop_voice_bridge()
        super().closeEvent(event)

    def _start_voice_bridge(self) -> None:
        result = start_voice_bridge()
        host = result.host
        port = result.port
        if result.started:
            self.bridge_status_label.setText(
                f"Voice Bridge: ONLINE — {host}:{port}"
            )
            self.bridge_status_label.setStyleSheet("color: #8f8; font-size: 12px;")
        else:
            self.bridge_status_label.setText(
                f"Voice Bridge: OFFLINE — {result.message}"
            )
            self.bridge_status_label.setStyleSheet("color: #f88; font-size: 12px;")

    def _update_datetime(self) -> None:
        self.datetime_label.setText(format_header_datetime())

    def _save_lan_settings(self) -> None:
        self._cfg["sip_server"] = self.sip_host_input.text().strip() or "127.0.0.1"
        self._cfg["sip_port"] = int(self.sip_port_spin.value())
        save_agentic_calling_config(self._cfg)
        QMessageBox.information(
            self,
            "Agentic Calling",
            "LAN SIP settings saved to config.json.",
        )
        self.refresh_status_async()

    def refresh_status_async(self) -> None:
        if self._status_worker is not None and self._status_worker.isRunning():
            return
        self._cfg = load_agentic_calling_config()
        self._status_worker = _StatusProbeWorker(dict(self._cfg))
        self._status_worker.result_ready.connect(self._apply_status)
        self._status_worker.start()

    def _apply_status(self, data: dict) -> None:
        fs_ok = data.get("fs_online")
        ol_ok = data.get("ollama_online")
        br_ok = data.get("bridge_online")
        fs_color = "#8f8" if fs_ok else "#f88"
        ol_color = "#8f8" if ol_ok else "#f88"
        br_color = "#8f8" if br_ok else "#f88"
        self.fs_status_label.setText(
            f"FreeSWITCH: <span style='color:{fs_color}'>"
            f"{'ONLINE' if fs_ok else 'OFFLINE'}</span> — {data.get('fs_detail', '')}"
        )
        self.ollama_status_label.setText(
            f"Ollama: <span style='color:{ol_color}'>"
            f"{'ONLINE' if ol_ok else 'OFFLINE'}</span> — {data.get('ollama_detail', '')}"
        )
        self.bridge_status_label.setText(
            f"Voice Bridge: <span style='color:{br_color}'>"
            f"{'ONLINE' if br_ok else 'OFFLINE'}</span> — {data.get('bridge_detail', '')}"
        )
        self.fs_status_label.setTextFormat(Qt.RichText)
        self.ollama_status_label.setTextFormat(Qt.RichText)
        self.bridge_status_label.setTextFormat(Qt.RichText)

    def refresh_call_logs(self) -> None:
        rows = load_call_log(limit=80)
        by_ext: Dict[str, List[str]] = {k: [] for k, _ in self._EXT_KEYS}
        for row in rows:
            key = row.get("extension_key") or EXTENSION_MANAGEMENT
            line = (
                f"{row.get('timestamp', '')} · ext {row.get('number', '?')} · "
                f"{row.get('summary', 'call')}"
            )
            if key in by_ext:
                by_ext[key].append(line)
        for ext_key, _ in self._EXT_KEYS:
            widget = self._extension_lists.get(ext_key)
            if widget is None:
                continue
            widget.clear()
            items = by_ext.get(ext_key) or []
            if not items:
                widget.addItem("No calls logged yet — dial from Zoiper on LAN")
            else:
                for item in reversed(items[-12:]):
                    widget.addItem(item)

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Copied", f"SIP URI copied:\n{text}")

    def _log_test_call(self, ext_key: str, number: str) -> None:
        append_call_log(
            {
                "extension_key": ext_key,
                "number": number,
                "summary": "Manual test entry from NStone UI",
            }
        )
        self.refresh_call_logs()

    def apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #0a0a15; color: #e8e8f0; }
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                color: #ccc;
                font-size: 11px;
            }
            """
        )
