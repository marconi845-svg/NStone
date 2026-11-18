"""Layout a 3 colonne per hub Orders / Quotations: tabelle laterali ampie, centro on-demand."""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QSplitter, QWidget

HUB_CENTER_COLUMN_INDEX = 1
HUB_CENTER_WIDTH_RATIO = 0.38
HUB_CENTER_MIN_WIDTH = 380
HUB_SIDE_MIN_WIDTH = 240
HUB_SIDE_TOOLBAR_HEIGHT = 34
HUB_SIDE_FOOTER_HEIGHT = 40


def hub_side_toolbar_spacer(height: int = HUB_SIDE_TOOLBAR_HEIGHT) -> QWidget:
    """Spacer per allineare l'inizio tabella quando la colonna sx ha una toolbar."""
    spacer = QWidget()
    spacer.setFixedHeight(height)
    return spacer


def create_hub_three_column_splitter(
    left: QWidget,
    center: QWidget,
    right: QWidget,
    *,
    parent=None,
) -> QSplitter:
    splitter = QSplitter(Qt.Horizontal, parent)
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(6)
    splitter.setOpaqueResize(True)
    splitter.setStyleSheet(
        """
        QSplitter::handle {
            background-color: #2a2a3a;
            margin: 0 1px;
        }
        QSplitter::handle:hover {
            background-color: #4a2a6a;
        }
        """
    )
    left.setMinimumWidth(HUB_SIDE_MIN_WIDTH)
    center.setMinimumWidth(0)
    right.setMinimumWidth(HUB_SIDE_MIN_WIDTH)
    splitter.addWidget(left)
    splitter.addWidget(center)
    splitter.addWidget(right)
    splitter.setCollapsible(0, False)
    splitter.setCollapsible(HUB_CENTER_COLUMN_INDEX, True)
    splitter.setCollapsible(2, False)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(HUB_CENTER_COLUMN_INDEX, 0)
    splitter.setStretchFactor(2, 1)
    return splitter


def _apply_splitter_sizes(splitter: QSplitter, sizes: list[int]) -> None:
    if not sizes or len(sizes) != splitter.count():
        return
    splitter.setSizes(sizes)


def _splitter_total_width(splitter: QSplitter) -> int:
    width = splitter.width()
    if width > 100:
        return width
    parent = splitter.parentWidget()
    while parent is not None:
        parent_width = parent.width()
        if parent_width > 100:
            return parent_width
        parent = parent.parentWidget()
    sizes = splitter.sizes()
    total = sum(sizes)
    if total > 0:
        return total
    return 900


def collapse_hub_center_column(
    splitter: QSplitter,
    center_index: int = HUB_CENTER_COLUMN_INDEX,
) -> None:
    center = splitter.widget(center_index)
    if center is not None:
        center.setMinimumWidth(0)
        center.hide()

    def apply() -> None:
        total = _splitter_total_width(splitter)
        half = total // 2
        sizes = [0, 0, 0]
        for idx in range(splitter.count()):
            if idx == center_index:
                sizes[idx] = 0
            elif idx < center_index:
                sizes[idx] = half
            else:
                sizes[idx] = total - half
        _apply_splitter_sizes(splitter, sizes)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(center_index, 0)
        splitter.setStretchFactor(2, 1)

    apply()
    QTimer.singleShot(0, apply)


def expand_hub_center_column(
    splitter: QSplitter,
    center_index: int = HUB_CENTER_COLUMN_INDEX,
    *,
    center_ratio: float = HUB_CENTER_WIDTH_RATIO,
    min_center: int = HUB_CENTER_MIN_WIDTH,
) -> None:
    center = splitter.widget(center_index)
    if center is not None:
        center.setMinimumWidth(min_center)
        center.show()

    def apply() -> None:
        total = _splitter_total_width(splitter)
        center_w = max(int(total * center_ratio), min_center)
        max_center = total - (HUB_SIDE_MIN_WIDTH * 2)
        if max_center > min_center:
            center_w = min(center_w, max_center)
        else:
            center_w = max(min_center, total // 3)
        side = (total - center_w) // 2
        remainder = total - center_w - (side * 2)
        sizes = [0, 0, 0]
        for idx in range(splitter.count()):
            if idx == center_index:
                sizes[idx] = center_w
            elif idx < center_index:
                sizes[idx] = side
            else:
                sizes[idx] = side + remainder
        _apply_splitter_sizes(splitter, sizes)
        splitter.setStretchFactor(0, 100 - int(center_ratio * 100))
        splitter.setStretchFactor(center_index, int(center_ratio * 100))
        splitter.setStretchFactor(2, 100 - int(center_ratio * 100))

    apply()
    QTimer.singleShot(0, apply)
    QTimer.singleShot(120, apply)


def schedule_hub_splitter_collapsed(
    splitter: QSplitter,
    center_index: int = HUB_CENTER_COLUMN_INDEX,
) -> None:
    QTimer.singleShot(0, lambda: collapse_hub_center_column(splitter, center_index))
    QTimer.singleShot(150, lambda: collapse_hub_center_column(splitter, center_index))
