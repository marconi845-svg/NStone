"""
Icone SVG minimali monocromatiche (stile enterprise / Palantir-like).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = _PROJECT_ROOT / "assets" / "icons"

# Grigio chiaro freddo — leggibile su sfondo scuro, non “emoji color”
DEFAULT_ICON_COLOR = "#B4BCC8"
HOVER_ICON_COLOR = "#E8ECF1"

ICON_ALIASES: Dict[str, str] = {
    "stock": "stock",
    "online_stock": "stock",
    "quotations": "quotations",
    "orders": "orders",
    "inspector": "inspector",
    "slab_inspector": "inspector",
    "calling": "calling",
    "agentic_calling": "calling",
    "production_orders": "production_orders",
    "cnc": "cnc",
    "polisher": "polisher",
    "multifilo": "multifilo",
    "multiwire": "multifilo",
    "yield": "yield",
    "finished_goods": "yield",
    "sludge": "sludge",
    "logistic": "logistic",
    "logistics": "logistic",
    "retrieval_fabric": "retrieval_fabric",
    "knowledge": "retrieval_fabric",
    "retrieval": "retrieval_fabric",
}


def _resolve_icon_file(name: str) -> Optional[Path]:
    key = ICON_ALIASES.get(name, name)
    path = ICON_DIR / f"{key}.svg"
    return path if path.is_file() else None


@lru_cache(maxsize=64)
def _renderer_for(name: str) -> Optional[QSvgRenderer]:
    path = _resolve_icon_file(name)
    if path is None:
        return None
    renderer = QSvgRenderer(str(path))
    return renderer if renderer.isValid() else None


def pixmap(
    name: str,
    size: int = 32,
    *,
    color: str = DEFAULT_ICON_COLOR,
) -> Optional[QPixmap]:
    renderer = _renderer_for(name)
    if renderer is None:
        return None
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    # Tint monocromatico sopra l'SVG (stroke bianco nel file)
    tinted = QPixmap(size, size)
    tinted.fill(Qt.transparent)
    tp = QPainter(tinted)
    tp.setRenderHint(QPainter.Antialiasing, True)
    tp.drawPixmap(0, 0, px)
    tp.setCompositionMode(QPainter.CompositionMode_SourceIn)
    tp.fillRect(tinted.rect(), QColor(color))
    tp.end()
    return tinted


def icon(name: str, size: int = 32, *, color: str = DEFAULT_ICON_COLOR) -> QIcon:
    px = pixmap(name, size, color=color)
    if px is None:
        return QIcon()
    return QIcon(px)


def has_icon(name: str) -> bool:
    return _resolve_icon_file(name) is not None
