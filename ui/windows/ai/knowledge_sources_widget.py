"""Tab Sources — audit log retrieval."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from modules.knowledge_audit_db import list_logs

_BTN_STYLE = """
    QPushButton {
        background-color: #2a4a6a;
        color: #FFFFFF;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #3a5a7a; }
"""


class KnowledgeSourcesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Retrieval audit trail (Ask tab + future Quotations hook)"))
        row.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_BTN_STYLE)
        refresh_btn.clicked.connect(self.refresh)
        row.addWidget(refresh_btn)
        layout.addLayout(row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["When", "Context", "Question", "Sources"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setStyleSheet(
            "QTableWidget { background:#0a0a1a; color:#fff; gridline-color:#2a2a3a; }"
            "QHeaderView::section { background:#2a2a3a; color:#fff; padding:6px; }"
        )
        self.table.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self.table, 2)

        layout.addWidget(QLabel("Detail"))
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setStyleSheet(
            "QTextEdit { background:#0a0a1a; color:#ccc; border:1px solid #2a2a3a; border-radius:8px; padding:8px; }"
        )
        layout.addWidget(self.detail, 1)
        self._logs = []

    def refresh(self) -> None:
        self._logs = list_logs(limit=200)
        self.table.setRowCount(len(self._logs))
        for row, entry in enumerate(self._logs):
            src_count = len(entry.get("sources") or [])
            self.table.setItem(row, 0, QTableWidgetItem(str(entry.get("created_at") or "")[:19]))
            self.table.setItem(row, 1, QTableWidgetItem(str(entry.get("context_key") or "")))
            q = str(entry.get("question") or "")
            self.table.setItem(row, 2, QTableWidgetItem(q[:120]))
            self.table.setItem(row, 3, QTableWidgetItem(str(src_count)))
            self.table.item(row, 0).setData(Qt.UserRole, row)

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._logs):
            self.detail.clear()
            return
        entry = self._logs[row]
        lines = [
            f"Question: {entry.get('question')}",
            f"Context: {entry.get('context_key')}",
            f"Module: {entry.get('module')}",
            "",
            "Sources:",
        ]
        for src in entry.get("sources") or []:
            lines.append(
                f"  • {src.get('file_name')} § {src.get('section_title')} "
                f"(chunk #{src.get('chunk_index')}, score {src.get('score')})"
            )
        lines.extend(["", "Answer preview:", str(entry.get("answer_preview") or "")])
        self.detail.setPlainText("\n".join(lines))
