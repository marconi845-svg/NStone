"""Bulk patch production module windows to Flat Metal theme helpers."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "ui/windows/machines/gestione_cnc_window.py",
    ROOT / "ui/windows/machines/gestione_multifilo_window.py",
    ROOT / "ui/windows/machines/gestione_lucidatrice_window.py",
    ROOT / "ui/windows/machines/gestione_fanghi_window.py",
]

IMPORT_BLOCK = """from ui.theme.production_theme import (
    apply_production_theme,
    apply_production_button,
    production_scroll_area_stylesheet,
    production_header_stylesheet,
    production_status_bar_stylesheet,
    production_monospace_field_stylesheet,
    production_section_title_stylesheet,
    production_label_stylesheet,
    state_indicator_style,
    STATUS_OK,
    STATUS_WARN,
    STATUS_ERR,
    STATUS_INFO,
    TEXT_MUTED,
)
"""

REPLACEMENTS = {
    '"color: #51CF66; font-size: 12px;"': 'state_indicator_style("ok")',
    '"color: #FF6B6B; font-size: 12px;"': 'state_indicator_style("alarm")',
    '"color: #FFD93D; font-size: 12px;"': 'state_indicator_style("warn")',
    '"color: #4DABF7; font-size: 12px;"': 'state_indicator_style("info")',
    '"color: #888899; font-size: 12px;"': 'production_label_stylesheet(variant="muted") + " font-size: 12px;"',
    '"color: #888888; font-size: 11px;"': 'production_label_stylesheet(variant="muted") + " font-size: 11px;"',
    '"color: #00FF00; font-size: 12px;"': 'state_indicator_style("ok")',
    'setStyleSheet("color: #FFFFFF; font-size: 12px;")': 'setStyleSheet(production_label_stylesheet() + " font-size: 12px;")',
    'setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")': 'setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 14px;")',
    'setStyleSheet("color: #CCCCCC; font-size: 12px;")': 'setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 12px;")',
    'setStyleSheet("color: #CCCCCC; font-size: 11px; min-width: 150px;")': 'setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")',
}


def ensure_import(text: str) -> str:
    if "from ui.theme.production_theme import" in text:
        return text
    for marker in (
        "from PyQt5.QtGui import QFont, QColor",
        "from PyQt5.QtGui import QFont",
    ):
        if marker in text:
            return text.replace(marker, IMPORT_BLOCK + marker, 1)
    return IMPORT_BLOCK + text


def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = ensure_import(text)
    text = re.sub(
        r"scroll_area\.setStyleSheet\(\"\"\"[\s\S]*?\"\"\"\)",
        "scroll_area.setStyleSheet(production_scroll_area_stylesheet())",
        text,
        count=1,
    )
    text = re.sub(
        r"    def apply_stylesheet\(self\):\s*\"\"\"[\s\S]*?\"\"\"\s*self\.setStyleSheet\(\"\"\"[\s\S]*?\"\"\"\)",
        '    def apply_stylesheet(self):\n        """Applica tema Production HMI (Flat Metal + ISO)."""\n        apply_production_theme(self)',
        text,
        count=1,
    )
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)

    if "gestione_fanghi" in path.name and "def apply_production_stylesheet" not in text:
        text = text.replace(
            "        register_dashboard(self, parent)\n",
            "        register_dashboard(self, parent)\n        self.apply_production_stylesheet()\n",
        )
        text = text.replace(
            "    def create_header(self):",
            '    def apply_production_stylesheet(self):\n        """Applica tema Production HMI (Flat Metal + ISO)."""\n        apply_production_theme(self)\n\n    def create_header(self):',
        )

    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    for file_path in FILES:
        patch_file(file_path)
        print(f"patched {file_path.name}")
