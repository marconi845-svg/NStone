"""Design tokens — Quotations Hub (Primary / Secondary / Danger)."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHeaderView, QPushButton, QTableView

# Text
TEXT_PRIMARY = "#F0F0F5"
TEXT_SECONDARY = "#B4B4C8"
TEXT_MUTED = "#8E8EA8"
TEXT_SUBTITLE_OK = "#8FD99A"

# Status (localhost / neural)
STATUS_OK = "#8FD99A"
STATUS_WARN = "#E8C468"
STATUS_ERR = "#E87070"
STATUS_ACCENT = "#9B8CF6"

# Buttons
BTN_PRIMARY = """
    QPushButton {
        background-color: #8B5CF6;
        color: #FFFFFF;
        border: 1px solid #9B6CF6;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #9B6CF6; }
    QPushButton:disabled {
        background-color: #3a3a4a;
        color: #777;
        border-color: #4a4a5a;
    }
"""

BTN_SECONDARY = """
    QPushButton {
        background-color: #2a2a3a;
        color: #E8E8EE;
        border: 1px solid #4a4a5a;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #353548;
        border-color: #5a5a6a;
    }
    QPushButton:disabled {
        background-color: #252530;
        color: #666;
        border-color: #3a3a4a;
    }
"""

BTN_DANGER = """
    QPushButton {
        background-color: #8B3030;
        color: #FFFFFF;
        border: 1px solid #A04040;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #A04040; }
    QPushButton:disabled {
        background-color: #3a3a4a;
        color: #777;
        border-color: #4a4a5a;
    }
"""

BTN_GHOST = """
    QPushButton {
        background-color: transparent;
        color: #CCCCCC;
        border: none;
        border-radius: 8px;
        font-size: 13px;
        text-align: left;
        padding: 10px 15px;
    }
    QPushButton:hover {
        background-color: #2a2a3a;
        color: #FFFFFF;
    }
"""

BTN_TECHNICAL = """
    QPushButton {
        background-color: transparent;
        color: #22D3EE;
        border: 1px solid #22D3EE;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: rgba(34, 211, 238, 0.12);
        border-color: #67E8F9;
    }
    QPushButton:disabled {
        background-color: transparent;
        color: #555;
        border-color: #3a3a4a;
    }
"""

BTN_RAG_COMPACT = """
    QPushButton {
        background-color: transparent;
        color: #22D3EE;
        border: 1px solid #22D3EE;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 10px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: rgba(34, 211, 238, 0.12);
    }
    QPushButton:disabled {
        color: #555;
        border-color: #3a3a4a;
    }
"""

BTN_FILTER = """
    QPushButton {
        background-color: #1a1a2a;
        color: #B4B4C8;
        border: 1px solid #3a3a4a;
        border-radius: 6px;
        padding: 4px 14px;
        font-size: 11px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #252535;
        color: #E8E8EE;
    }
    QPushButton:checked {
        background-color: #2a2a3a;
        color: #FFFFFF;
        border: 1px solid #8B5CF6;
    }
"""

BTN_FILTER_TECH = """
    QPushButton {
        background-color: #1a1a2a;
        color: #B4B4C8;
        border: 1px solid #3a3a4a;
        border-radius: 6px;
        padding: 4px 14px;
        font-size: 11px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #252535;
        color: #E8E8EE;
    }
    QPushButton:checked {
        background-color: rgba(34, 211, 238, 0.1);
        color: #67E8F9;
        border: 1px solid #22D3EE;
    }
"""

TABLE_STYLE = """
    QTableView {
        background-color: #0a0a1a;
        border: 1px solid #2a2a3a;
        border-radius: 8px;
        color: #FFFFFF;
        gridline-color: #2a2a3a;
    }
    QTableView::item { padding: 6px 8px; border: none; }
    QTableView::item:selected { background-color: #4a2a6a; }
    QHeaderView::section {
        background-color: #2a2a3a;
        color: #E8E8EE;
        padding: 8px;
        border: none;
        font-weight: bold;
        font-size: 11px;
    }
"""

_ROLE_STYLES = {
    "primary": BTN_PRIMARY,
    "secondary": BTN_SECONDARY,
    "danger": BTN_DANGER,
    "ghost": BTN_GHOST,
    "technical": BTN_TECHNICAL,
    "rag_compact": BTN_RAG_COMPACT,
    "filter": BTN_FILTER,
    "filter_tech": BTN_FILTER_TECH,
}


def apply_button_role(button: QPushButton, role: str, *, min_height: int = 36) -> None:
    style = _ROLE_STYLES.get(role, BTN_SECONDARY)
    button.setStyleSheet(style)
    button.setMinimumHeight(min_height)


def is_technical_stato(stato: str) -> bool:
    s = (stato or "").upper()
    return "TECNICA" in s


def request_type_badge(stato: str) -> tuple[str, str]:
    """Ritorna (etichetta badge, colore) per colonna tipo richiesta."""
    if is_technical_stato(stato):
        return "TECNICA", "#22D3EE"
    return "ORDINE", "#A78BFA"


def status_dot_color(stato: str) -> str:
    s = (stato or "").upper()
    if s in ("NUOVA", "NEW"):
        return STATUS_ACCENT
    if "TECNICA" in s:
        return "#6BA3E8"
    if s in ("ELABORATA", "BOZZA_IN_ATTESA", "RISPOSTA_TECNICA", "IN_CONVERSAZIONE"):
        return STATUS_WARN
    if s.startswith("ERRORE"):
        return STATUS_ERR
    if s == "ORDINE_CONFERMATO":
        return STATUS_OK
    return TEXT_MUTED


def configure_requests_table(table: QTableView) -> None:
    table.setStyleSheet(TABLE_STYLE)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.Fixed)
    header.setSectionResizeMode(1, QHeaderView.Fixed)
    header.setSectionResizeMode(2, QHeaderView.Stretch)
    header.setSectionResizeMode(3, QHeaderView.Stretch)
    header.setSectionResizeMode(4, QHeaderView.Stretch)
    header.setSectionResizeMode(5, QHeaderView.Fixed)
    table.setColumnWidth(0, 78)
    table.setColumnWidth(1, 128)
    table.setColumnWidth(5, 108)


def configure_email_table(table: QTableView) -> None:
    table.setStyleSheet(TABLE_STYLE)
    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    header.setSectionResizeMode(0, QHeaderView.Fixed)
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    header.setSectionResizeMode(2, QHeaderView.Stretch)
    table.setColumnWidth(0, 128)
