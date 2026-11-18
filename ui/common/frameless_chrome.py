"""Frameless hub window — single title bar (no OS + in-app double chrome)."""
from __future__ import annotations

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ui.theme.quotations_theme import BTN_GHOST, apply_button_role


class _DragHandle:
    def __init__(self, window: QWidget, handle: QWidget) -> None:
        self._window = window
        self._handle = handle
        self._origin: QPoint | None = None
        handle.mousePressEvent = self._press  # type: ignore[method-assign]
        handle.mouseMoveEvent = self._move  # type: ignore[method-assign]
        handle.mouseReleaseEvent = self._release  # type: ignore[method-assign]

    def _press(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._origin = event.globalPos() - self._window.frameGeometry().topLeft()
            event.accept()

    def _move(self, event) -> None:
        if self._origin is not None and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPos() - self._origin)
            event.accept()

    def _release(self, event) -> None:
        self._origin = None
        if hasattr(self._handle, "mouseReleaseEvent"):
            QWidget.mouseReleaseEvent(self._handle, event)


def _chrome_btn(text: str, tooltip: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedSize(36, 28)
    btn.setToolTip(tooltip)
    btn.setStyleSheet("""
        QPushButton {
            background-color: transparent;
            color: #CCCCCC;
            border: none;
            border-radius: 4px;
            font-size: 14px;
        }
        QPushButton:hover { background-color: #3a3a4a; color: #FFFFFF; }
    """)
    return btn


def add_window_controls(window: QWidget, layout) -> None:
    """Minimize / maximize / close on the right of the hub top bar."""
    row = QHBoxLayout()
    row.setSpacing(4)
    row.setContentsMargins(0, 0, 0, 0)

    btn_min = _chrome_btn("—", "Minimize")
    btn_min.clicked.connect(window.showMinimized)

    btn_max = _chrome_btn("□", "Maximize")
    btn_max.clicked.connect(
        lambda: window.showNormal() if window.isMaximized() else window.showMaximized()
    )

    btn_close = _chrome_btn("✕", "Close")
    btn_close.setStyleSheet("""
        QPushButton {
            background-color: transparent;
            color: #CCCCCC;
            border: none;
            border-radius: 4px;
            font-size: 13px;
        }
        QPushButton:hover { background-color: #8B3030; color: #FFFFFF; }
    """)
    btn_close.clicked.connect(window.close)

    row.addWidget(btn_min)
    row.addWidget(btn_max)
    row.addWidget(btn_close)
    layout.addLayout(row)


def apply_frameless_hub_chrome(window: QWidget, drag_handle: QWidget) -> None:
    window.setWindowFlags(
        Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint
    )
    _DragHandle(window, drag_handle)
