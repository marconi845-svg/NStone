"""Base classes for hub section windows (resizable, timers pause when hidden/minimized)."""
from __future__ import annotations

from typing import List, Tuple

from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtGui import QHideEvent, QShowEvent
from PyQt5.QtWidgets import QDialog, QMainWindow, QWidget

from ui.common.window_helpers import configure_independent_window, ensure_initial_maximized, return_to_dashboard


class _SectionTimerLifecycle:
    """Pause background QTimers when a hub section is hidden or minimized."""

    def _init_section_timers(self) -> None:
        if not hasattr(self, "_section_managed_timers"):
            self._section_managed_timers: List[Tuple[QTimer, int]] = []
        self._section_timers_active = False

    def manage_section_timer(self, timer: QTimer, interval_ms: int) -> None:
        """Register a timer; it starts on show and stops on hide/minimize."""
        self._init_section_timers()
        timer.stop()
        self._section_managed_timers.append((timer, int(interval_ms)))

    def _resume_section_timers(self) -> None:
        self._init_section_timers()
        if self._section_timers_active:
            return
        self._section_timers_active = True
        for timer, interval_ms in self._section_managed_timers:
            if interval_ms > 0:
                timer.start(interval_ms)
            else:
                timer.start()

    def _pause_section_timers(self) -> None:
        self._init_section_timers()
        if not self._section_timers_active:
            return
        self._section_timers_active = False
        for timer, _interval_ms in self._section_managed_timers:
            timer.stop()

    def pause_session_timers(self) -> None:
        """Pausa timer (sleep PC) senza chiudere la sezione."""
        self._pause_section_timers()

    def resume_session_timers(self) -> None:
        """Riprende timer se la finestra è ancora visibile."""
        if not self.isVisible() or self._section_is_minimized():
            return
        self._resume_section_timers()

    def on_section_shown(self) -> None:
        """Override in subclasses for refresh-on-show logic."""

    def on_section_hidden(self) -> None:
        """Override in subclasses to stop workers when the section is hidden."""

    def go_back_to_dashboard(self) -> None:
        """Dashboard button: focus main window, minimize this section to taskbar."""
        return_to_dashboard(self)

    def _section_is_minimized(self) -> bool:
        return bool(self.windowState() & Qt.WindowMinimized)

    def _section_handle_activated(self) -> None:
        self._init_section_timers()
        if self._section_is_minimized():
            return
        if getattr(self, "_dashboard_navigation", False):
            return
        was_active = self._section_timers_active
        self._resume_section_timers()
        if not was_active:
            try:
                from modules.ollama_prewarm import prewarm_for_section

                prewarm_for_section(self)
            except Exception:
                pass
            self.on_section_shown()

    def _section_handle_deactivated(self) -> None:
        if getattr(self, "_dashboard_navigation", False):
            return
        self.on_section_hidden()
        self._pause_section_timers()

    def _section_handle_window_state_change(self) -> None:
        if getattr(self, "_dashboard_navigation", False):
            return
        if self._section_is_minimized():
            self._section_handle_deactivated()
        elif self.isVisible():
            self._section_handle_activated()


class SectionDialog(QDialog, _SectionTimerLifecycle):
    """Section dialog — independent resizable window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_independent_window(self, modal=False)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        ensure_initial_maximized(self)
        self._section_handle_activated()

    def hideEvent(self, event: QHideEvent) -> None:
        if not self._section_is_minimized():
            self._section_handle_deactivated()
        super().hideEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.WindowStateChange:
            self._section_handle_window_state_change()
        super().changeEvent(event)


class SectionMainWindow(QMainWindow, _SectionTimerLifecycle):
    """Section main window — independent and resizable."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_independent_window(self, modal=False)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        ensure_initial_maximized(self)
        self._section_handle_activated()

    def hideEvent(self, event: QHideEvent) -> None:
        if not self._section_is_minimized():
            self._section_handle_deactivated()
        super().hideEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.WindowStateChange:
            self._section_handle_window_state_change()
        super().changeEvent(event)
