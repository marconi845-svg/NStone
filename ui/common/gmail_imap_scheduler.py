"""
Poll IMAP Gmail in background (ordini + preventivi + risposte thread).
Avviato automaticamente con l'app — nessuna sezione Orders/Quotations deve restare aperta.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_monitor = None
_lock = threading.Lock()
_running = False


def _run_imap_check() -> None:
    global _running
    _running = True
    try:
        from modules.orders_imap_service import check_gmail_orders

        result = check_gmail_orders()
        try:
            from ui.common.gmail_imap_poll_log import record_imap_poll_result

            record_imap_poll_result(result, source="auto")
        except Exception:
            pass
        ok = result.get("status") != "ERROR" and not result.get("skipped")
        err = str(result.get("error_message") or "") or None
        try:
            from ui.common.background_services import (
                record_service_tick,
                register_service,
                set_service_running,
            )

            register_service(
                "gmail_imap",
                "Poll automatico casella Gmail (ordini + preventivi + risposte NS-Q)",
            )
            set_service_running("gmail_imap", True)
            record_service_tick("gmail_imap", ok=ok, error=err)
        except Exception:
            pass
        if result.get("skipped"):
            logger.debug("IMAP poll saltato (già in corso)")
        elif ok:
            logger.info(
                "IMAP auto: %s email, +%s preventivi, +%s risposte thread",
                result.get("emails_processed", 0),
                result.get("quotation_inbound", 0),
                result.get("quotation_replies", 0),
            )
            _notify_quotations_ui_refresh()
            _notify_orders_ui_refresh()
    except Exception as exc:
        logger.warning("Gmail IMAP check error: %s", exc)
        try:
            from ui.common.background_services import record_service_tick

            record_service_tick("gmail_imap", ok=False, error=str(exc))
        except Exception:
            pass
    finally:
        _running = False


def _notify_quotations_ui_refresh() -> None:
    """Aggiorna tabella Quotations sul main thread se la sezione è aperta."""
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        for widget in app.topLevelWidgets():
            if widget.__class__.__name__ != "QuotationsHubWindow":
                continue
            if not getattr(widget, "_ui_active", False):
                continue
            from PyQt5.QtCore import QTimer

            if hasattr(widget, "load_messages_from_backend"):
                QTimer.singleShot(0, lambda w=widget: w.load_messages_from_backend(force_api=False))
            if hasattr(widget, "update_gmail_status"):
                QTimer.singleShot(0, lambda w=widget: w.update_gmail_status())
            break
    except Exception:
        pass


def _notify_orders_ui_refresh() -> None:
    """Aggiorna monitor IMAP Orders sul main thread se la sezione è aperta."""
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        for widget in app.topLevelWidgets():
            if widget.__class__.__name__ != "OrdersWindow":
                continue
            if not getattr(widget, "_ui_active", False):
                continue
            from PyQt5.QtCore import QTimer

            if hasattr(widget, "refresh_gmail_monitor_panel"):
                QTimer.singleShot(0, widget.refresh_gmail_monitor_panel)
            if hasattr(widget, "load_orders_from_files"):
                QTimer.singleShot(0, widget.load_orders_from_files)
            break
    except Exception:
        pass


def is_gmail_imap_scheduler_active() -> bool:
    """True se il monitor globale IMAP è in esecuzione."""
    return _monitor is not None and _monitor._thread is not None and _monitor._thread.is_alive()


def _imap_auto_start_disabled() -> bool:
    import os

    if os.environ.get("NSTONELLM_SKIP_IMAP", "").strip().lower() in ("1", "true", "yes"):
        return True
    try:
        from modules.orders_imap_service import get_orders_imap_settings

        return not get_orders_imap_settings().get("imap_auto_start", True)
    except Exception:
        return False


def start_gmail_imap_background(*, immediate_poll: bool = False) -> None:
    """Avvia monitor IMAP globale (idempotente). Poll differito — no crash all'avvio GUI."""
    if _imap_auto_start_disabled():
        logger.warning(
            "Gmail IMAP disabilitato (NSTONELLM_SKIP_IMAP o orders.imap_auto_start=false)"
        )
        return

    global _monitor
    with _lock:
        if _monitor is None:
            from modules.gmail_imap_monitor import GmailImapMonitor

            _monitor = GmailImapMonitor(_run_imap_check)
        _monitor.start()
        logger.info("Gmail IMAP automatico avviato (intervallo da config orders.gmail_poll_seconds)")

    if immediate_poll:
        threading.Thread(
            target=_run_imap_check,
            name="GmailImapFirstPoll",
            daemon=True,
        ).start()


def stop_gmail_imap_background() -> None:
    global _monitor
    with _lock:
        if _monitor is not None:
            _monitor.stop()
        try:
            from ui.common.background_services import set_service_running

            set_service_running("gmail_imap", False)
        except Exception:
            pass


def trigger_imap_poll_now(*, source: str = "manual") -> dict:
    """Poll immediato (pulsante UI / debug)."""
    from modules.orders_imap_service import check_gmail_orders

    result = check_gmail_orders()
    try:
        from ui.common.gmail_imap_poll_log import record_imap_poll_result

        record_imap_poll_result(result, source=source)
    except Exception:
        pass
    return result
