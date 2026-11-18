"""
Helper condivisi per lifecycle di QThread / aggiornamenti UI nelle sezioni hub.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from PyQt5.QtCore import QThread


def is_ui_active(owner) -> bool:
    return bool(getattr(owner, "_ui_active", False))


def wire_worker(owner, worker: QThread, finished_slot: Callable, attr_name: str) -> None:
    """Avvia worker con cleanup automatico (no accumulo thread).

    Il risultato viaggia sul segnale custom `result_ready`; il cleanup
    (deleteLater) è collegato SOLO al `finished` nativo di QThread, emesso
    a thread realmente terminato. Collegare deleteLater a un segnale emesso
    dentro run() distrugge il thread mentre gira → crash 0xC0000409.
    """
    result_signal = getattr(worker, "result_ready", None)
    if result_signal is not None:
        result_signal.connect(finished_slot)
    else:
        worker.finished.connect(finished_slot)
    worker.finished.connect(lambda: setattr(owner, attr_name, None))
    worker.finished.connect(worker.deleteLater)
    setattr(owner, attr_name, worker)
    worker.start()


def wait_workers(owner, attr_names: Iterable[str], timeout_ms: int = 1500) -> None:
    for attr in attr_names:
        worker = getattr(owner, attr, None)
        if worker is None:
            continue
        if worker.isRunning():
            if hasattr(worker, "requestInterruption"):
                worker.requestInterruption()
            if not worker.wait(timeout_ms):
                try:
                    worker.terminate()
                    worker.wait(500)
                except Exception:
                    pass
        setattr(owner, attr, None)


def safe_widget_update(owner, callback: Callable[[], None]) -> None:
    if not is_ui_active(owner):
        return
    try:
        callback()
    except RuntimeError:
        pass


QUOTATIONS_WORKER_ATTRS = (
    "_status_worker",
    "_neural_stats_worker",
    "_messages_worker",
    "_detail_worker",
    "_ai_worker",
    "_gmail_poll_worker",
)

ORDERS_WORKER_ATTRS = (
    "_neural_stats_worker",
    "_sent_orders_worker",
    "gmail_check_worker",
    "_order_ai_worker",
    "_ai_worker",
)
