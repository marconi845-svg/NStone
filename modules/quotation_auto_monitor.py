"""
Monitor background: elabora richieste NUOVA quando autonomia office consente invio auto.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 90


class QuotationAutoMonitor:
    def __init__(self, interval_sec: int = DEFAULT_INTERVAL_SEC):
        self._interval = max(30, int(interval_sec))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="QuotationAutoMonitor",
            daemon=True,
        )
        self._thread.start()
        try:
            from ui.common.background_services import register_service, set_service_running

            register_service(
                "quotation_auto",
                "Auto-elaborazione richieste preventivo (L2)",
            )
            set_service_running("quotation_auto", True)
        except Exception:
            pass
        logger.info("Quotation auto monitor avviato (ogni %ss)", self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None
        try:
            from ui.common.background_services import set_service_running

            set_service_running("quotation_auto", False)
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                from modules.quotation_auto_pipeline import process_pending_nuova_requests

                out = process_pending_nuova_requests(limit=2)
                if out.get("processed"):
                    logger.info("Quotation auto: elaborate %s richieste", out["processed"])
                try:
                    from ui.common.background_services import record_service_tick

                    record_service_tick("quotation_auto", ok=True)
                except Exception:
                    pass
            except Exception as exc:
                logger.warning("Quotation auto monitor error: %s", exc)
                try:
                    from ui.common.background_services import record_service_tick

                    record_service_tick("quotation_auto", ok=False, error=str(exc))
                except Exception:
                    pass
            self._stop.wait(self._interval)


_monitor: Optional[QuotationAutoMonitor] = None


def start_quotation_auto_monitor(interval_sec: int = DEFAULT_INTERVAL_SEC) -> None:
    global _monitor
    if _monitor is None:
        _monitor = QuotationAutoMonitor(interval_sec=interval_sec)
    _monitor.start()


def stop_quotation_auto_monitor() -> None:
    global _monitor
    if _monitor is not None:
        _monitor.stop()
