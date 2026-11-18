"""Mini-grafico trend per variabile PLC (DB live)."""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Optional

from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget


class _TrendCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: Deque[float] = deque(maxlen=120)
        self.setMinimumHeight(160)
        self.setStyleSheet("background-color: #0a0a1a; border: 1px solid #3a3a4a;")

    def add_sample(self, value: Optional[float]) -> None:
        if value is None:
            return
        try:
            self._history.append(float(value))
        except (TypeError, ValueError):
            return
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if len(self._history) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin = 12
        vals = list(self._history)
        vmin, vmax = min(vals), max(vals)
        if vmax - vmin < 1e-9:
            vmax = vmin + 1.0
        pen = QPen(QColor("#51CF66"))
        pen.setWidth(2)
        painter.setPen(pen)
        span = max(1, len(vals) - 1)
        for i in range(1, len(vals)):
            x0 = margin + (w - 2 * margin) * (i - 1) / span
            x1 = margin + (w - 2 * margin) * i / span
            y0 = h - margin - (h - 2 * margin) * (vals[i - 1] - vmin) / (vmax - vmin)
            y1 = h - margin - (h - 2 * margin) * (vals[i] - vmin) / (vmax - vmin)
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))
        painter.end()


class PlcTrendDialog(QDialog):
    def __init__(self, variable_name: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Trend — {variable_name}")
        self.setMinimumSize(480, 280)
        self._canvas = _TrendCanvas()
        layout = QVBoxLayout(self)
        title = QLabel(f"{variable_name}" + (f" ({unit})" if unit else ""))
        title.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        self._value_label = QLabel("—")
        self._value_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        layout.addWidget(self._value_label)
        layout.addWidget(self._canvas, 1)
        self.setStyleSheet("QDialog { background-color: #0a0a15; }")

    def add_sample(self, value: Any, display: str) -> None:
        self._value_label.setText(f"Ultimo: {display}")
        if isinstance(value, bool):
            self._canvas.add_sample(1.0 if value else 0.0)
        elif isinstance(value, (int, float)):
            self._canvas.add_sample(float(value))
