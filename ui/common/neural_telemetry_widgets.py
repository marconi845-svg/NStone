"""Widget telemetria Neural engine (QPainter, zero dipendenze extra)."""

from __future__ import annotations

import math
from typing import List, Optional

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget


def _smooth_series(values: List[float]) -> List[float]:
    if len(values) < 3:
        return list(values)
    out: List[float] = []
    for i, v in enumerate(values):
        if i == 0 or i == len(values) - 1:
            out.append(v)
        else:
            out.append((values[i - 1] + v + values[i + 1]) / 3.0)
    return out


def _alpha(color: QColor, a: int) -> QColor:
    c = QColor(color)
    c.setAlpha(a)
    return c


class TelemetrySparkline(QWidget):
    """Curva neon con gradiente sotto e badge valore istantaneo."""

    def __init__(
        self,
        title: str,
        *,
        line_color: str = "#00f2fe",
        fill_top: str = "#8B5CF640",
        parent=None,
    ):
        super().__init__(parent)
        self._title = title
        self._line = QColor(line_color)
        self._fill_top = QColor(fill_top)
        self._values: List[float] = []
        self._display_value: Optional[str] = None
        self._idle_phase = 0.0
        self.setMinimumHeight(72)
        self.setMaximumHeight(88)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")

    def set_series(self, values: List[float], display_value: Optional[str] = None) -> None:
        self._values = [float(v) for v in values if v is not None]
        self._display_value = display_value
        self.update()

    def advance_idle(self, step: float = 0.12) -> None:
        """Animazione leggera quando non c'è storico live."""
        if len(self._values) < 2:
            self._idle_phase += step
            self.update()

    def _draw_series(self, painter: QPainter, plot: QRectF, series: List[float]) -> None:
        vmin = min(series)
        vmax = max(series)
        span = vmax - vmin
        if span < 1e-6:
            vmin -= 0.5
            vmax += 0.5
            span = vmax - vmin

        points = []
        n = len(series)
        for i, val in enumerate(series):
            x = plot.left() + (i / (n - 1)) * plot.width()
            y = plot.bottom() - ((val - vmin) / span) * plot.height()
            points.append((x, y))

        path_bottom = plot.bottom()
        grad = QLinearGradient(0, plot.top(), 0, path_bottom)
        grad.setColorAt(0.0, self._fill_top)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        fill_path = QPainterPath()
        fill_path.moveTo(points[0][0], path_bottom)
        for x, y in points:
            fill_path.lineTo(x, y)
        fill_path.lineTo(points[-1][0], path_bottom)
        fill_path.closeSubpath()
        painter.fillPath(fill_path, grad)

        pen = QPen(self._line, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        for i in range(1, len(points)):
            x1, y1 = points[i - 1]
            x2, y2 = points[i]
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_idle_wave(self, painter: QPainter, plot: QRectF) -> None:
        """Onda soft + gradiente quando il motore è in idle."""
        n = 28
        mid = (plot.top() + plot.bottom()) / 2.0
        amp = plot.height() * 0.14
        points = []
        for i in range(n):
            x = plot.left() + (i / max(n - 1, 1)) * plot.width()
            y = mid + math.sin(self._idle_phase + i * 0.38) * amp
            points.append((x, y))

        idle_fill = _alpha(self._line, 55)
        idle_line = _alpha(self._line, 150)

        path_bottom = plot.bottom()
        grad = QLinearGradient(0, plot.top(), 0, path_bottom)
        grad.setColorAt(0.0, idle_fill)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        fill_path = QPainterPath()
        fill_path.moveTo(points[0][0], path_bottom)
        for x, y in points:
            fill_path.lineTo(x, y)
        fill_path.lineTo(points[-1][0], path_bottom)
        fill_path.closeSubpath()
        painter.fillPath(fill_path, grad)

        pen = QPen(idle_line, 1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        for i in range(1, len(points)):
            x1, y1 = points[i - 1]
            x2, y2 = points[i]
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = 8, 8, 22, 8
        plot = QRectF(margin_l, margin_t, w - margin_l - margin_r, h - margin_t - margin_b)

        painter.setPen(QColor("#888899"))
        painter.setFont(QFont("Inter", 9, QFont.Bold))
        painter.drawText(8, 14, self._title)

        badge = self._display_value or "idle"
        badge_idle = len(self._values) < 2 and badge in ("—", "idle", None)
        if badge_idle:
            badge = "idle"
            painter.setPen(_alpha(self._line, 180))
        else:
            painter.setPen(self._line)
        painter.setFont(QFont("Inter", 10, QFont.Bold))
        painter.drawText(w - 8 - painter.fontMetrics().width(badge), 14, badge)

        if len(self._values) < 2:
            self._draw_idle_wave(painter, plot)
            painter.end()
            return

        self._draw_series(painter, plot, _smooth_series(self._values))
        painter.end()


class VramRingGauge(QWidget):
    """Anello telemetria: attivo / idle colorato / offline (Neural engine, Host hardware)."""

    def __init__(self, parent=None, *, caption: str = "VRAM"):
        super().__init__(parent)
        self._loaded = False
        self._offline = False
        self._idle_phase = 0.0
        self._caption = caption
        self._detail = "—"
        self.setMinimumSize(88, 88)
        self.setMaximumSize(100, 100)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")

    def set_state(
        self,
        loaded: bool,
        detail: str = "—",
        *,
        offline: bool = False,
    ) -> None:
        self._loaded = loaded
        self._offline = offline
        self._detail = detail
        self.update()

    def advance_idle(self, step: float = 0.08) -> None:
        if not self._loaded and not self._offline:
            self._idle_phase += step
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        size = min(self.width(), self.height())
        cx, cy = self.width() / 2.0, self.height() / 2.0
        outer = size * 0.42
        inner = size * 0.30

        track = QColor("#2a2a3a")
        if self._offline:
            glow = QColor("#e74c3c")
            arc_span = 50
        elif self._loaded:
            glow = QColor("#00f2fe")
            arc_span = 270
        else:
            pulse = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(self._idle_phase))
            glow = QColor(int(139 * pulse), int(92 * pulse), int(246 * pulse))
            arc_span = 145

        ring = QRectF(cx - outer, cy - outer, outer * 2, outer * 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawEllipse(ring)

        idle_ring = _alpha(glow, 70 if not self._loaded else 255)
        pen = QPen(idle_ring if not self._loaded and not self._offline else glow, 6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        start = 225 * 16
        painter.drawArc(
            int(cx - outer),
            int(cy - outer),
            int(outer * 2),
            int(outer * 2),
            start,
            -arc_span * 16,
        )

        if not self._loaded and not self._offline:
            inner_pen = QPen(_alpha(QColor("#8B5CF6"), 90), 2)
            painter.setPen(inner_pen)
            painter.setBrush(Qt.NoBrush)
            inner_r = outer * 0.72
            painter.drawEllipse(
                QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
            )

        caption_color = "#FFFFFF" if self._loaded else "#c8a8e8"
        painter.setPen(QColor(caption_color))
        painter.setFont(QFont("Inter", 8, QFont.Bold))
        painter.drawText(QRectF(cx - inner, cy - 10, inner * 2, 14), Qt.AlignCenter, self._caption)
        painter.setPen(QColor("#CCCCCC"))
        painter.setFont(QFont("Inter", 7))
        detail = self._detail if len(self._detail) <= 14 else self._detail[:12] + "…"
        painter.drawText(QRectF(cx - inner, cy + 2, inner * 2, 20), Qt.AlignCenter | Qt.TextWordWrap, detail)

        painter.end()
