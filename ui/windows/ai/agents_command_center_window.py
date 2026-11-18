"""
Agents Command Center — autonomia, agenti, tattiche commerciali, registro azioni.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from agents.runtime import is_runtime_running, start_runtime, stop_runtime
from core.agents_config import (
    AUTONOMY_LEVEL_LABELS,
    COMMERCIAL_TONE_LABELS,
    CommandCenterSettings,
    effective_autonomy_level,
    effective_commercial_tone,
    load_command_center_settings,
    save_command_center_settings,
)
from modules.access_control_db import SECTION_AGENTS_COMMAND_CENTER
from ui.common.section_access import prompt_section_access
from core.autonomy_policy import get_policy, reload_policy
from modules.action_store import (
    list_recent_agent_messages,
    list_recent_audit,
    list_recent_pending,
)


class AgentsCommandCenterWindow(SectionDialog):
    """Centro di comando agenti e policy di autonomia."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agents Command Center")
        self.setMinimumSize(1100, 720)
        self.setModal(False)
        self._settings: CommandCenterSettings = load_command_center_settings()
        self._authorized = False
        self.init_ui()
        self.apply_stylesheet()
        if not self._prompt_access():
            self._authorized = False
        else:
            self._authorized = True
            self.load_into_form()

    def init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._create_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_autonomy_tab(), "System Autonomy")
        self.tabs.addTab(self._build_production_tab(), "Production Agent")
        self.tabs.addTab(self._build_commercial_tab(), "Commercial Tactics")
        self.tabs.addTab(self._build_audit_tab(), "Action Log")
        self.tabs.addTab(self._build_security_tab(), "Access")
        root.addWidget(self.tabs, 1)
        root.addWidget(self._create_footer())

    def _create_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("accHeader")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(6)

        title = QLabel("Agents Command Center")
        title.setObjectName("accTitle")
        layout.addWidget(title)

        restricted = QLabel("Restricted Access")
        restricted.setObjectName("accRestricted")
        font = QFont()
        font.setBold(True)
        font.setUnderline(True)
        restricted.setFont(font)
        layout.addWidget(restricted)

        operators = QLabel("Authorized Operators Only")
        operators.setObjectName("accOperators")
        font2 = QFont()
        font2.setUnderline(True)
        operators.setFont(font2)
        layout.addWidget(operators)

        self.status_banner = QLabel("")
        self.status_banner.setWordWrap(True)
        self.status_banner.setObjectName("accBanner")
        layout.addWidget(self.status_banner)
        return frame

    def _build_autonomy_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        layout = QVBoxLayout(w)

        grp = QGroupBox("Global autonomy level (entire software)")
        form = QFormLayout(grp)
        self.autonomy_level = QComboBox()
        for i in range(5):
            self.autonomy_level.addItem(f"L{i} — {AUTONOMY_LEVEL_LABELS[i]}", i)
        form.addRow("Operating level:", self.autonomy_level)
        self.autonomy_max_label = QLabel("")
        form.addRow("License cap (max):", self.autonomy_max_label)
        self.autonomy_effective_label = QLabel("")
        form.addRow("Effective level:", self.autonomy_effective_label)

        self.chk_office_auto_email = QCheckBox("Office: automatic email sending (L≥2)")
        self.chk_office_auto_stock = QCheckBox("Office: automatic stock updates")
        self.chk_plant_auto_plc = QCheckBox("Production: PLC writes (with Safety)")
        self.chk_plant_sim_only = QCheckBox("Production: simulation / localhost only (L≥3)")
        self.chk_agents_paused = QCheckBox("Kill switch — pause all agents")

        layout.addWidget(grp)
        layout.addWidget(self.chk_office_auto_email)
        layout.addWidget(self.chk_office_auto_stock)
        layout.addWidget(self.chk_plant_auto_plc)
        layout.addWidget(self.chk_plant_sim_only)
        layout.addWidget(self.chk_agents_paused)

        cap_row = QHBoxLayout()
        cap_row.addWidget(QLabel("Raise license cap (max level):"))
        self.autonomy_max_level = QSpinBox()
        self.autonomy_max_level.setRange(0, 4)
        self.autonomy_max_level.setToolTip(
            "Massimo livello selezionabile. L2 = email office automatiche. L3–L4 solo lab."
        )
        self.autonomy_max_level.valueChanged.connect(self._on_max_level_changed)
        cap_row.addWidget(self.autonomy_max_level)
        cap_row.addStretch()
        layout.addLayout(cap_row)

        hint = QLabel(
            "L2 = invio email preventivi automatico (con checkbox sotto). "
            "L3–L4 solo banco/lab. Se L2 è grigio, alza «license cap»."
        )
        hint.setWordWrap(True)
        hint.setObjectName("accHint")
        layout.addWidget(hint)
        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _build_production_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        layout = QVBoxLayout(w)

        grp_agents = QGroupBox("Active agents")
        ag_layout = QVBoxLayout(grp_agents)
        self.chk_office_agent = QCheckBox("Office agent (orders, stock, communications)")
        self.chk_plant_agent = QCheckBox("Production agent (PLC, machines, suggestions)")
        self.chk_memory_agent = QCheckBox("Memory agent (RAG / episodes — optional)")
        ag_layout.addWidget(self.chk_office_agent)
        ag_layout.addWidget(self.chk_plant_agent)
        ag_layout.addWidget(self.chk_memory_agent)

        row = QHBoxLayout()
        row.addWidget(QLabel("Max parallel agents:"))
        self.spin_max_concurrent = QSpinBox()
        self.spin_max_concurrent.setRange(1, 4)
        row.addWidget(self.spin_max_concurrent)
        row.addWidget(QLabel("Max rounds per case:"))
        self.spin_max_rounds = QSpinBox()
        self.spin_max_rounds.setRange(1, 20)
        row.addWidget(self.spin_max_rounds)
        row.addStretch()
        ag_layout.addLayout(row)
        layout.addWidget(grp_agents)

        grp_runtime = QGroupBox("Office ↔ production runtime")
        rt_layout = QHBoxLayout(grp_runtime)
        self.runtime_status_label = QLabel("Runtime: stopped")
        rt_layout.addWidget(self.runtime_status_label)
        rt_layout.addStretch()
        self.btn_runtime_start = QPushButton("Start runtime")
        self.btn_runtime_start.clicked.connect(self._on_runtime_start)
        rt_layout.addWidget(self.btn_runtime_start)
        self.btn_runtime_stop = QPushButton("Stop")
        self.btn_runtime_stop.clicked.connect(self._on_runtime_stop)
        rt_layout.addWidget(self.btn_runtime_stop)
        layout.addWidget(grp_runtime)

        grp_plant = QGroupBox("Production agent scope")
        pl_layout = QVBoxLayout(grp_plant)
        self.chk_watch_multifilo = QCheckBox("Monitor multiwire")
        self.chk_watch_lucidatrice = QCheckBox("Monitor polisher")
        self.chk_watch_cnc = QCheckBox("Monitor CNC")
        pl_layout.addWidget(self.chk_watch_multifilo)
        pl_layout.addWidget(self.chk_watch_lucidatrice)
        pl_layout.addWidget(self.chk_watch_cnc)
        layout.addWidget(grp_plant)

        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _build_commercial_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        layout = QVBoxLayout(w)

        grp = QGroupBox("Commercial tactics (office agent)")
        form = QFormLayout(grp)
        self.commercial_tone = QComboBox()
        for i in range(5):
            self.commercial_tone.addItem(f"T{i} — {COMMERCIAL_TONE_LABELS[i]}", i)
        form.addRow("Aggressiveness profile:", self.commercial_tone)
        self.commercial_max_label = QLabel("")
        form.addRow("Tone cap (max):", self.commercial_max_label)
        self.commercial_effective_label = QLabel("")
        form.addRow("Effective tone:", self.commercial_effective_label)
        self.spin_follow_up = QSpinBox()
        self.spin_follow_up.setRange(1, 30)
        form.addRow("Follow-up (days):", self.spin_follow_up)
        self.chk_upsell = QCheckBox("Enable catalog upsell")
        self.chk_urgency = QCheckBox("Allow urgency phrases in drafts")
        layout.addWidget(grp)
        layout.addWidget(self.chk_upsell)
        layout.addWidget(self.chk_urgency)

        hint = QLabel(
            "The effective tone modifies Gemini prompts (quotations and order confirmation emails)."
        )
        hint.setWordWrap(True)
        hint.setObjectName("accHint")
        layout.addWidget(hint)
        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _build_audit_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("Refresh log")
        btn_refresh.clicked.connect(self.refresh_audit_tables)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Recent approved actions (pending_actions)"))
        self.table_pending = QTableWidget(0, 6)
        self.table_pending.setHorizontalHeaderLabels(
            ["ID", "Date", "Machine", "Action", "Level", "Result"]
        )
        self.table_pending.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table_pending)

        layout.addWidget(QLabel("Policy audit (autonomy_audit)"))
        self.table_audit = QTableWidget(0, 6)
        self.table_audit.setHorizontalHeaderLabels(
            ["ID", "Date", "Action", "Agent", "OK", "Reason"]
        )
        self.table_audit.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table_audit)

        layout.addWidget(QLabel("Agent bus (recent messages)"))
        self.table_bus = QTableWidget(0, 6)
        self.table_bus.setHorizontalHeaderLabels(
            ["ID", "Date", "From", "To", "Type", "Status"]
        )
        self.table_bus.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table_bus)
        return w

    def _build_security_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        grp = QGroupBox("Restricted access")
        form = QFormLayout(grp)
        self.require_pin_above = QSpinBox()
        self.require_pin_above.setRange(0, 4)
        form.addRow("Require PIN for level >", self.require_pin_above)
        layout.addWidget(grp)
        pin_hint = QLabel(
            "Section open passwords are managed in Privacy & Security Center → Access Control."
        )
        pin_hint.setWordWrap(True)
        pin_hint.setObjectName("accHint")
        layout.addWidget(pin_hint)
        audit = QLabel(
            "Save → config.json + policy reload.\n"
            "DB: data/nstonellm.db (pending_actions, autonomy_audit, agent_messages, section_password)."
        )
        audit.setWordWrap(True)
        audit.setObjectName("accHint")
        layout.addWidget(audit)
        layout.addStretch()
        return w

    def _create_footer(self) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 12, 20, 12)
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.clicked.connect(self.load_into_form)
        layout.addWidget(self.btn_reload)
        layout.addStretch()
        self.btn_save = QPushButton("Save and apply policy")
        self.btn_save.setObjectName("accSaveBtn")
        self.btn_save.clicked.connect(self.on_save)
        layout.addWidget(self.btn_save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        return frame

    def _prompt_access(self) -> bool:
        return prompt_section_access(
            self,
            SECTION_AGENTS_COMMAND_CENTER,
            title="Restricted Access",
        )

    def _update_runtime_label(self) -> None:
        if is_runtime_running():
            self.runtime_status_label.setText("Runtime: active (tick every ~8s)")
        else:
            self.runtime_status_label.setText("Runtime: stopped")

    def _on_runtime_start(self) -> None:
        ok, msg = start_runtime(self.parent())
        if ok:
            QMessageBox.information(self, "Runtime", msg)
        else:
            QMessageBox.warning(self, "Runtime", msg)
        self._update_runtime_label()

    def _on_runtime_stop(self) -> None:
        stop_runtime()
        self._update_runtime_label()

    def refresh_audit_tables(self) -> None:
        pending = list_recent_pending(15)
        self.table_pending.setRowCount(len(pending))
        for row, item in enumerate(pending):
            self.table_pending.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
            self.table_pending.setItem(row, 1, QTableWidgetItem(str(item.get("created_at", ""))[:19]))
            self.table_pending.setItem(row, 2, QTableWidgetItem(str(item.get("machine_id", ""))))
            self.table_pending.setItem(row, 3, QTableWidgetItem(str(item.get("action_type", ""))))
            self.table_pending.setItem(row, 4, QTableWidgetItem(str(item.get("policy_level", ""))))
            msg = str(item.get("result_message", ""))[:120]
            self.table_pending.setItem(row, 5, QTableWidgetItem(msg))

        audits = list_recent_audit(20)
        self.table_audit.setRowCount(len(audits))
        for row, item in enumerate(audits):
            self.table_audit.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
            self.table_audit.setItem(row, 1, QTableWidgetItem(str(item.get("ts", ""))[:19]))
            self.table_audit.setItem(row, 2, QTableWidgetItem(str(item.get("action", ""))))
            self.table_audit.setItem(row, 3, QTableWidgetItem(str(item.get("agent", ""))))
            ok_txt = "yes" if item.get("allowed") else "no"
            self.table_audit.setItem(row, 4, QTableWidgetItem(ok_txt))
            self.table_audit.setItem(row, 5, QTableWidgetItem(str(item.get("reason", ""))[:80]))

        bus = list_recent_agent_messages(15)
        self.table_bus.setRowCount(len(bus))
        for row, item in enumerate(bus):
            self.table_bus.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
            self.table_bus.setItem(row, 1, QTableWidgetItem(str(item.get("created_at", ""))[:19]))
            self.table_bus.setItem(row, 2, QTableWidgetItem(str(item.get("from_agent", ""))))
            self.table_bus.setItem(row, 3, QTableWidgetItem(str(item.get("to_agent", ""))))
            self.table_bus.setItem(row, 4, QTableWidgetItem(str(item.get("msg_type", ""))))
            self.table_bus.setItem(row, 5, QTableWidgetItem(str(item.get("status", ""))))

    def load_into_form(self) -> None:
        if not self._authorized:
            return
        self._settings = load_command_center_settings()
        a = self._settings["autonomy"]
        ag = self._settings["agents"]
        c = self._settings["commercial"]

        max_level = a["max_level"]
        self.autonomy_max_level.blockSignals(True)
        self.autonomy_max_level.setValue(max_level)
        self.autonomy_max_level.blockSignals(False)
        self._apply_autonomy_level_cap(max_level)
        self.autonomy_level.setCurrentIndex(min(a["level"], max_level, 4))

        self.autonomy_max_label.setText(f"L{max_level} — {AUTONOMY_LEVEL_LABELS.get(max_level, '')}")
        eff = effective_autonomy_level(a)
        self.autonomy_effective_label.setText(f"L{eff} — {AUTONOMY_LEVEL_LABELS.get(eff, '')}")

        self.chk_office_auto_email.setChecked(a["office_auto_email"])
        self.chk_office_auto_stock.setChecked(a["office_auto_stock"])
        self.chk_plant_auto_plc.setChecked(a["plant_auto_plc_write"])
        self.chk_plant_sim_only.setChecked(a["plant_sim_only"])
        self.chk_agents_paused.setChecked(a["agents_paused"])

        self.chk_office_agent.setChecked(ag["office_enabled"])
        self.chk_plant_agent.setChecked(ag["plant_enabled"])
        self.chk_memory_agent.setChecked(ag["memory_enabled"])
        self.spin_max_concurrent.setValue(ag["max_concurrent"])
        self.spin_max_rounds.setValue(ag["max_rounds_per_case"])
        self.chk_watch_multifilo.setChecked(ag["plant_watch_multifilo"])
        self.chk_watch_lucidatrice.setChecked(ag["plant_watch_lucidatrice"])
        self.chk_watch_cnc.setChecked(ag["plant_watch_cnc"])

        max_tone = c["max_tone"]
        self.commercial_tone.setCurrentIndex(min(c["tone"], 4))
        for i in range(5):
            self.commercial_tone.model().item(i).setEnabled(i <= max_tone)
        self.commercial_max_label.setText(f"T{max_tone} — {COMMERCIAL_TONE_LABELS.get(max_tone, '')}")
        te = effective_commercial_tone(c)
        self.commercial_effective_label.setText(f"T{te} — {COMMERCIAL_TONE_LABELS.get(te, '')}")
        self.spin_follow_up.setValue(c["follow_up_days"])
        self.chk_upsell.setChecked(c["upsell_enabled"])
        self.chk_urgency.setChecked(c["urgency_phrasing"])

        self.require_pin_above.setValue(a["require_pin_above"])

        reload_policy()
        self.status_banner.setText(get_policy().banner_text())
        self._update_runtime_label()
        self.refresh_audit_tables()

    def _apply_autonomy_level_cap(self, max_level: int) -> None:
        for i in range(5):
            self.autonomy_level.model().item(i).setEnabled(i <= max_level)

    def _on_max_level_changed(self, value: int) -> None:
        self._apply_autonomy_level_cap(value)
        if self.autonomy_level.currentData() > value:
            self.autonomy_level.setCurrentIndex(value)

    def _collect_settings(self) -> CommandCenterSettings:
        a = dict(self._settings["autonomy"])
        a["max_level"] = self.autonomy_max_level.value()
        a["level"] = min(int(self.autonomy_level.currentData()), a["max_level"])
        a["office_auto_email"] = self.chk_office_auto_email.isChecked()
        a["office_auto_stock"] = self.chk_office_auto_stock.isChecked()
        a["plant_auto_plc_write"] = self.chk_plant_auto_plc.isChecked()
        a["plant_sim_only"] = self.chk_plant_sim_only.isChecked()
        a["agents_paused"] = self.chk_agents_paused.isChecked()
        a["require_pin_above"] = self.require_pin_above.value()

        ag = dict(self._settings["agents"])
        ag["office_enabled"] = self.chk_office_agent.isChecked()
        ag["plant_enabled"] = self.chk_plant_agent.isChecked()
        ag["memory_enabled"] = self.chk_memory_agent.isChecked()
        ag["max_concurrent"] = self.spin_max_concurrent.value()
        ag["max_rounds_per_case"] = self.spin_max_rounds.value()
        ag["plant_watch_multifilo"] = self.chk_watch_multifilo.isChecked()
        ag["plant_watch_lucidatrice"] = self.chk_watch_lucidatrice.isChecked()
        ag["plant_watch_cnc"] = self.chk_watch_cnc.isChecked()
        enabled = []
        if ag["office_enabled"]:
            enabled.append("office")
        if ag["plant_enabled"]:
            enabled.append("plant")
        if ag["memory_enabled"]:
            enabled.append("memory")
        ag["enabled"] = enabled

        c = dict(self._settings["commercial"])
        c["tone"] = self.commercial_tone.currentData()
        c["follow_up_days"] = self.spin_follow_up.value()
        c["upsell_enabled"] = self.chk_upsell.isChecked()
        c["urgency_phrasing"] = self.chk_urgency.isChecked()

        return {"autonomy": a, "agents": ag, "commercial": c}

    def on_save(self) -> None:
        if not self._authorized:
            QMessageBox.warning(self, "Access", "Unauthorized session.")
            return
        try:
            save_command_center_settings(self._collect_settings())
            self._settings = load_command_center_settings()
            reload_policy()
            self.load_into_form()
            if hasattr(self.parent(), "update_policy_banner"):
                self.parent().update_policy_banner()
            QMessageBox.information(
                self,
                "Policy applied",
                "Configuration saved to config.json.\n"
                f"{get_policy().banner_text()}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed:\n{e}")

    def on_section_shown(self) -> None:
        if self._authorized:
            self.load_into_form()
        elif hasattr(self, "tabs"):
            self.tabs.setEnabled(False)
            if hasattr(self, "btn_save"):
                self.btn_save.setEnabled(False)

    def closeEvent(self, event) -> None:
        if is_runtime_running():
            stop_runtime()
        super().closeEvent(event)

    def apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QDialog { background-color: #0f0f1a; color: #e8e8f0; }
            #accHeader { background-color: #1a1028; border-bottom: 2px solid #6a3d9a; }
            #accTitle { font-size: 22px; font-weight: bold; color: #ffffff; }
            #accRestricted, #accOperators { font-size: 13px; color: #ffcccc; }
            #accBanner {
                background-color: #2a1a3a; border: 1px solid #6a3d9a;
                border-radius: 6px; padding: 8px; color: #d4b8ff;
            }
            #accHint { color: #9999aa; font-size: 11px; }
            QTabWidget::pane { border: 1px solid #2a2a3a; background: #12121c; }
            QTabBar::tab {
                background: #1a1a2a; color: #aaa; padding: 10px 16px;
                border: 1px solid #2a2a3a;
            }
            QTabBar::tab:selected { background: #2a1a3a; color: #fff; }
            QGroupBox {
                font-weight: bold; border: 1px solid #3a3a4a;
                border-radius: 8px; margin-top: 12px; padding-top: 12px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QCheckBox, QLabel { color: #e0e0e8; }
            QComboBox, QSpinBox, QLineEdit {
                background: #1a1a2a; color: #fff; border: 1px solid #3a3a4a;
                padding: 6px; border-radius: 4px;
            }
            QTableWidget {
                background: #12121c; color: #e8e8f0; gridline-color: #3a3a4a;
            }
            QHeaderView::section {
                background: #1a1a2a; color: #ccc; padding: 6px; border: 1px solid #3a3a4a;
            }
            QPushButton {
                background: #1a1a2a; color: #fff; border: 1px solid #3a3a4a;
                padding: 8px 16px; border-radius: 6px;
            }
            QPushButton:hover { background: #2a2a3a; }
            #accSaveBtn { background: #4a2a6a; border: 1px solid #8a5aaa; font-weight: bold; }
            #accSaveBtn:hover { background: #5a3a7a; }
        """)
