"""
Nstone LLM - Privacy & Security Center (Access Control + Users)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionMainWindow

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.access_control_db import (
    SECTION_ADMINISTRATOR_BYPASS,
    is_access_control_editable,
    load_section_password_records,
    update_section_access,
)
from modules.app_users_db import (
    ROLE_ADMINISTRATOR,
    ROLE_OPERATOR,
    delete_app_user,
    get_current_user,
    insert_app_user,
    is_app_users_editable,
    load_app_users,
    set_current_user,
    update_app_user,
)

_BTN_STYLE = """
    QPushButton {
        background-color: #4a2a6a;
        color: #FFFFFF;
        border: 2px solid #5a3a7a;
        border-radius: 8px;
        font-size: 13px;
        font-weight: bold;
        padding: 8px 16px;
    }
    QPushButton:hover { background-color: #5a3a7a; }
    QPushButton:pressed { background-color: #3a1a5a; }
    QPushButton:disabled {
        background-color: #2a2a3a;
        color: #666666;
        border-color: #3a3a4a;
    }
"""

_TABLE_STYLE = """
    QTableWidget {
        background-color: #0a0a1a;
        border: 1px solid #2a2a3a;
        border-radius: 8px;
        color: #FFFFFF;
        gridline-color: #2a2a3a;
    }
    QTableWidget::item { padding: 10px; }
    QTableWidget::item:selected { background-color: #4a2a6a; }
    QHeaderView::section {
        background-color: #2a2a3a;
        color: #FFFFFF;
        padding: 10px;
        border: none;
        font-weight: bold;
    }
"""


class SectionAccessEditDialog(QDialog):
    """Edit protection settings for a section_password row."""

    def __init__(self, parent=None, record: dict | None = None):
        super().__init__(parent)
        self.record = record or {}
        self.setWindowTitle("Edit access rule")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        section_label = QLabel(self.record.get("display_name", ""))
        section_label.setWordWrap(True)
        section_label.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        form.addRow("Section:", section_label)

        is_admin = self.record.get("section_key") == SECTION_ADMINISTRATOR_BYPASS
        self.protection_check = QCheckBox(
            "Disable section passwords for administrator"
            if is_admin
            else "Require password to open this section"
        )
        self.protection_check.setChecked(bool(self.record.get("protection_enabled")))
        form.addRow("Protection:", self.protection_check)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Leave empty to keep current password")
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText("Confirm new password")

        if is_admin:
            self.password_input.setEnabled(False)
            self.confirm_input.setEnabled(False)
        else:
            form.addRow("New password:", self.password_input)
            form.addRow("Confirm:", self.confirm_input)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet("""
            QDialog { background-color: #12121c; color: #e8e8f0; }
            QLabel { color: #e0e0e8; }
            QLineEdit {
                background: #1a1a2a; color: #fff; border: 1px solid #3a3a4a;
                padding: 8px; border-radius: 4px;
            }
            QCheckBox { color: #e0e0e8; }
        """)

    def _on_accept(self) -> None:
        if self.record.get("section_key") == SECTION_ADMINISTRATOR_BYPASS:
            self.accept()
            return
        pwd = self.password_input.text()
        confirm = self.confirm_input.text()
        if pwd or confirm:
            if pwd != confirm:
                QMessageBox.warning(self, "Password", "Passwords do not match.")
                return
            if len(pwd.strip()) < 4:
                QMessageBox.warning(self, "Password", "Password must be at least 4 characters.")
                return
        elif self.protection_check.isChecked() and not self.record.get("password_set"):
            QMessageBox.warning(
                self,
                "Password",
                "Set a password before enabling protection for this section.",
            )
            return
        self.accept()

    def access_data(self) -> dict:
        return {
            "protection_enabled": self.protection_check.isChecked(),
            "new_password": self.password_input.text().strip(),
        }


class AppUserEditDialog(QDialog):
    """Add or edit an application user."""

    def __init__(self, parent=None, record: dict | None = None):
        super().__init__(parent)
        self.record = record or {}
        self.is_new = not self.record.get("id")
        self.setWindowTitle("New user" if self.is_new else "Edit user")
        self.setMinimumWidth(460)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.username_input = QLineEdit(str(self.record.get("username", "")))
        self.display_name_input = QLineEdit(str(self.record.get("display_name", "")))
        self.role_combo = QComboBox()
        self.role_combo.addItem("Administrator", ROLE_ADMINISTRATOR)
        self.role_combo.addItem("Operator", ROLE_OPERATOR)
        role = self.record.get("role", ROLE_OPERATOR)
        idx = self.role_combo.findData(role)
        if idx >= 0:
            self.role_combo.setCurrentIndex(idx)

        self.active_check = QCheckBox("User is active")
        self.active_check.setChecked(self.record.get("is_active", True))

        form.addRow("Username:", self.username_input)
        form.addRow("Display name:", self.display_name_input)
        form.addRow("Role:", self.role_combo)
        form.addRow("Status:", self.active_check)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet("""
            QDialog { background-color: #12121c; color: #e8e8f0; }
            QLabel, QCheckBox { color: #e0e0e8; }
            QLineEdit, QComboBox {
                background: #1a1a2a; color: #fff; border: 1px solid #3a3a4a;
                padding: 8px; border-radius: 4px;
            }
        """)

    def _on_accept(self) -> None:
        if len(self.username_input.text().strip()) < 2:
            QMessageBox.warning(self, "User", "Username must be at least 2 characters.")
            return
        if len(self.display_name_input.text().strip()) < 2:
            QMessageBox.warning(self, "User", "Display name must be at least 2 characters.")
            return
        self.accept()

    def user_data(self) -> dict:
        return {
            "username": self.username_input.text().strip(),
            "display_name": self.display_name_input.text().strip(),
            "role": self.role_combo.currentData(),
            "is_active": self.active_check.isChecked(),
        }


class PrivacySecurityCenterWindow(SectionMainWindow):
    """Privacy & Security Center — Access Control and Users."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Privacy & Security Center")
        self.access_data: list[dict] = []
        self.users_data: list[dict] = []
        self._access_editable = False
        self._users_editable = False
        self.setup_window_size()
        self.init_ui()
        self.refresh_all()
        self.apply_stylesheet()
    
    def setup_window_size(self) -> None:
        from ui.common.window_helpers import default_window_geometry, ensure_resizable_window

        ensure_resizable_window(self, min_width=1024, min_height=700)
        default_window_geometry(self)

    def init_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._create_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_access_tab(), "Access Control")
        self.tabs.addTab(self._build_users_tab(), "Users")
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self._create_footer())

        self.setCentralWidget(container)

    def _build_access_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        subtitle = QLabel(
            "Manage section passwords for Agents Command Center and Advanced Dataset Options. "
            "Use the administrator row to bypass all section passwords."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        layout.addWidget(subtitle)

        layout.addWidget(self._create_access_toolbar())
        layout.addWidget(self._create_access_table(), 1)
        return w

    def _build_users_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        subtitle = QLabel(
            "Register operators and administrators. Choose who is using the software on this workstation — "
            "the active user is shown on the main dashboard."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        layout.addWidget(subtitle)

        session_row = QHBoxLayout()
        session_row.addWidget(QLabel("Active session user:"))
        self.active_user_combo = QComboBox()
        self.active_user_combo.setMinimumWidth(280)
        self.active_user_combo.setStyleSheet("""
            QComboBox {
                background-color: #1a1a2a; color: #FFFFFF; border: 1px solid #3a3a4a;
                padding: 8px; border-radius: 6px;
            }
        """)
        session_row.addWidget(self.active_user_combo)
        self.apply_user_btn = QPushButton("Apply")
        self.apply_user_btn.setStyleSheet(_BTN_STYLE)
        self.apply_user_btn.clicked.connect(self.apply_active_user)
        session_row.addWidget(self.apply_user_btn)
        session_row.addStretch()
        layout.addLayout(session_row)

        layout.addWidget(self._create_users_toolbar())
        layout.addWidget(self._create_users_table(), 1)
        return w

    def _create_header(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(72)
        frame.setStyleSheet("""
            QFrame { background-color: #1a1a2a; border-bottom: 1px solid #3a3a4a; }
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(20, 0, 20, 0)

        title = QLabel("🔒 Privacy & Security Center")
        title.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        row.addWidget(title)
        row.addStretch()

        self.datetime_label = QLabel()
        self.datetime_label.setStyleSheet("color: #AAAAAA; font-size: 11px;")
        row.addWidget(self.datetime_label)

        btn = QPushButton("Dashboard")
        btn.setFixedHeight(32)
        btn.setStyleSheet(_BTN_STYLE)
        btn.setToolTip("Return to main window")
        btn.clicked.connect(self.tornaAllaDashboard)
        row.addWidget(btn)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_datetime)
        self._timer.start(1000)
        self._update_datetime()
        return frame

    def _create_access_toolbar(self) -> QFrame:
        frame = QFrame()
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)

        self.access_edit_btn = QPushButton("Edit")
        self.access_refresh_btn = QPushButton("Refresh")
        for btn in (self.access_edit_btn, self.access_refresh_btn):
            btn.setStyleSheet(_BTN_STYLE)
            btn.setMinimumHeight(38)
        self.access_edit_btn.clicked.connect(self.edit_access_row)
        self.access_refresh_btn.clicked.connect(self.load_access_data)

        row.addWidget(self.access_edit_btn)
        row.addStretch()
        row.addWidget(self.access_refresh_btn)

        self.access_source_label = QLabel("")
        self.access_source_label.setStyleSheet("color: #7dcea0; font-size: 12px;")
        row.addWidget(self.access_source_label)
        return frame

    def _create_users_toolbar(self) -> QFrame:
        frame = QFrame()
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.user_add_btn = QPushButton("+ New")
        self.user_edit_btn = QPushButton("Edit")
        self.user_delete_btn = QPushButton("Delete")
        self.user_set_active_btn = QPushButton("Set as active")
        self.user_refresh_btn = QPushButton("Refresh")
        for btn in (
            self.user_add_btn,
            self.user_edit_btn,
            self.user_delete_btn,
            self.user_set_active_btn,
            self.user_refresh_btn,
        ):
            btn.setStyleSheet(_BTN_STYLE)
            btn.setMinimumHeight(38)

        self.user_add_btn.clicked.connect(self.add_user)
        self.user_edit_btn.clicked.connect(self.edit_user)
        self.user_delete_btn.clicked.connect(self.delete_user)
        self.user_set_active_btn.clicked.connect(self.set_selected_as_active)
        self.user_refresh_btn.clicked.connect(self.load_users_data)

        row.addWidget(self.user_add_btn)
        row.addWidget(self.user_edit_btn)
        row.addWidget(self.user_delete_btn)
        row.addWidget(self.user_set_active_btn)
        row.addStretch()
        row.addWidget(self.user_refresh_btn)

        self.users_source_label = QLabel("")
        self.users_source_label.setStyleSheet("color: #7dcea0; font-size: 12px;")
        row.addWidget(self.users_source_label)
        return frame

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet(_TABLE_STYLE)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Stretch)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setFont(QFont("Segoe UI", 11))
        return table

    def _create_access_table(self) -> QTableWidget:
        self.access_table = self._make_table([
            "ID", "Section", "Protection", "Password", "Updated",
        ])
        self.access_table.doubleClicked.connect(self.edit_access_row)
        return self.access_table

    def _create_users_table(self) -> QTableWidget:
        self.users_table = self._make_table([
            "ID", "Username", "Display name", "Role", "Active", "Session", "Updated",
        ])
        self.users_table.doubleClicked.connect(self.edit_user)
        return self.users_table

    def _create_footer(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(44)
        row = QHBoxLayout(frame)
        label = QLabel(
            "NStone — all rights reserved."
        )
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #888888; font-size: 10px;")
        row.addWidget(label)
        return frame

    def _update_datetime(self) -> None:
        self.datetime_label.setText(format_header_datetime())

    def _notify_main_user_banner(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "update_current_user_banner"):
            parent.update_current_user_banner()

    def refresh_all(self) -> None:
        self.load_access_data()
        self.load_users_data()

    def load_access_data(self) -> None:
        self.access_data = []
        try:
            self.access_data = load_section_password_records()
            self._access_editable = is_access_control_editable()
            self.access_edit_btn.setEnabled(self._access_editable)
            if self._access_editable:
                self.access_source_label.setText("SQLite — section_password · editing enabled")
            else:
                self.access_source_label.setText("Read-only — database not available")
            self._populate_access_table()
        except Exception as exc:
            self._access_editable = False
            self.access_edit_btn.setEnabled(False)
            QMessageBox.warning(self, "Error", f"Unable to load access rules:\n{exc}")

    def load_users_data(self) -> None:
        self.users_data = []
        try:
            self.users_data = load_app_users()
            self._users_editable = is_app_users_editable()
            for btn in (
                self.user_add_btn,
                self.user_edit_btn,
                self.user_delete_btn,
                self.user_set_active_btn,
            ):
                btn.setEnabled(self._users_editable)
            if self._users_editable:
                self.users_source_label.setText("SQLite — app_user · editing enabled")
            else:
                self.users_source_label.setText("Read-only — database not available")
            self._populate_users_table()
            self._reload_active_user_combo()
        except Exception as exc:
            self._users_editable = False
            for btn in (
                self.user_add_btn,
                self.user_edit_btn,
                self.user_delete_btn,
                self.user_set_active_btn,
            ):
                btn.setEnabled(False)
            QMessageBox.warning(self, "Error", f"Unable to load users:\n{exc}")

    def _reload_active_user_combo(self) -> None:
        current = get_current_user()
        current_id = current["id"] if current else None
        self.active_user_combo.blockSignals(True)
        self.active_user_combo.clear()
        for user in self.users_data:
            if not user["is_active"]:
                continue
            label = f"{user['display_name']} ({user['username']})"
            self.active_user_combo.addItem(label, user["id"])
        if current_id is not None:
            idx = self.active_user_combo.findData(current_id)
            if idx >= 0:
                self.active_user_combo.setCurrentIndex(idx)
        self.active_user_combo.blockSignals(False)

    def _protection_label(self, record: dict) -> str:
        if record.get("is_admin_bypass"):
            return "Bypass active" if record.get("protection_enabled") else "Bypass off"
        return "Enabled" if record.get("protection_enabled") else "Disabled"

    def _password_label(self, record: dict) -> str:
        if record.get("is_admin_bypass"):
            return "—"
        return "Set" if record.get("password_set") else "Not set"

    def _populate_access_table(self) -> None:
        self.access_table.setRowCount(len(self.access_data))
        for row_idx, record in enumerate(self.access_data):
            values = [
                str(record.get("id", "")),
                record.get("display_name", ""),
                self._protection_label(record),
                self._password_label(record),
                (record.get("updated_at") or "—")[:19],
            ]
            for col_idx, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col_idx == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.access_table.setItem(row_idx, col_idx, item)

    def _populate_users_table(self) -> None:
        current = get_current_user()
        current_id = current["id"] if current else None
        self.users_table.setRowCount(len(self.users_data))
        for row_idx, user in enumerate(self.users_data):
            session = "Active" if user["id"] == current_id else ""
            role_label = "Administrator" if user["is_administrator"] else "Operator"
            values = [
                str(user.get("id", "")),
                user.get("username", ""),
                user.get("display_name", ""),
                role_label,
                "Yes" if user.get("is_active") else "No",
                session,
                (user.get("updated_at") or "—")[:19],
            ]
            for col_idx, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col_idx == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.users_table.setItem(row_idx, col_idx, item)

    def _selected_access_record(self) -> dict | None:
        row = self.access_table.currentRow()
        if row < 0 or row >= len(self.access_data):
            return None
        return self.access_data[row]

    def _selected_user_record(self) -> dict | None:
        row = self.users_table.currentRow()
        if row < 0 or row >= len(self.users_data):
            return None
        return self.users_data[row]

    def edit_access_row(self) -> None:
        if not self._access_editable:
            QMessageBox.information(
                self,
                "Read only",
                "Editing requires SQLite at data/nstonellm.db.",
            )
            return
        record = self._selected_access_record()
        if not record:
            QMessageBox.warning(self, "Selection", "Select a row from the table.")
            return
        dialog = SectionAccessEditDialog(self, record=record)
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.access_data()
        result = update_section_access(
            record["id"],
            protection_enabled=data["protection_enabled"],
            new_password=data.get("new_password", ""),
        )
        if result.get("ok"):
            self.load_access_data()
            QMessageBox.information(self, "Saved", "Access rule updated.")
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Update failed."))

    def add_user(self) -> None:
        if not self._users_editable:
            return
        dialog = AppUserEditDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.user_data()
        result = insert_app_user(
            data["username"],
            data["display_name"],
            role=data["role"],
            is_active=data["is_active"],
        )
        if result.get("ok"):
            self.load_users_data()
            QMessageBox.information(self, "Saved", "User added.")
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Insert failed."))

    def edit_user(self) -> None:
        if not self._users_editable:
            QMessageBox.information(self, "Read only", "User editing requires SQLite.")
            return
        record = self._selected_user_record()
        if not record:
            QMessageBox.warning(self, "Selection", "Select a user from the table.")
            return
        dialog = AppUserEditDialog(self, record=record)
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.user_data()
        result = update_app_user(
            record["id"],
            username=data["username"],
            display_name=data["display_name"],
            role=data["role"],
            is_active=data["is_active"],
        )
        if result.get("ok"):
            self.load_users_data()
            self._notify_main_user_banner()
            QMessageBox.information(self, "Saved", "User updated.")
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Update failed."))

    def delete_user(self) -> None:
        if not self._users_editable:
            return
        record = self._selected_user_record()
        if not record:
            QMessageBox.warning(self, "Selection", "Select a user to delete.")
            return
        answer = QMessageBox.question(
            self,
            "Confirm deletion",
            f"Delete user «{record.get('display_name')}»?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        result = delete_app_user(record["id"])
        if result.get("ok"):
            self.load_users_data()
            self._notify_main_user_banner()
            QMessageBox.information(self, "Deleted", "User removed.")
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Delete failed."))

    def _set_active_user_id(self, user_id: int) -> None:
        result = set_current_user(user_id)
        if result.get("ok"):
            self.load_users_data()
            self._notify_main_user_banner()
            QMessageBox.information(
                self,
                "Session updated",
                f"Active user set to {result['user']['display_name']}.",
            )
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Unable to set active user."))

    def apply_active_user(self) -> None:
        user_id = self.active_user_combo.currentData()
        if user_id is None:
            QMessageBox.warning(self, "Selection", "Choose an active user.")
            return
        self._set_active_user_id(int(user_id))

    def set_selected_as_active(self) -> None:
        record = self._selected_user_record()
        if not record:
            QMessageBox.warning(self, "Selection", "Select a user from the table.")
            return
        if not record.get("is_active"):
            QMessageBox.warning(self, "User", "Activate the user before setting the session.")
            return
        self._set_active_user_id(record["id"])

    def apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2a, stop:0.5 #2a2a3a, stop:1 #1a1a2a);
            }
            QLabel { color: #FFFFFF; }
            QTabWidget::pane { border: 1px solid #2a2a3a; background: #12121c; }
            QTabBar::tab {
                background: #1a1a2a; color: #aaa; padding: 10px 18px;
                border: 1px solid #2a2a3a;
            }
            QTabBar::tab:selected { background: #2a1a3a; color: #fff; }
        """)

    def closeEvent(self, event) -> None:
        self._notify_main_user_banner()
        super().closeEvent(event)

    def tornaAllaDashboard(self) -> None:
        self._notify_main_user_banner()
        self.go_back_to_dashboard()
