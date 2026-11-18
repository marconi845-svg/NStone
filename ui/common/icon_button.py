"""Pulsante hub con icona SVG minimal e testo."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QLabel

from ui.common.app_icons import DEFAULT_ICON_COLOR, pixmap

_ICON_BUTTON_STYLE = """
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #2a1a3a, stop:1 #1a0a2a);
        border: 1px solid #3a2a4a;
        border-radius: 15px;
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #3a2a4a, stop:1 #2a1a3a);
        border: 1px solid #4a3a5a;
    }
    QPushButton:pressed {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1a0a2a, stop:1 #0a0a1a);
    }
"""


class IconButton(QPushButton):
    """Pulsante moduli hub: icona lineare + etichetta."""

    clicked_with_text = pyqtSignal(str)

    def __init__(self, text: str, *, icon_key: str, parent=None):
        super().__init__(parent)
        self.button_text = text
        self.icon_key = icon_key
        self.setMinimumSize(250, 140)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 16, 12, 16)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        px = pixmap(icon_key, 36, color=DEFAULT_ICON_COLOR)
        if px is not None:
            self.icon_label.setPixmap(px)
        else:
            self.icon_label.setText("•")
            self.icon_label.setStyleSheet(
                "color: #B4BCC8; font-size: 28px; background: transparent;"
            )
        layout.addWidget(self.icon_label)

        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setFont(QFont("Inter", 13, QFont.Medium))
        self.text_label.setStyleSheet(
            "color: #FFFFFF; background: transparent; border: none;"
        )
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        self.setStyleSheet(_ICON_BUTTON_STYLE)
        self.clicked.connect(lambda: self.clicked_with_text.emit(self.button_text))
