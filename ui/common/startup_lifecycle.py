"""Timer avvio GUI — annullabili se l'utente chiude durante splash o primi secondi."""
from __future__ import annotations

from typing import Callable, List, Optional

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QApplication, QSplashScreen, QWidget


class StartupLifecycle(QObject):
    """Gestisce splash → main → servizi background senza riaprire dopo chiusura."""

    def __init__(
        self,
        window: QWidget,
        splash: Optional[QSplashScreen] = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._splash = splash
        self._aborted = False
        self._main_shown = False
        self._timers: List[QTimer] = []

    @property
    def aborted(self) -> bool:
        return self._aborted

    def abort(self) -> None:
        self._aborted = True
        for timer in self._timers:
            timer.stop()
        self._timers.clear()

    def _schedule(self, delay_ms: int, callback: Callable[[], None]) -> QTimer:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.start(max(0, int(delay_ms)))
        self._timers.append(timer)
        return timer

    def on_splash_destroyed(self) -> None:
        """Splash chiusa dall'utente prima che compaia la main → esci pulito."""
        if self._aborted or self._main_shown:
            return
        if self._window.isVisible():
            return
        self.abort()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def schedule_show_main(self, delay_ms: int = 3000) -> None:
        self._schedule(delay_ms, self._show_main)

    def schedule_background_services(self, delay_ms: int = 12000) -> None:
        self._schedule(delay_ms, self._start_background_services)

    def _show_main(self) -> None:
        if self._aborted or getattr(self._window, "_closing", False):
            return
        self._main_shown = True
        if self._splash is not None:
            self._splash.close()
        self._window.showMaximized()
        self._window.raise_()
        self._window.activateWindow()
        self.schedule_background_services(12000)

    def _start_background_services(self) -> None:
        if self._aborted or getattr(self._window, "_closing", False):
            return
        if not self._window.isVisible():
            return
        start_fn = getattr(self._window, "_start_background_services", None)
        if callable(start_fn):
            start_fn()
