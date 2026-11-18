"""Shared date/time formatting for UI headers (demo: English)."""
from __future__ import annotations

from datetime import datetime


def format_header_datetime(when: datetime | None = None) -> str:
    """e.g. Wednesday 3 June 2026 • 14:15:56"""
    when = when or datetime.now()
    return when.strftime("%A %d %B %Y • %H:%M:%S")
