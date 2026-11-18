"""UI helpers for section PIN prompts."""
from __future__ import annotations

from PyQt5.QtWidgets import QInputDialog, QLineEdit, QMessageBox

from modules.access_control_db import section_requires_pin, verify_section_pin


def prompt_section_access(parent, section_key: str, *, title: str = "Restricted Access") -> bool:
    """
    Return True if the user may access the section (no PIN required, bypass, or valid PIN).
    """
    if not section_requires_pin(section_key):
        return True

    pin, ok = QInputDialog.getText(
        parent,
        title,
        "Enter section password:",
        QLineEdit.Password,
    )
    if not ok:
        return False
    if verify_section_pin(section_key, pin):
        return True
    QMessageBox.warning(
        parent,
        "Access denied",
        "Invalid password.\nAuthorized operators only.",
    )
    return False
