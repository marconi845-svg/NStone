"""
Stato e log poll IMAP Gmail condivisi (scheduler globale + UI Orders/Quotations).
"""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

_lock = threading.Lock()
_log_lines: Deque[str] = deque(maxlen=300)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def status_file_path() -> Path:
    return _project_root() / "logs" / "gmail_orders_status.json"


def log_file_path() -> Path:
    return _project_root() / "logs" / "gmail_imap_poll.log"


def _format_poll_line(result: Dict[str, Any], *, source: str = "auto") -> str:
    ts = datetime.now().strftime("%H:%M:%S")
    tag = "MAN" if source == "manual" else "AUTO"
    if result.get("skipped"):
        return f"[{ts}] {tag} poll saltato (già in corso)"
    if result.get("status") == "ERROR":
        err = (result.get("error_message") or "errore sconosciuto")[:120]
        return f"[{ts}] {tag} ERRORE — {err}"
    n_proc = int(result.get("emails_processed") or 0)
    n_ord = int(result.get("orders_saved") or 0)
    n_conf = int(result.get("confirmations_sent") or 0)
    n_in = int(result.get("quotation_inbound") or 0)
    n_rep = int(result.get("quotation_replies") or 0)
    subj = (result.get("last_email_subject") or "").strip().replace("\r", " ").replace("\n", " ")
    if len(subj) > 55:
        subj = subj[:55] + "…"
    parts = [f"{n_proc} mail", f"{n_ord} ordini", f"{n_conf} conferme"]
    if n_in or n_rep:
        parts.append(f"+{n_in} preventivi · {n_rep} risposte NS-Q")
    llm_mode = result.get("confirmation_use_llm_on_poll")
    if llm_mode is not None:
        parts.append("LLM-on" if llm_mode else "LLM-off")
    line = f"[{ts}] {tag} OK — " + " · ".join(parts)
    if subj:
        line += f" — «{subj}»"
    return line


def append_pipeline_event(message: str) -> None:
    """Riga di dettaglio pipeline (per mail singola) nel log sidebar."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"  [{ts}] {message.strip()}"
    log_path = log_file_path()
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    with _lock:
        _log_lines.append(line)


def record_imap_poll_result(result: Dict[str, Any], *, source: str = "auto") -> None:
    """Persiste stato JSON, append log file e buffer in memoria."""
    line = _format_poll_line(result, source=source)
    status_path = status_file_path()
    log_path = log_file_path()
    try:
        status_path.parent.mkdir(parents=True, exist_ok=True)
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    with _lock:
        _log_lines.append(line)


def get_poll_log_lines(*, max_lines: int = 50) -> List[str]:
    with _lock:
        if _log_lines:
            return list(_log_lines)[-max_lines:]
    log_path = log_file_path()
    if not log_path.exists():
        return []
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return lines[-max_lines:]
    except Exception:
        return []


def get_poll_log_text(*, max_lines: int = 50) -> str:
    lines = get_poll_log_lines(max_lines=max_lines)
    if not lines:
        return "Nessun poll registrato ancora.\nIl monitor si aggiorna automaticamente ogni pochi secondi."
    return "\n".join(lines)


def read_status_snapshot() -> Optional[Dict[str, Any]]:
    path = status_file_path()
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
