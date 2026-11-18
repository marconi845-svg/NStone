"""
Traccia step-by-step pipeline ordini (poll IMAP → classificazione → conferma → LLM).
Visibile nel log monitor Orders (sidebar).
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Deque, List, Optional

_lock = threading.Lock()
_last_run: Deque[str] = deque(maxlen=80)
_current_subject: Optional[str] = None


def trace_step(step: str, detail: str = "", *, subject: Optional[str] = None) -> None:
    """Registra uno step pipeline (thread-safe)."""
    ts = datetime.now().strftime("%H:%M:%S")
    subj = (subject or _current_subject or "email").replace("\r", " ").replace("\n", " ")[:36]
    line = f"  [{ts}] {subj} │ {step}"
    if detail:
        line += f" — {detail[:120]}"
    with _lock:
        _last_run.append(line)
    try:
        from ui.common.gmail_imap_poll_log import append_pipeline_event

        append_pipeline_event(line.strip())
    except Exception:
        pass


def begin_email_trace(subject: str) -> None:
    global _current_subject
    _current_subject = subject
    trace_step("START", subject=subject)


def end_email_trace(outcome: str) -> None:
    global _current_subject
    trace_step("END", outcome, subject=_current_subject)
    _current_subject = None


def get_recent_trace_lines(*, max_lines: int = 40) -> List[str]:
    with _lock:
        return list(_last_run)[-max_lines:]
