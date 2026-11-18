"""
DB live fullscreen — debugger PLC professionale (Monitoring).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.machine_plc_config import MachinePlcSettings, describe_plc_endpoint
from plc.plc_db_write import PlcWriteGuard, PlcWriteJournal, write_variable
from plc.plc_map_decoder import (
    DiffTracker,
    decode_variables,
    format_display_value,
    format_hex_with_interpretation,
)
from plc.plc_map_loader import (
    SIZE_PRESETS,
    ResolvedDbBlock,
    build_machine_debug_banner,
    describe_map_profile,
    find_block_spec,
    iter_full_map_documentation,
    list_all_db_numbers,
    resolve_blocks_for_machine,
    suggested_read_size,
)
from plc.plc_rust_bridge import rust_plc_engine_available
from ui.common.plc_db_live_worker import PlcDbPollWorker, RETRY_OFFLINE_MS, create_plc_client
from ui.common.plc_db_rust_worker import PlcDbRustPollWorker
from ui.common.plc_trend_dialog import PlcTrendDialog

_DIALOG_THEME = """
QDialog, QWidget {
    background-color: #0a0a15;
    color: #e8e8f0;
}
QTabWidget::pane {
    border: 1px solid #3a3a4a;
    background-color: #0a0a15;
}
QTabBar::tab {
    background: #1a1a2a;
    color: #aaa;
    padding: 8px 14px;
    border: 1px solid #3a3a4a;
}
QTabBar::tab:selected {
    background: #2a1a3a;
    color: #fff;
}
QTableWidget {
    background-color: #0a0a1a;
    color: #fff;
    gridline-color: #3a3a4a;
}
QHeaderView::section {
    background-color: #1a1a2a;
    color: #ccc;
    border: 1px solid #3a3a4a;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #1a1a2a;
    color: #fff;
    border: 1px solid #4a4a5a;
    padding: 4px;
}
QPushButton {
    background-color: #2a2a3a;
    color: #fff;
    border: 1px solid #4a4a5a;
    padding: 6px 12px;
    border-radius: 4px;
}
QCheckBox { color: #ddd; }
QTextEdit { background-color: #0a0a1a; color: #e8e8f0; }
"""


class PlcDbLiveDialog(QDialog):
    def __init__(
        self,
        machine_id: str,
        machine_name: str,
        plc_settings: MachinePlcSettings,
        parent=None,
    ):
        super().__init__(parent)
        self._machine_id = machine_id
        self._machine_name = machine_name
        self._settings = dict(plc_settings)
        self._map_profile = self._settings.get("map_profile", "sim_v1")
        self._poll_blocks = resolve_blocks_for_machine(
            self._map_profile, machine_id
        )
        self._known_dbs = list_all_db_numbers(self._map_profile, machine_id)
        self._db1_values: Dict[str, Any] = {}

        self._map_tables: Dict[int, QTableWidget] = {}
        self._diff = DiffTracker()
        self._worker: Optional[Union[PlcDbPollWorker, PlcDbRustPollWorker]] = None
        self._write_client: Any = None
        self._rust_available = rust_plc_engine_available()
        self._engine_mode = "rust" if self._rust_available else "python"
        self._trend_dialog: Optional[PlcTrendDialog] = None
        self._trend_key: Optional[str] = None
        self._write_journal = PlcWriteJournal()
        self._closing = False
        self._offline = False
        self._diff_enabled = True
        self._explore_auto_detect = True
        self._detected_sizes: Dict[int, int] = {}
        self._doc_table_filled = False
        self._worker_started = False

        self.setWindowTitle(f"DB live — {machine_name}")
        self._apply_dialog_theme()
        self.setup_fullscreen_window()
        self._build_ui()

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._start_worker)

    def setup_fullscreen_window(self) -> None:
        from ui.common.window_helpers import apply_machine_section_window

        apply_machine_section_window(self)

    def _apply_dialog_theme(self) -> None:
        self.setStyleSheet(_DIALOG_THEME)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor("#0a0a15"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(6)

        top = QHBoxLayout()
        left = QVBoxLayout()
        title = QLabel(f"DB live — {self._machine_name}")
        title.setStyleSheet("color: #FFF; font-size: 18px; font-weight: bold;")
        left.addWidget(title)
        self._endpoint_label = QLabel()
        self._endpoint_label.setStyleSheet("color: #AAA; font-size: 10px;")
        left.addWidget(self._endpoint_label)
        top.addLayout(left, 1)

        self._profile_box = QLabel()
        self._profile_box.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self._profile_box.setStyleSheet(
            "color: #9cf; font-size: 10px; padding: 8px; "
            "background: #12122a; border: 1px solid #334; border-radius: 4px;"
        )
        top.addWidget(self._profile_box, 1)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(36)
        close_btn.clicked.connect(self._on_close_clicked)
        top.addWidget(close_btn)
        root.addLayout(top)

        self._conn_label = QLabel("Connection: —")
        self._conn_label.setStyleSheet("color: #8a8; font-size: 10px;")
        root.addWidget(self._conn_label)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("DB:"))
        self._db_spin = QSpinBox()
        self._db_spin.setRange(1, 9999)
        self._db_spin.setValue(self._known_dbs[0] if self._known_dbs else 1)
        self._db_spin.valueChanged.connect(self._on_explore_db_changed)
        toolbar.addWidget(self._db_spin)

        self._db_combo = QComboBox()
        for n in self._known_dbs:
            label = f"DB{n} (map)"
            if n == 8:
                label = "DB8 — AI_Features"
            self._db_combo.addItem(label, n)
        self._db_combo.currentIndexChanged.connect(self._on_db_combo)
        toolbar.addWidget(self._db_combo)

        toolbar.addWidget(QLabel("Byte:"))
        self._size_combo = QComboBox()
        self._size_combo.addItem("Auto-detect (PLC)", -2)
        self._size_combo.addItem("Auto (map)", 0)
        for s in SIZE_PRESETS:
            self._size_combo.addItem(str(s), s)
        self._size_combo.addItem("Manual", -1)
        self._size_combo.currentIndexChanged.connect(self._on_size_mode_changed)
        toolbar.addWidget(self._size_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 8192)
        self._size_spin.setValue(256)
        self._size_spin.setEnabled(False)
        toolbar.addWidget(self._size_spin)

        self._detect_label = QLabel("")
        self._detect_label.setStyleSheet("color: #6a8; font-size: 9px;")
        toolbar.addWidget(self._detect_label)

        self._diff_chk = QCheckBox("Diff")
        self._diff_chk.setChecked(True)
        self._diff_chk.toggled.connect(self._on_diff_toggled)
        toolbar.addWidget(self._diff_chk)

        self._pause_chk = QCheckBox("Pause poll")
        self._pause_chk.toggled.connect(self._on_pause_poll)
        toolbar.addWidget(self._pause_chk)

        self._adapt_chk = QCheckBox("Adaptive poll")
        self._adapt_chk.setChecked(True)
        self._adapt_chk.toggled.connect(self._on_adaptive_poll)
        toolbar.addWidget(self._adapt_chk)

        poll_btn = QPushButton("Poll 1×")
        poll_btn.clicked.connect(self._manual_poll)
        toolbar.addWidget(poll_btn)

        self._rust_btn = QPushButton("⚡ Rust engine: OFF")
        self._rust_btn.setCheckable(True)
        self._rust_btn.setToolTip(
            "Enable high-performance Rust engine (native read/decode, parallel decode). "
            "Requires compiled rust_engine."
        )
        self._rust_btn.clicked.connect(self._on_toggle_rust_engine)
        self._update_rust_button_state()
        toolbar.addWidget(self._rust_btn)

        leg = QLabel("Diff: green=stable · yellow=change · red=burst")
        leg.setStyleSheet("color: #666; font-size: 9px;")
        toolbar.addWidget(leg)
        toolbar.addStretch()
        root.addLayout(toolbar)

        self._status_label = QLabel("Starting…")
        self._status_label.setStyleSheet("color: #FD3; font-weight: bold;")
        root.addWidget(self._status_label)

        self._updated_label = QLabel()
        self._updated_label.setStyleSheet("color: #888; font-size: 10px;")
        root.addWidget(self._updated_label)

        self._main_tabs = QTabWidget()

        self._map_tabs = QTabWidget()
        for block in self._poll_blocks:
            table = self._make_table(block)
            self._map_tables[block.number] = table
            wrap = QWidget()
            lay = QVBoxLayout(wrap)
            lay.setContentsMargins(4, 4, 4, 4)
            title_lbl = QLabel(
                f"{block.tab_title()} · {block.size_bytes} B · "
                f"{block.direction} · {len(block.variables)} var"
            )
            title_lbl.setStyleSheet("color: #888; font-size: 10px;")
            lay.addWidget(title_lbl)
            lay.addWidget(table)
            tab_title = block.tab_title()
            if block.number == 8:
                tab_title = "DB8 — AI_Features"
            self._map_tabs.addTab(wrap, tab_title)
        self._main_tabs.addTab(self._map_tabs, "Live (poll)")

        self._explore_table = QTableWidget(0, 5)
        self._explore_table.setHorizontalHeaderLabels(
            ["Offset", "Variable", "Type", "Value", "Unit"]
        )
        self._explore_table.verticalHeader().setVisible(False)
        self._explore_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._explore_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._explore_wrap = QWidget()
        ex_lay = QVBoxLayout(self._explore_wrap)
        self._explore_hint = QLabel()
        self._explore_hint.setStyleSheet("color: #888; font-size: 10px;")
        ex_lay.addWidget(self._explore_hint)
        ex_lay.addWidget(self._explore_table)
        self._main_tabs.addTab(self._explore_wrap, "Explore DB")

        self._hex_view = QTextEdit()
        self._hex_view.setReadOnly(True)
        self._hex_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; color: #0F0; "
            "background: #0a0a1a; border: 1px solid #3a3a4a;"
        )
        self._main_tabs.addTab(self._hex_view, "Hex + decode")

        self._doc_table = QTableWidget(0, 7)
        self._doc_table.setHorizontalHeaderLabels(
            ["DB", "Block", "Offset", "Variable", "Type", "Unit", "Description"]
        )
        self._doc_table.verticalHeader().setVisible(False)
        self._doc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        doc_wrap = QWidget()
        doc_lay = QVBoxLayout(doc_wrap)
        doc_lay.addWidget(
            QLabel("Internal docs — official JSON map (Plant / sim)")
        )
        doc_lay.addWidget(self._doc_table)
        self._doc_tab_index = self._main_tabs.addTab(doc_wrap, "Full map")

        self._write_wrap = self._build_write_panel()
        self._main_tabs.addTab(self._write_wrap, "DB6 write")

        root.addWidget(self._main_tabs, 1)
        self._main_tabs.currentChanged.connect(self._on_main_tab_changed_lazy)
        self._apply_dialog_theme()
        self._on_explore_db_changed(self._db_spin.value())

    def _build_write_panel(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.addWidget(
            QLabel(
                "Controlled write to DB6 (commands). Requires confirmation; "
                "blocked if emergency active on DB1."
            )
        )
        row = QHBoxLayout()
        self._write_name = QComboBox()
        self._write_name.setMinimumWidth(220)
        row.addWidget(QLabel("Variable:"))
        row.addWidget(self._write_name)
        self._write_value = QLineEdit()
        row.addWidget(QLabel("Value:"))
        row.addWidget(self._write_value)
        w_btn = QPushButton("Write…")
        w_btn.clicked.connect(self._on_write_clicked)
        row.addWidget(w_btn)
        undo_btn = QPushButton("Undo last")
        undo_btn.clicked.connect(self._on_undo_write)
        row.addWidget(undo_btn)
        lay.addLayout(row)
        self._write_log = QTextEdit()
        self._write_log.setReadOnly(True)
        self._write_log.setMaximumHeight(120)
        self._write_log.setStyleSheet("font-size: 10px; color: #ccc;")
        lay.addWidget(self._write_log)
        self._refresh_write_combos()
        return wrap

    def _refresh_write_combos(self) -> None:
        self._write_name.clear()
        spec = find_block_spec(self._map_profile, self._machine_id, 6)
        if not spec:
            self._write_name.addItem("(DB6 not in map)", None)
            return
        for var in spec.variables:
            self._write_name.addItem(
                f"{var.get('name')} @ {var.get('offset')}", var
            )

    def _fill_doc_table(self) -> None:
        rows = iter_full_map_documentation(self._map_profile, self._machine_id)
        self._doc_table.setRowCount(len(rows))
        hdr = self._doc_table.horizontalHeader()
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        for i, r in enumerate(rows):
            self._doc_table.setItem(i, 0, self._cell(f"DB{r['db']}", True))
            self._doc_table.setItem(i, 1, self._cell(str(r["db_name"])))
            self._doc_table.setItem(i, 2, self._cell(str(r["offset"]), True))
            self._doc_table.setItem(i, 3, self._cell(str(r["name"])))
            self._doc_table.setItem(i, 4, self._cell(str(r["type"]), True))
            self._doc_table.setItem(i, 5, self._cell(str(r["unit"]), True))
            self._doc_table.setItem(i, 6, self._cell(str(r["description"])))

    def _update_rust_button_state(self) -> None:
        self._rust_btn.blockSignals(True)
        if not self._rust_available:
            self._rust_btn.setEnabled(False)
            self._rust_btn.setText("⚡ Rust N/A")
            self._rust_btn.setToolTip(
                "Rust engine unavailable. Build: cd rust_engine && maturin develop"
            )
            self._rust_btn.blockSignals(False)
            return
        if self._engine_mode == "rust":
            self._rust_btn.setText("⚡ Rust engine: ON")
            self._rust_btn.setStyleSheet(
                "background-color: #1a4a2a; color: #8f8; font-weight: bold;"
            )
            self._rust_btn.setChecked(True)
        else:
            self._rust_btn.setText("⚡ Rust engine: OFF")
            self._rust_btn.setStyleSheet("")
            self._rust_btn.setChecked(False)
        self._rust_btn.blockSignals(False)

    def _on_toggle_rust_engine(self, checked: bool) -> None:
        if not self._rust_available:
            self._rust_btn.setChecked(False)
            QMessageBox.warning(
                self,
                "Rust engine",
                "rust_engine is not installed.\n\n"
                "Build with:\n  cd rust_engine\n  maturin develop --release",
            )
            return
        new_mode = "rust" if checked else "python"
        if new_mode == self._engine_mode:
            return
        self._engine_mode = new_mode
        self._update_rust_button_state()
        if self._closing:
            return
        self._restart_worker()

    def _restart_worker(self) -> None:
        self._stop_worker()
        if not self._closing:
            self._start_worker()

    def _ensure_write_client(self) -> Any:
        if isinstance(self._worker, PlcDbPollWorker) and self._worker._plc_client:
            return self._worker._plc_client
        if self._write_client is not None:
            try:
                if self._write_client.is_connected():
                    return self._write_client
            except Exception:
                pass
        client = create_plc_client(
            self._machine_id,
            self._settings["ip"],
            self._settings["rack"],
            self._settings["slot"],
            2500,
        )
        if client and client.connect():
            self._write_client = client
            return client
        return None

    def _release_write_client(self) -> None:
        if self._write_client is not None:
            try:
                self._write_client.disconnect()
            except Exception:
                pass
            self._write_client = None

    def _make_table(self, block: ResolvedDbBlock) -> QTableWidget:
        rows = block.variables
        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(
            ["Offset", "Variable", "Type", "Value", "Unit"]
        )
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for i, var in enumerate(rows):
            table.setItem(i, 0, self._cell(str(var.get("offset", "")), True))
            table.setItem(i, 1, self._cell(str(var.get("name", ""))))
            table.setItem(i, 2, self._cell(str(var.get("type", "")), True))
            table.setItem(i, 3, self._cell("—", True))
            table.setItem(i, 4, self._cell(str(var.get("unit") or ""), True))
        return table

    @staticmethod
    def _cell(text: str, center: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if center:
            item.setTextAlignment(Qt.AlignCenter)
        return item

    def _explore_size_mode(self) -> tuple[bool, Optional[int]]:
        data = self._size_combo.currentData()
        if data == -2:
            return True, None
        if data == 0:
            return False, None
        if data == -1:
            return False, self._size_spin.value()
        return False, int(data)

    def _explore_size_bytes(self) -> int:
        auto, user = self._explore_size_mode()
        if user is not None and user > 0:
            return user
        db = self._db_spin.value()
        if auto and db in self._detected_sizes:
            return self._detected_sizes[db]
        return suggested_read_size(self._map_profile, self._machine_id, db)

    def _on_size_mode_changed(self) -> None:
        self._size_spin.setEnabled(self._size_combo.currentData() == -1)
        data = self._size_combo.currentData()
        self._explore_auto_detect = data == -2
        if isinstance(data, int) and data > 0:
            self._size_spin.setValue(data)
        self._push_explore_to_worker()

    def _on_db_combo(self, index: int) -> None:
        if index < 0:
            return
        db = self._db_combo.itemData(index)
        if db is not None:
            self._db_spin.blockSignals(True)
            self._db_spin.setValue(int(db))
            self._db_spin.blockSignals(False)
            self._on_explore_db_changed(int(db))

    def _on_explore_db_changed(self, db_num: int) -> None:
        spec = find_block_spec(self._map_profile, self._machine_id, db_num)
        if spec:
            extra = " · modulo AI NStone" if db_num == 8 else ""
            self._explore_hint.setText(
                f"DB{db_num} — {spec.symbolic_name}{extra} · "
                f"{spec.size_bytes} B in mappa · {len(spec.variables)} variabili"
            )
            self._rebuild_explore_table(spec)
        else:
            self._explore_hint.setText(
                f"DB{db_num} — non in mappa; auto-rileva dimensione o usa Hex"
            )
            self._explore_table.setRowCount(0)
        idx = self._main_tabs.indexOf(self._explore_wrap)
        if idx >= 0:
            title = f"Esplora DB{db_num}"
            if db_num == 8:
                title = "Esplora DB8 AI"
            self._main_tabs.setTabText(idx, title)
        self._push_explore_to_worker()

    def _rebuild_explore_table(self, block: ResolvedDbBlock) -> None:
        self._explore_table.setRowCount(len(block.variables))
        for i, var in enumerate(block.variables):
            self._explore_table.setItem(
                i, 0, self._cell(str(var.get("offset", "")), True)
            )
            self._explore_table.setItem(i, 1, self._cell(str(var.get("name", ""))))
            self._explore_table.setItem(
                i, 2, self._cell(str(var.get("type", "")), True)
            )
            self._explore_table.setItem(i, 3, self._cell("—", True))
            self._explore_table.setItem(
                i, 4, self._cell(str(var.get("unit") or ""), True)
            )

    def _push_explore_to_worker(self) -> None:
        if not self._worker or not self._worker.isRunning():
            return
        auto, user = self._explore_size_mode()
        self._worker.update_explore(
            self._db_spin.value(),
            self._explore_size_bytes(),
            auto_detect=auto,
            user_size=user,
        )

    def _on_diff_toggled(self, checked: bool) -> None:
        self._diff_enabled = checked
        if not checked:
            self._diff.reset()

    def _on_pause_poll(self, paused: bool) -> None:
        if self._worker:
            self._worker.set_paused(paused)

    def _on_adaptive_poll(self, enabled: bool) -> None:
        if self._worker:
            self._worker.set_adaptive(enabled)

    def _manual_poll(self) -> None:
        if self._worker:
            self._worker.request_manual_poll()

    def _on_main_tab_changed(self, index: int) -> None:
        if not self._worker:
            return
        widget = self._main_tabs.widget(index)
        live = widget is self._map_tabs or widget is self._explore_wrap
        self._worker.set_paused(self._pause_chk.isChecked() or not live)

    def _fill_table(
        self,
        table: QTableWidget,
        block: ResolvedDbBlock,
        values: Dict[str, Any],
        db_number: int,
    ) -> None:
        for i, var in enumerate(block.variables):
            name = var.get("name")
            item = table.item(i, 3)
            if item is None:
                continue
            vtype = str(var.get("type", "BOOL"))
            raw = values.get(name) if values else None
            display = format_display_value(raw, vtype)
            item.setText(display)
            key = f"{db_number}:{name}"
            if self._diff_enabled:
                item.setBackground(QColor(self._diff.cell_color(key, raw, vtype)))
            if self._trend_dialog and self._trend_key == key and raw is not None:
                self._trend_dialog.add_sample(raw, display)

    def _disconnect_worker_signals(self, worker: Any) -> None:
        for signal, slot in (
            (worker.snapshot_ready, self._on_snapshot),
            (worker.conn_stats_ready, self._on_conn_stats),
            (worker.status_message, self._on_status_message),
            (worker.finished, self._on_worker_finished),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _flush_queued_worker_slots(self) -> None:
        app = QApplication.instance()
        if app:
            app.removePostedEvents(self, QEvent.MetaCall)

    def _on_snapshot(self, payload: object) -> None:
        if self._closing or not isinstance(payload, dict):
            return
        self._offline = False
        self._retry_timer.stop()

        sizes = payload.get("db_sizes")
        if isinstance(sizes, dict):
            self._detected_sizes.update({int(k): int(v) for k, v in sizes.items()})
            src = payload.get("size_sources") or {}
            db = self._db_spin.value()
            if db in self._detected_sizes:
                src_tag = src.get(db, src.get(str(db), "?"))
                self._detect_label.setText(
                    f"DB{db}: {self._detected_sizes[db]} B ({src_tag})"
                )

        blocks = payload.get("blocks") or {}
        if isinstance(blocks, dict):
            db1 = blocks.get(1) or blocks.get("1")
            if isinstance(db1, dict):
                self._db1_values = db1
            for db_num, values in blocks.items():
                table = self._map_tables.get(int(db_num))
                block = next(
                    (b for b in self._poll_blocks if b.number == int(db_num)), None
                )
                if table and block and isinstance(values, dict):
                    self._fill_table(table, block, values, int(db_num))

        explore = payload.get("explore")
        if explore and isinstance(explore, tuple) and len(explore) >= 3:
            db_num, raw, decoded = explore[0], explore[1], explore[2]
            size = explore[3] if len(explore) > 3 else len(raw)
            src = explore[4] if len(explore) > 4 else ""
            self._hex_view.setPlainText(
                format_hex_with_interpretation(raw)
                + f"\n\n— DB{db_num} · {len(raw)} B letti (target {size}, src={src}) —"
            )
            spec = find_block_spec(self._map_profile, self._machine_id, int(db_num))
            if spec and isinstance(decoded, dict):
                self._fill_table(self._explore_table, spec, decoded, int(db_num))

        lat = payload.get("read_latency_ms")
        engine = payload.get("engine", self._engine_mode)
        if lat is not None:
            self._updated_label.setText(
                f"Aggiornamento {datetime.now().strftime('%H:%M:%S')} · "
                f"{engine} · lettura {lat} ms"
            )
        else:
            self._updated_label.setText(
                f"Aggiornamento: {datetime.now().strftime('%H:%M:%S')}"
            )

    def _on_conn_stats(self, stats: object) -> None:
        if self._closing or not isinstance(stats, dict):
            return
        ping = stats.get("ping_ok")
        ping_ms = stats.get("ping_ms")
        ping_s = "OK" if ping else ("FAIL" if ping is False else "—")
        if ping_ms is not None:
            ping_s += f" {ping_ms}ms"
        cpu = stats.get("cpu_state", "—")
        lat = stats.get("read_latency_ms", "—")
        err = stats.get("last_error") or ""
        retry = stats.get("retry_count", 0)
        order = stats.get("plc_order_code") or ""
        snap = "Snap7 OK" if stats.get("snap7_connected") else "Snap7 off"
        self._conn_label.setText(
            f"Connessione: ping {ping_s} · risposta {lat} ms · CPU {cpu} · "
            f"{snap} · retry {retry}"
            + (f" · {order}" if order else "")
            + (f" · {err}" if err else "")
        )

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        table = self.sender()
        if not isinstance(table, QTableWidget) or col != 3:
            return
        name_item = table.item(row, 1)
        if not name_item:
            return
        name = name_item.text()
        db_num = self._db_spin.value()
        for n, t in self._map_tables.items():
            if t is table:
                db_num = n
                break
        block = find_block_spec(self._map_profile, self._machine_id, db_num)
        unit = ""
        if block:
            for v in block.variables:
                if v.get("name") == name:
                    unit = str(v.get("unit") or "")
                    break
        self._trend_key = f"{db_num}:{name}"
        if self._trend_dialog:
            self._trend_dialog.close()
        self._trend_dialog = PlcTrendDialog(name, unit, parent=None)
        self._trend_dialog.show()

    def _on_write_clicked(self) -> None:
        var = self._write_name.currentData()
        if not isinstance(var, dict):
            QMessageBox.warning(self, "Scrittura", "DB6 non disponibile in questa mappa.")
            return
        if PlcWriteGuard.emergency_active(self._db1_values):
            QMessageBox.critical(
                self,
                "Scrittura bloccata",
                "Emergenza attiva su DB1 — scrittura DB6 non consentita.",
            )
            return
        name = str(var.get("name", ""))
        vtype = str(var.get("type", "BOOL"))
        offset = int(var.get("offset", 0))
        raw_val = self._write_value.text().strip()
        if vtype == "BOOL":
            value = raw_val.lower() in ("1", "true", "si", "sì", "yes")
        elif vtype == "REAL":
            value = float(raw_val.replace(",", "."))
        else:
            value = int(raw_val)
        ok_confirm = QMessageBox.question(
            self,
            "Conferma scrittura",
            f"Scrivere {name} (DB6 @{offset}) = {value}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ok_confirm != QMessageBox.Yes:
            return
        client = self._ensure_write_client()
        if not client:
            QMessageBox.warning(self, "Scrittura", "PLC non connesso.")
            return
        ok, msg, old_b, new_b = write_variable(
            client,
            6,
            offset,
            vtype,
            value,
            name=name,
        )
        entry = PlcWriteJournal.make_entry(
            6, offset, vtype, name, old_b, new_b, ok, msg
        )
        self._write_journal.push(entry)
        self._write_log.prepend(
            f"[{entry.timestamp}] {name} → {value} ({msg})\n"
        )
        if ok:
            self._manual_poll()

    def _on_undo_write(self) -> None:
        entry = self._write_journal.pop_undo()
        if not entry:
            QMessageBox.information(self, "Undo", "Nessuna scrittura da annullare.")
            return
        if not self._worker or (
            isinstance(self._worker, PlcDbPollWorker) and not self._worker._plc_client
        ):
            client = self._ensure_write_client()
        else:
            client = (
                self._worker._plc_client
                if isinstance(self._worker, PlcDbPollWorker)
                else self._ensure_write_client()
            )
        if not client:
            return
        ok = client._write_bytes(
            entry.db_number, entry.offset, bytearray(entry.old_bytes)
        )
        self._write_log.prepend(
            f"[undo] {entry.name} ripristinato ({'OK' if ok else 'FAIL'})\n"
        )

    def _set_status(self, text: str, error: bool) -> None:
        self._status_label.setText(text)
        c = "#F66" if error else "#5F6"
        self._status_label.setStyleSheet(f"color: {c}; font-weight: bold;")

    def _on_status_message(self, text: str, error: bool) -> None:
        if self._closing:
            return
        self._set_status(text, error)
        if error and (
            "non raggiungibile" in text.lower() or "non disponibile" in text.lower()
        ):
            self._offline = True

    def _start_worker(self) -> None:
        if self._closing or (self._worker and self._worker.isRunning()):
            return
        auto, user = self._explore_size_mode()
        if self._engine_mode == "rust" and self._rust_available:
            self._worker = PlcDbRustPollWorker(
                self._machine_id,
                self._map_profile,
                self._settings["ip"],
                self._settings["rack"],
                self._settings["slot"],
                self._poll_blocks,
                self._db_spin.value(),
                self._explore_size_bytes(),
                parent=None,
            )
        else:
            self._engine_mode = "python"
            self._update_rust_button_state()
            self._worker = PlcDbPollWorker(
                self._machine_id,
                self._map_profile,
                self._settings["ip"],
                self._settings["rack"],
                self._settings["slot"],
                self._poll_blocks,
                self._db_spin.value(),
                self._explore_size_bytes(),
                explore_auto_detect=auto,
                explore_user_size=user,
                parent=None,
            )
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.conn_stats_ready.connect(self._on_conn_stats)
        self._worker.status_message.connect(self._on_status_message)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.set_paused(self._pause_chk.isChecked())
        self._worker.set_adaptive(self._adapt_chk.isChecked())
        self._on_main_tab_changed(self._main_tabs.currentIndex())
        self._worker.start()

    def _on_worker_finished(self) -> None:
        sender = self.sender()
        if sender is not None and sender is not self._worker:
            return
        self._worker = None
        if self._closing:
            return
        if self._offline:
            self._set_status(f"Riprovo tra {RETRY_OFFLINE_MS // 1000}s…", True)
            self._retry_timer.start(RETRY_OFFLINE_MS)

    def _stop_worker(self) -> None:
        """Arresto thread Snap7 senza lasciare segnali in coda verso UI distrutta."""
        self._retry_timer.stop()
        w = self._worker
        if not w:
            return
        self._disconnect_worker_signals(w)
        w.request_stop()
        if w.isRunning():
            if not w.wait(5000):
                try:
                    w.terminate()
                    w.wait(1000)
                except Exception:
                    pass
        self._flush_queued_worker_slots()
        w.deleteLater()
        self._worker = None

    def _refresh_labels(self) -> None:
        self._endpoint_label.setText(describe_plc_endpoint(self._settings))
        banner = build_machine_debug_banner(
            self._map_profile, self._machine_id, self._settings
        )
        try:
            map_desc = describe_map_profile(self._map_profile)
        except OSError:
            map_desc = self._map_profile
        self._profile_box.setText(
            f"<b>Modello:</b> {banner.get('model', self._machine_name)}<br>"
            f"<b>Costruttore:</b> {banner.get('manufacturer', '—')}<br>"
            f"<b>PLC:</b> {banner.get('plc', 'Siemens S7')}<br>"
            f"<b>Mappa:</b> {self._map_profile} — {map_desc}<br>"
            f"<b>DB:</b> {banner.get('dbs', '—')}<br>"
            f"<b>Endpoint:</b> {banner.get('endpoint', '—')}"
        )

    def _on_close_clicked(self) -> None:
        if self._closing:
            return
        self._shutdown()
        super().accept()

    def _shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._main_tabs.blockSignals(True)
        if self._trend_dialog:
            self._trend_dialog.close()
            self._trend_dialog = None
        self._stop_worker()
        self._release_write_client()
        self._flush_queued_worker_slots()

    def _on_main_tab_changed_lazy(self, index: int) -> None:
        if getattr(self, "_doc_tab_index", -1) == index:
            self._ensure_doc_table()
        self._on_main_tab_changed(index)

    def _ensure_doc_table(self) -> None:
        if self._doc_table_filled:
            return
        self._doc_table_filled = True
        self._fill_doc_table()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._closing and not self._worker_started:
            self._refresh_labels()
            self._update_rust_button_state()
            QTimer.singleShot(0, self._deferred_start_worker)

    def _deferred_start_worker(self) -> None:
        if self._closing or self._worker_started:
            return
        self._worker_started = True
        self._start_worker()

    def hideEvent(self, event) -> None:
        if not self._closing:
            self._stop_worker()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._shutdown()
        event.accept()
        super().closeEvent(event)

    def reject(self) -> None:
        self._shutdown()
        super().reject()

    def accept(self) -> None:
        if not self._closing:
            self._shutdown()
        super().accept()

    def done(self, result: int) -> None:
        if not self._closing:
            self._shutdown()
        super().done(result)
