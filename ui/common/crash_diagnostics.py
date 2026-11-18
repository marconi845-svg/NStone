"""
Diagnostica crash: log eccezioni Python e stack trace su file (uso prolungato / debug).
"""
from __future__ import annotations

import faulthandler
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_LOG: Optional[logging.Logger] = None
_LOG_PATH: Optional[Path] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def install_crash_diagnostics(*, also_console: bool = True) -> Path:
    """
    Registra excepthook + faulthandler su logs/nstonellm_crash.log.
    Chiamare all'avvio, prima di QApplication.
    """
    global _LOG, _LOG_PATH

    log_dir = _project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "nstonellm_crash.log"
    _LOG_PATH = log_path

    handlers: list[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8")]
    if also_console:
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )
    _LOG = logging.getLogger("nstonellm.crash")

    def _excepthook(exc_type, exc_value, exc_tb):
        lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        text = "".join(lines)
        if _LOG:
            _LOG.critical("Eccezione non gestita (thread principale):\n%s", text)
        else:
            sys.stderr.write(text)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    try:
        crash_file = open(log_path, "a", encoding="utf-8")
        faulthandler.enable(file=crash_file, all_threads=True)
    except OSError:
        faulthandler.enable(all_threads=True)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if _LOG:
        _LOG.info("=== Sessione avviata %s ===", stamp)

    return log_path


def log_event(message: str, *, level: int = logging.INFO) -> None:
    if _LOG:
        _LOG.log(level, message)


def crash_log_path() -> Optional[Path]:
    return _LOG_PATH
