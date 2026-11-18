"""Pillole informative nella barra header dell'hub NStone."""

from __future__ import annotations

import socket
import urllib.error
import urllib.request

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QWidget

_PILL_STYLE = """
    QPushButton {
        background-color: #1a1a2a;
        color: #E8ECF1;
        border: 1px solid #3a3a5a;
        border-radius: 18px;
        font-family: "Inter", "Segoe UI", sans-serif;
        font-size: 12px;
        font-weight: bold;
        padding: 9px 18px;
    }
    QPushButton:hover {
        background-color: #252538;
        border: 1px solid #5a5a8a;
        color: #FFFFFF;
    }
    QPushButton:pressed {
        background-color: #12121c;
    }
"""

_PILL_FONT = None  # lazy: creato al primo uso (dopo QApplication)


def _pill_font() -> QFont:
    global _PILL_FONT
    if _PILL_FONT is None:
        _PILL_FONT = QFont("Inter", 12, QFont.Bold)
    return _PILL_FONT


def _info(parent, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def _make_pill(label: str, handler) -> QPushButton:
    btn = QPushButton(label)
    btn.setFont(_pill_font())
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(_PILL_STYLE)
    btn.clicked.connect(handler)
    return btn


def _network_status_text() -> str:
    lines = []
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1.5).close()
        lines.append("OK — Internet")
    except OSError:
        lines.append("OFFLINE — Internet")
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=1.5)
        lines.append("OK — Backend API :8000")
    except (urllib.error.URLError, OSError):
        lines.append("OFFLINE — Backend API :8000")
    return "\n".join(lines)


class HeaderPillsBar(QWidget):
    """Network · Requirements · Changelog · Updates · IT/Sysadmin maintenance · About"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        specs = (
            ("Network Status", self._on_network),
            ("System Requirements", self._on_requirements),
            ("Changelog", self._on_changelog),
            ("Updates", self._on_updates),
            ("IT/Sysadmin maintenance", self._on_sysadmin_maintenance),
            ("About", self._on_about),
        )
        for label, handler in specs:
            layout.addWidget(_make_pill(label, handler))

    def _on_network(self) -> None:
        _info(
            self.window(),
            "Network Status",
            _network_status_text(),
        )

    def _on_requirements(self) -> None:
        _info(
            self.window(),
            "System Requirements",
            "Windows 10/11 x64\n"
            "Python 3.10+ (dev) / NSTONELLM bundle\n"
            "RAM 8 GB min · 16 GB consigliati\n"
            "GPU opzionale (Ollama locale)\n"
            "Rete LAN per PLC Snap7 / FastAPI :8000",
        )

    def _on_changelog(self) -> None:
        _info(
            self.window(),
            "Changelog",
            "BETA V1.14 — hub Edge UI, icone SVG, governance CNC shadow,\n"
            "ordini/offerte pipeline, header pillole, logo NST.",
        )

    def _on_updates(self) -> None:
        _info(
            self.window(),
            "Updates",
            "Canale update manuale in questa build.\n"
            "Controlla la cartella release o il repository NStone.",
        )

    def _on_sysadmin_maintenance(self) -> None:
        _info(
            self.window(),
            "IT/Sysadmin maintenance",
            "Strumenti e riferimenti per IT / system administrator:\n\n"
            "· README.md — install, config, security\n"
            "· logs/ — crash log e stato servizi background (locale, non in git)\n"
            "· FastAPI :8000/docs — API backend locale",
        )

    def _on_about(self) -> None:
        _info(
            self.window(),
            "About NStone",
            "NStone workforce hub\n"
            "Edge software for natural stone\n\n"
            "NST Technologies · Nicolò Marconi",
        )
