"""
Animazione vintage: floppy drive che 'mangia' il floppy.
Unica animazione del progetto NStone — Retrieval Fabric PDF import.
"""
from __future__ import annotations

import math

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class FloppyDriveWidget(QWidget):
    """Drive 3.5\" con floppy che scivola dentro lo slot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._led_on = True
        self.setFixedSize(300, 220)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_phase(self, phase: float) -> None:
        self._phase = max(0.0, min(1.0, phase))
        self._led_on = int(self._phase * 20) % 2 == 0 or self._phase < 0.15
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        cx = w / 2.0

        # Corpo drive — beige anni '90
        body_top = 70
        body_h = 120
        body_w = 220
        body_left = cx - body_w / 2
        body = QColor("#c8c4b0")
        shadow = QColor("#8a8678")
        slot = QColor("#1a1a1a")

        painter.setPen(QPen(shadow, 2))
        painter.setBrush(body)
        painter.drawRoundedRect(int(body_left), body_top, int(body_w), body_h, 8, 8)

        # Etichetta drive
        painter.setPen(QColor("#4a4a4a"))
        painter.setFont(QFont("Courier New", 9, QFont.Bold))
        painter.drawText(int(body_left + 14), body_top + 22, "NSTONE KB")

        # Slot
        slot_y = body_top + 52
        slot_w = 150
        slot_h = 8
        slot_x = cx - slot_w / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(slot)
        painter.drawRect(int(slot_x), int(slot_y), int(slot_w), int(slot_h))

        # LED attività
        led_x = int(body_left + body_w - 28)
        led_y = body_top + 18
        led_color = QColor("#39ff14") if self._led_on and self._phase > 0.05 else QColor("#2a4a2a")
        painter.setBrush(led_color)
        painter.setPen(QPen(QColor("#1a301a"), 1))
        painter.drawEllipse(led_x, led_y, 10, 10)

        # Floppy — scivola dentro lo slot man mano che phase → 1
        floppy_w = 130
        floppy_h = 125
        start_y = body_top - floppy_h + 18
        end_y = slot_y + slot_h - 8
        floppy_y = start_y + (end_y - start_y) * self._phase
        floppy_x = cx - floppy_w / 2

        if self._phase < 0.98:
            self._draw_floppy(painter, floppy_x, floppy_y, floppy_w, floppy_h)

        # Testo retro sotto
        painter.setPen(QColor("#e8e0c8"))
        painter.setFont(QFont("Courier New", 10))
        msg = "READING FLOPPY…" if self._phase < 1.0 else "DATA OK"
        tw = painter.fontMetrics().width(msg)
        painter.drawText(int(cx - tw / 2), h - 12, msg)
        painter.end()

    def _draw_floppy(self, painter: QPainter, x: float, y: float, fw: float, fh: float) -> None:
        shell = QColor("#2a2a8a")
        label = QColor("#ff6b9d")
        metal = QColor("#9a9a9a")
        shutter = QColor("#6a6a6a")

        painter.setPen(QPen(QColor("#1a1a5a"), 2))
        painter.setBrush(shell)
        painter.drawRoundedRect(int(x), int(y), int(fw), int(fh), 4, 4)

        # Slider metallico in alto
        painter.setBrush(metal)
        painter.setPen(Qt.NoPen)
        painter.drawRect(int(x + 28), int(y + 6), int(fw - 56), 14)

        # Shutter
        painter.setBrush(shutter)
        painter.drawRect(int(x + fw / 2 - 18), int(y + 24), 36, 10)

        # Etichetta rosa
        painter.setBrush(label)
        painter.setPen(QPen(QColor("#cc4477"), 1))
        painter.drawRect(int(x + 16), int(y + 42), int(fw - 32), int(fh - 54))

        painter.setPen(QColor("#fff"))
        painter.setFont(QFont("Courier New", 8, QFont.Bold))
        painter.drawText(int(x + 22), int(y + 58), "KNOWLEDGE")
        painter.drawText(int(x + 22), int(y + 72), "BASE .PDF")


class FloppyImportOverlay(QFrame):
    """Overlay modale con animazione floppy durante import PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("floppyImportOverlay")
        self.setStyleSheet(
            """
            QFrame#floppyImportOverlay {
                background-color: rgba(8, 8, 18, 210);
                border: 2px solid #5a3a7a;
                border-radius: 12px;
            }
            """
        )
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._elapsed_ms = 0
        self._running = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        title = QLabel("Retrieval Fabric")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #c8a8e8; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        self.drive = FloppyDriveWidget()
        layout.addWidget(self.drive, alignment=Qt.AlignCenter)
        self.subtitle = QLabel("Import PDF → Markdown")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setStyleSheet("color: #aaa; font-size: 11px; font-family: 'Courier New';")
        layout.addWidget(self.subtitle)
        self.hide()

    def start(self, message: str = "Import PDF → Markdown") -> None:
        self.subtitle.setText(message)
        self._elapsed_ms = 0
        self._running = True
        self.drive.set_phase(0.0)
        self._timer.start()
        self.show()
        self.raise_()

    def finish(self) -> None:
        self._running = False
        self.drive.set_phase(1.0)
        self._timer.stop()
        QTimer.singleShot(350, self.hide)

    def _tick(self) -> None:
        if not self._running:
            return
        self._elapsed_ms += self._timer.interval()
        # Ciclo ~2.8s: il floppy entra, poi riparte finché non finisce il job
        cycle_ms = 2800
        t = (self._elapsed_ms % cycle_ms) / cycle_ms
        # Easing: lento all'inizio, accelera in ingestione
        eased = 1.0 - math.pow(1.0 - t, 2.2)
        self.drive.set_phase(min(0.92, eased))
