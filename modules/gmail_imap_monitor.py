"""
Monitor Gmail IMAP: modalità timer (poll) o thread dedicato (idle leggero).

In modalità idle il thread attende tra un check e l'altro senza bloccare la UI;
non usa token Gemini (solo check_gmail_orders).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class GmailImapMonitor:
    """Avvia/ferma controllo casella ordini in base a config orders.imap_mode."""

    def __init__(self, on_check: Callable[[], None]):
        self._on_check = on_check
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        from modules.orders_imap_service import get_orders_imap_settings

        settings = get_orders_imap_settings()
        mode = settings.get("imap_mode", "poll")
        interval = max(60, int(settings.get("gmail_poll_seconds", 300)))

        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()

        if mode == "idle":
            self._thread = threading.Thread(
                target=self._idle_loop,
                args=(interval,),
                name="GmailImapIdle",
                daemon=True,
            )
            logger.info("Gmail IMAP monitor: modalità idle (intervallo %ss)", interval)
        else:
            self._thread = threading.Thread(
                target=self._poll_loop,
                args=(interval,),
                name="GmailImapPoll",
                daemon=True,
            )
            logger.info("Gmail IMAP monitor: modalità poll (intervallo %ss)", interval)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def _poll_loop(self, interval: int) -> None:
        while not self._stop.is_set():
            self._stop.wait(interval)
            if self._stop.is_set():
                break
            try:
                self._on_check()
            except Exception as exc:
                logger.warning("Gmail poll check error: %s", exc)

    def _idle_loop(self, interval: int) -> None:
        """Loop dedicato: stesso check del poll ma senza QTimer Qt."""
        while not self._stop.is_set():
            self._stop.wait(interval)
            if self._stop.is_set():
                break
            try:
                self._on_check()
            except Exception as exc:
                logger.warning("Gmail idle check error: %s", exc)
