"""
AI Governance & Compliance Center — L. 132/2025, GDPR, AI Act.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionMainWindow

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.agents_config import AUTONOMY_LEVEL_LABELS, load_command_center_settings
from core.autonomy_policy import get_policy, reload_policy
from modules.ai_compliance_catalog import REQUIREMENT_BY_ID
from modules.ai_compliance_service import (
    compute_posture,
    ensure_default_profile_version,
    export_compliance_pack,
    render_worker_notice,
    sync_auto_checklist_from_posture,
)
from modules.compliance_pdf_export import export_compliance_pdf_for_consultant
from modules.app_users_db import get_current_user, load_app_users
from modules.compliance_registry_db import (
    insert_worker_acknowledgment,
    list_worker_acknowledgments,
    load_compliance_profile,
    publish_worker_notice,
    save_compliance_profile,
    update_checklist_item,
    _now_iso,
)

_BTN_STYLE = """
    QPushButton {
        background-color: #2a4a6a;
        color: #FFFFFF;
        border: 2px solid #3a5a7a;
        border-radius: 8px;
        font-size: 13px;
        font-weight: bold;
        padding: 8px 16px;
    }
    QPushButton:hover { background-color: #3a5a7a; }
    QPushButton:pressed { background-color: #1a3a5a; }
"""

_STATUS_COLORS = {
    "good": "#51CF66",
    "elevated": "#FFD93D",
    "lab_only": "#FF922B",
    "action_required": "#FF6B6B",
}


class AiGovernanceComplianceWindow(SectionMainWindow):
    """Centro governance AI e compliance normativa."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Governance & Compliance")
        ensure_default_profile_version()
        self.setup_window_size()
        self.init_ui()
        self.apply_stylesheet()
        self.refresh_all()

    def setup_window_size(self) -> None:
        from ui.common.window_helpers import default_window_geometry, ensure_resizable_window

        ensure_resizable_window(self, min_width=1100, min_height=760)
        default_window_geometry(self)

    def init_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._create_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Posture & Overview")
        self.tabs.addTab(self._build_register_tab(), "Employer Register")
        self.tabs.addTab(self._build_worker_tab(), "Worker Information")
        self.tabs.addTab(self._build_checklist_tab(), "Requirements Checklist")
        self.tabs.addTab(self._build_safeguards_tab(), "Technical Safeguards")
        self.tabs.addTab(self._build_export_tab(), "Evidence Export")
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self._create_footer())
        self.setCentralWidget(container)

    def _create_header(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background-color: #1a2436; border-bottom: 1px solid #3a4a5a; }
        """)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(20, 14, 20, 14)
        outer.setSpacing(6)

        row = QHBoxLayout()
        title = QLabel("AI Governance & Compliance Center")
        title.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        row.addWidget(title)
        row.addStretch()
        self.datetime_label = QLabel()
        self.datetime_label.setStyleSheet("color: #AAAAAA; font-size: 11px;")
        row.addWidget(self.datetime_label)
        btn = QPushButton("Dashboard")
        btn.setStyleSheet(_BTN_STYLE)
        btn.clicked.connect(self.go_back_to_dashboard)
        row.addWidget(btn)
        outer.addLayout(row)

        sub = QLabel(
            "L. 132/2025 · D.Lgs. 152/1997 art. 1-bis · GDPR · EU AI Act — "
            "operational compliance toolkit (not legal advice)"
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #8ab4d4; font-size: 12px;")
        outer.addWidget(sub)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_datetime)
        self.manage_section_timer(self._timer, 1000)
        self._update_datetime()
        return frame

    def _create_footer(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(44)
        frame.setStyleSheet("QFrame { background-color: #12121c; border-top: 1px solid #2a2a3a; }")
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 0, 16, 0)
        disclaimer = QLabel(
            "Generated records support GDPR / L. 132/2025 workplace transparency. "
            "Validate with your DPO or legal counsel before production deployment."
        )
        disclaimer.setStyleSheet("color: #666; font-size: 11px;")
        row.addWidget(disclaimer)
        return frame

    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        top = QHBoxLayout()
        self.posture_banner = QLabel("")
        self.posture_banner.setWordWrap(True)
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        self.posture_banner.setFont(font)
        top.addWidget(self.posture_banner, 1)

        refresh = QPushButton("Refresh posture")
        refresh.setStyleSheet(_BTN_STYLE)
        refresh.clicked.connect(self.refresh_all)
        sync = QPushButton("Sync auto-checks")
        sync.setStyleSheet(_BTN_STYLE)
        sync.setToolTip("Update checklist from technical probes (autonomy, audit, profile)")
        sync.clicked.connect(self._on_sync_auto)
        top.addWidget(sync)
        top.addWidget(refresh)
        layout.addLayout(top)

        self.posture_details = QLabel("")
        self.posture_details.setWordWrap(True)
        self.posture_details.setStyleSheet("color: #ccc; font-size: 13px;")
        layout.addWidget(self.posture_details)

        grp = QGroupBox("Legal framework mapped in this product")
        g_layout = QVBoxLayout(grp)
        for line in (
            "Italy L. 132/2025 art. 11 — safe, transparent workplace AI; worker information",
            "D.Lgs. 152/1997 art. 1-bis — worker information on monitoring tools",
            "GDPR (EU 2016/679) — arts. 13, 22, 35 (notice, automated decisions, DPIA)",
            "EU AI Act (2024/1689) — transparency, human oversight, logging",
            "NStone governance — autonomy levels L0–L4, license cap, audit trail",
        ):
            lbl = QLabel(f"• {line}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #ddd;")
            g_layout.addWidget(lbl)
        layout.addWidget(grp)
        layout.addStretch()
        return w

    def _build_register_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)

        form_box = QGroupBox("Data controller / employer register (GDPR art. 13)")
        form = QFormLayout(form_box)
        self.f_employer = QLineEdit()
        self.f_vat = QLineEdit()
        self.f_site = QLineEdit()
        self.f_legal_rep = QLineEdit()
        self.f_dpo_name = QLineEdit()
        self.f_dpo_email = QLineEdit()
        self.f_purposes = QTextEdit()
        self.f_purposes.setMaximumHeight(80)
        self.f_legal_basis = QLineEdit()
        self.f_retention = QSpinBox()
        self.f_retention.setRange(30, 3650)
        self.f_retention.setSuffix(" days")
        self.f_llm = QLineEdit()
        self.f_llm.setPlaceholderText("e.g. Ollama local / Google Gemini API — region & DPA")
        self.f_version = QLineEdit()

        form.addRow("Employer / controller:", self.f_employer)
        form.addRow("VAT / fiscal ID:", self.f_vat)
        form.addRow("Workplace site:", self.f_site)
        form.addRow("Legal representative:", self.f_legal_rep)
        form.addRow("DPO / privacy contact:", self.f_dpo_name)
        form.addRow("DPO email:", self.f_dpo_email)
        form.addRow("Processing purposes:", self.f_purposes)
        form.addRow("Legal basis (GDPR):", self.f_legal_basis)
        form.addRow("Retention (indicative):", self.f_retention)
        form.addRow("LLM provider note:", self.f_llm)
        form.addRow("System version:", self.f_version)

        self.dpia_check = QCheckBox("DPIA / impact assessment reviewed for this deployment")
        form.addRow("DPIA:", self.dpia_check)

        layout.addWidget(form_box)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save register")
        save_btn.setStyleSheet(_BTN_STYLE)
        save_btn.clicked.connect(self._save_register)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    def _build_worker_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        row = QHBoxLayout()
        row.addWidget(QLabel("Notice language:"))
        self.notice_lang = QComboBox()
        self.notice_lang.addItem("Italiano", "it")
        self.notice_lang.addItem("English", "en")
        self.notice_lang.currentIndexChanged.connect(self._refresh_worker_notice)
        row.addWidget(self.notice_lang)
        row.addStretch()
        pub = QPushButton("Publish notice (new version timestamp)")
        pub.setStyleSheet(_BTN_STYLE)
        pub.clicked.connect(self._publish_notice)
        row.addWidget(pub)
        layout.addLayout(row)

        self.notice_view = QTextEdit()
        self.notice_view.setReadOnly(True)
        layout.addWidget(self.notice_view, 2)

        ack_grp = QGroupBox("Worker acknowledgment (L. 132/2025 / art. 1-bis D.Lgs. 152/1997)")
        ack_form = QFormLayout(ack_grp)
        self.ack_name = QLineEdit()
        self.ack_role = QLineEdit()
        self.ack_notes = QLineEdit()
        ack_form.addRow("Worker name:", self.ack_name)
        ack_form.addRow("Role / department:", self.ack_role)
        ack_form.addRow("Notes:", self.ack_notes)
        ack_btn = QPushButton("Record acknowledgment")
        ack_btn.setStyleSheet(_BTN_STYLE)
        ack_btn.clicked.connect(self._record_ack)
        ack_form.addRow("", ack_btn)
        layout.addWidget(ack_grp)

        layout.addWidget(QLabel("Recent acknowledgments"))
        self.ack_table = QTableWidget(0, 5)
        self.ack_table.setHorizontalHeaderLabels(
            ["Date", "Name", "Role", "Notice ver.", "Method"]
        )
        self.ack_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.ack_table, 1)
        return w

    def _build_checklist_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)

        hint = QLabel(
            "Mark organizational evidence (training, contract, DPO review). "
            "Technical probes update via «Sync auto-checks» on Overview."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa;")
        layout.addWidget(hint)

        self.checklist_table = QTableWidget(0, 6)
        self.checklist_table.setHorizontalHeaderLabels(
            ["Domain", "Requirement", "Legal ref", "Status", "Auto probe", "Evidence"]
        )
        self.checklist_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.checklist_table.cellDoubleClicked.connect(self._edit_checklist_row)
        layout.addWidget(self.checklist_table, 1)
        return w

    def _build_safeguards_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)

        self.safeguards_label = QLabel("")
        self.safeguards_label.setWordWrap(True)
        self.safeguards_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.safeguards_label)

        btn_row = QHBoxLayout()
        acc = QPushButton("Open Agents Command Center")
        acc.setStyleSheet(_BTN_STYLE)
        acc.clicked.connect(self._open_command_center)
        priv = QPushButton("Open Privacy & Security Center")
        priv.setStyleSheet(_BTN_STYLE)
        priv.clicked.connect(self._open_privacy)
        btn_row.addWidget(acc)
        btn_row.addWidget(priv)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        return w

    def _build_export_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        info = QLabel(
            "Export evidence for DPO, labor consultant (consulente del lavoro), or audit.\n"
            "PDF: formatted dossier (employer register, worker notice, checklist, acknowledgments).\n"
            "JSON: machine-readable pack + worker notice text files."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #ccc;")
        layout.addWidget(info)

        pdf_btn = QPushButton("Export PDF for labor consultant…")
        pdf_btn.setStyleSheet(_BTN_STYLE)
        pdf_btn.clicked.connect(self._export_pdf)
        layout.addWidget(pdf_btn)

        json_btn = QPushButton("Export JSON compliance pack…")
        json_btn.setStyleSheet(_BTN_STYLE)
        json_btn.clicked.connect(self._export_pack)
        layout.addWidget(json_btn)
        layout.addStretch()
        return w

    def apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #0e1018; color: #e8e8f0; }
            QGroupBox {
                border: 1px solid #3a4a5a; border-radius: 8px;
                margin-top: 12px; padding-top: 12px; font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox {
                background: #1a1a2a; color: #fff; border: 1px solid #3a3a4a;
                padding: 6px; border-radius: 4px;
            }
            QTableWidget {
                background-color: #0a0a1a; border: 1px solid #2a2a3a;
                gridline-color: #2a2a3a;
            }
            QHeaderView::section {
                background-color: #2a2a3a; color: #fff; padding: 8px; border: none;
            }
            QTabWidget::pane { border: 1px solid #3a3a4a; }
            QTabBar::tab {
                background: #1a1a2a; color: #aaa; padding: 10px 16px;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
            }
            QTabBar::tab:selected { background: #2a4a6a; color: #fff; }
        """)

    def _update_datetime(self) -> None:
        self.datetime_label.setText(format_header_datetime())

    def refresh_all(self) -> None:
        self._load_register_form()
        self._refresh_posture()
        self._refresh_worker_notice()
        self._refresh_checklist()
        self._refresh_safeguards()
        self._refresh_ack_table()

    def _load_register_form(self) -> None:
        p = load_compliance_profile()
        self.f_employer.setText(p.get("employer_name") or "")
        self.f_vat.setText(p.get("employer_vat") or "")
        self.f_site.setText(p.get("workplace_site") or "")
        self.f_legal_rep.setText(p.get("legal_rep_name") or "")
        self.f_dpo_name.setText(p.get("dpo_name") or "")
        self.f_dpo_email.setText(p.get("dpo_email") or "")
        self.f_purposes.setPlainText(p.get("processing_purposes") or "")
        self.f_legal_basis.setText(p.get("legal_basis") or "")
        self.f_retention.setValue(int(p.get("retention_days") or 365))
        self.f_llm.setText(p.get("llm_provider_note") or "")
        self.f_version.setText(p.get("ai_system_version") or "1.14")
        self.dpia_check.setChecked(bool(p.get("dpia_completed")))

    def _save_register(self) -> None:
        save_compliance_profile(
            {
                "employer_name": self.f_employer.text().strip(),
                "employer_vat": self.f_vat.text().strip(),
                "workplace_site": self.f_site.text().strip(),
                "legal_rep_name": self.f_legal_rep.text().strip(),
                "dpo_name": self.f_dpo_name.text().strip(),
                "dpo_email": self.f_dpo_email.text().strip(),
                "processing_purposes": self.f_purposes.toPlainText().strip(),
                "legal_basis": self.f_legal_basis.text().strip(),
                "retention_days": self.f_retention.value(),
                "llm_provider_note": self.f_llm.text().strip(),
                "ai_system_version": self.f_version.text().strip() or "1.14",
                "dpia_completed": 1 if self.dpia_check.isChecked() else 0,
                "dpia_reviewed_at": _now_iso() if self.dpia_check.isChecked() else "",
            }
        )
        QMessageBox.information(self, "Saved", "Employer register updated.")
        self.refresh_all()

    def _refresh_posture(self) -> None:
        posture = compute_posture()
        color = _STATUS_COLORS.get(posture["overall"], "#aaa")
        self.posture_banner.setText(
            f"Compliance posture: {posture['score_percent']}% — {posture['overall_label']}"
        )
        self.posture_banner.setStyleSheet(f"color: {color};")
        auto = posture["auto_checks"]
        lines = [
            f"Effective autonomy: L{posture['effective_autonomy_level']} "
            f"({posture['autonomy_label']}) · max_level=L{posture['max_level']}",
            f"Agents paused: {'yes' if posture['agents_paused'] else 'no'}",
            f"Worker notice published: {auto.get('worker_notice_published', {}).get('detail', '')}",
            f"Profile: {auto.get('profile_complete', {}).get('detail', '')}",
            f"Audit trail: {auto.get('audit_available', {}).get('detail', '')}",
        ]
        self.posture_details.setText("\n".join(lines))

    def _refresh_worker_notice(self) -> None:
        lang = self.notice_lang.currentData() or "it"
        self.notice_view.setPlainText(render_worker_notice(language=lang))

    def _publish_notice(self) -> None:
        profile = load_compliance_profile()
        ver = (profile.get("worker_notice_version") or "1.0").strip()
        publish_worker_notice(version=ver)
        QMessageBox.information(
            self,
            "Published",
            "Worker notice publication timestamp recorded.\n"
            "Distribute the text to staff and record acknowledgments below.",
        )
        self.refresh_all()

    def _record_ack(self) -> None:
        name = self.ack_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Enter worker name.")
            return
        profile = load_compliance_profile()
        user = get_current_user()
        uid = user.get("id") if user else None
        try:
            insert_worker_acknowledgment(
                name,
                profile.get("worker_notice_version") or "1.0",
                worker_role=self.ack_role.text().strip(),
                user_id=uid,
                notes=self.ack_notes.text().strip(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self.ack_name.clear()
        self.ack_notes.clear()
        self._refresh_ack_table()
        QMessageBox.information(self, "Recorded", "Worker acknowledgment saved.")

    def _refresh_ack_table(self) -> None:
        rows = list_worker_acknowledgments(50)
        self.ack_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.ack_table.setItem(i, 0, QTableWidgetItem(str(r.get("acknowledged_at", ""))[:19]))
            self.ack_table.setItem(i, 1, QTableWidgetItem(str(r.get("worker_name", ""))))
            self.ack_table.setItem(i, 2, QTableWidgetItem(str(r.get("worker_role", ""))))
            self.ack_table.setItem(i, 3, QTableWidgetItem(str(r.get("notice_version", ""))))
            self.ack_table.setItem(i, 4, QTableWidgetItem(str(r.get("method", ""))))

    def _refresh_checklist(self) -> None:
        posture = compute_posture()
        items = posture["items"]
        self.checklist_table.setRowCount(len(items))
        for i, item in enumerate(items):
            auto_txt = "—"
            if item["auto_ok"] is True:
                auto_txt = "OK"
            elif item["auto_ok"] is False:
                auto_txt = "Review"
            self.checklist_table.setItem(i, 0, QTableWidgetItem(item["domain"]))
            self.checklist_table.setItem(i, 1, QTableWidgetItem(item["title_en"]))
            self.checklist_table.setItem(i, 2, QTableWidgetItem(item["legal_ref"]))
            self.checklist_table.setItem(i, 3, QTableWidgetItem(item["status"]))
            self.checklist_table.setItem(i, 4, QTableWidgetItem(auto_txt))
            self.checklist_table.setItem(
                i, 5, QTableWidgetItem(item["evidence_note"] or item["auto_detail"])
            )
            self.checklist_table.item(i, 0).setData(Qt.UserRole, item["req_id"])

    def _edit_checklist_row(self, row: int, _col: int) -> None:
        req_item = self.checklist_table.item(row, 0)
        if not req_item:
            return
        req_id = req_item.data(Qt.UserRole)
        req = REQUIREMENT_BY_ID.get(req_id)
        if not req:
            return
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Checklist — {req.title_en}")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(req.summary_en))
        status = QComboBox()
        for s in ("open", "partial", "done", "na"):
            status.addItem(s, s)
        cur = self.checklist_table.item(row, 3).text()
        idx = status.findData(cur)
        if idx >= 0:
            status.setCurrentIndex(idx)
        evidence = QLineEdit(self.checklist_table.item(row, 5).text())
        form = QFormLayout()
        form.addRow("Status:", status)
        form.addRow("Evidence note:", evidence)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec_() != QDialog.Accepted:
            return
        user = get_current_user()
        by = (user.get("display_name") or user.get("username") or "operator") if user else "operator"
        update_checklist_item(
            req_id,
            status.currentData(),
            evidence_note=evidence.text(),
            updated_by=by,
        )
        self._refresh_checklist()

    def _refresh_safeguards(self) -> None:
        reload_policy()
        policy = get_policy()
        settings = load_command_center_settings()
        auto = settings["autonomy"]
        level = policy.effective_level()
        lines = [
            "=== NStone technical safeguards (read-only snapshot) ===",
            policy.banner_text(),
            "",
            f"Operating level: L{auto['level']} · License cap: L{auto['max_level']}",
            f"Label: {AUTONOMY_LEVEL_LABELS.get(level, '')}",
            f"office_auto_email: {auto.get('office_auto_email')}",
            f"office_auto_stock: {auto.get('office_auto_stock')}",
            f"plant_auto_plc_write: {auto.get('plant_auto_plc_write')}",
            f"plant_sim_only: {auto.get('plant_sim_only')}",
            f"agents_paused (kill switch): {auto.get('agents_paused')}",
            f"require_pin_above: L>{auto.get('require_pin_above')}",
            "",
            "Maps to L. 132/2025 (human oversight) and AI Act deployer obligations.",
            "Change settings in Agents Command Center (restricted PIN).",
        ]
        self.safeguards_label.setText("\n".join(lines))

    def _on_sync_auto(self) -> None:
        user = get_current_user()
        by = (user.get("display_name") or "system") if user else "system"
        sync_auto_checklist_from_posture(updated_by=by)
        self.refresh_all()
        QMessageBox.information(self, "Synced", "Checklist updated from technical probes.")

    def _export_pack(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select export folder", str(_PROJECT_ROOT / "data")
        )
        if not folder:
            return
        try:
            path = export_compliance_pack(Path(folder))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Compliance pack saved:\n{path}")

    def _export_pdf(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select folder for PDF (consulente del lavoro)",
            str(_PROJECT_ROOT / "data"),
        )
        if not folder:
            return
        try:
            path = export_compliance_pdf_for_consultant(Path(folder))
        except ImportError as exc:
            QMessageBox.warning(
                self,
                "PDF unavailable",
                f"{exc}\n\nInstall: pip install fpdf2",
            )
            return
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QMessageBox.information(
            self,
            "PDF exported",
            f"Dossier per consulente del lavoro salvato:\n{path}",
        )

    def _open_command_center(self) -> None:
        parent = self.parent()
        if parent and hasattr(parent, "on_agents_command_center_clicked"):
            parent.on_agents_command_center_clicked()

    def _open_privacy(self) -> None:
        parent = self.parent()
        if parent and hasattr(parent, "on_privacy_security_center_clicked"):
            parent.on_privacy_security_center_clicked()
