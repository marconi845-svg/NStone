"""Helpers for independent, non-modal section and tool windows."""
from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QDialog, QMainWindow, QSizePolicy, QWidget

# Qt default maximum (effectively unlimited)
_MAX_DIM = 16777215


def ensure_resizable_window(window: QWidget, *, min_width: int = 960, min_height: int = 640) -> None:
    """Allow drag-resize; clear any prior setFixedSize on the top-level window."""
    window.setMinimumSize(min_width, min_height)
    window.setMaximumSize(_MAX_DIM, _MAX_DIM)
    if isinstance(window, QDialog):
        window.setSizeGripEnabled(True)
    policy = window.sizePolicy()
    policy.setHorizontalPolicy(QSizePolicy.Preferred)
    policy.setVerticalPolicy(QSizePolicy.Preferred)
    window.setSizePolicy(policy)


def configure_independent_window(window: QWidget, *, modal: bool = False) -> None:
    """Own taskbar entry, minimizable; does not block the rest of the app."""
    if isinstance(window, QDialog):
        window.setModal(modal)
    if not getattr(window, "_independent_window_configured", False):
        window.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        window._independent_window_configured = True
    ensure_resizable_window(window)


def default_window_geometry(window: QWidget, *, width_ratio: float = 0.92, height_ratio: float = 0.90) -> None:
    """Legacy fallback when a window must not use maximized mode (rare)."""
    try:
        app = QApplication.instance()
        screen = app.primaryScreen() if app else None
        if screen is None and hasattr(window, "screen"):
            screen = window.screen()
        if screen is None:
            window.resize(1400, 900)
            return
        geo = screen.availableGeometry()
        w = max(960, int(geo.width() * width_ratio))
        h = max(640, int(geo.height() * height_ratio))
        window.resize(w, h)
        window.move(
            geo.x() + max(0, (geo.width() - w) // 2),
            geo.y() + max(0, (geo.height() - h) // 2),
        )
    except Exception:
        window.resize(1400, 900)


def ensure_initial_maximized(window: QWidget) -> None:
    """First show: open maximized (full workspace). Skips fixed-size dialogs."""
    if getattr(window, "_initial_maximize_done", False):
        return
    max_w, max_h = window.maximumWidth(), window.maximumHeight()
    min_w, min_h = window.minimumWidth(), window.minimumHeight()
    if max_w < _MAX_DIM and max_w == min_w and max_h < _MAX_DIM and max_h == min_h:
        return
    window._initial_maximize_done = True
    if not window.isMaximized():
        QTimer.singleShot(0, window.showMaximized)


def apply_machine_section_window(window: QWidget) -> None:
    """Machine / monitoring hubs: resizable independent window (maximized on first show)."""
    configure_independent_window(window, modal=False)


def register_dashboard(window: QWidget, dashboard: QWidget | None = None) -> None:
    """Keep explicit link to NStone main window for the Dashboard button."""
    dash = dashboard or getattr(window, "parent_window", None) or window.parent()
    if dash is not None:
        window._nstone_dashboard = dash


def resolve_dashboard(window: QWidget) -> Optional[QWidget]:
    dash = getattr(window, "_nstone_dashboard", None)
    if dash is not None:
        return dash
    dash = getattr(window, "parent_window", None)
    if dash is not None:
        return dash
    parent = window.parent()
    if parent is not None:
        return parent
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if isinstance(widget, QMainWindow) and widget.__class__.__name__ == "NStoneMainWindow":
            return widget
    return None


def _clear_dashboard_navigation_flag(window: QWidget) -> None:
    window._dashboard_navigation = False


def return_to_dashboard(window: QWidget) -> None:
    """Show main dashboard; minimize current section (taskbar) without heavy refresh."""
    dashboard = resolve_dashboard(window)
    if dashboard is None:
        return

    window._dashboard_navigation = True
    window._fast_section_hide = True
    try:
        pause = getattr(window, "_pause_section_timers", None)
        if callable(pause):
            pause()
        on_hidden = getattr(window, "on_section_hidden", None)
        if callable(on_hidden):
            on_hidden()
    finally:
        window._fast_section_hide = False

    if dashboard.isMinimized():
        dashboard.showNormal()
    dashboard.show()
    dashboard.raise_()
    dashboard.activateWindow()

    def _minimize_section() -> None:
        if window.isVisible() and not window.isMinimized():
            window.showMinimized()
        QTimer.singleShot(400, lambda: _clear_dashboard_navigation_flag(window))

    QTimer.singleShot(0, _minimize_section)


def present_window(window: QWidget, *, maximized: bool = True) -> None:
    """Show a top-level window; default is maximized (full screen workspace)."""
    register_dashboard(window)
    configure_independent_window(window, modal=False)
    if window.isMinimized():
        window.showNormal()
    if maximized:
        window.showMaximized()
    else:
        if window.isMaximized():
            window.showNormal()
        if not window.isVisible():
            default_window_geometry(window)
        window.show()
    window.raise_()
    window.activateWindow()


def show_section_window(window: QWidget) -> None:
    """Show a hub section maximized."""
    present_window(window, maximized=True)


def show_auxiliary_window(window: QWidget, *, maximized: bool = True) -> None:
    """Show a tool/detail window without blocking navigation."""
    present_window(window, maximized=maximized)


def show_section_dialog(dialog: QWidget, *, maximized: bool = True) -> int:
    """Backward-compatible alias: opens non-modally (no exec_ block)."""
    show_auxiliary_window(dialog, maximized=maximized)
    return 0


def open_or_raise_window(
    owner: Any,
    attr_name: str,
    factory: Callable[[], QWidget],
    *,
    maximized: bool = True,
    recreate: bool = False,
) -> QWidget:
    """Reuse an existing window on owner or create via factory."""
    existing: Optional[QWidget] = getattr(owner, attr_name, None)
    if existing is not None and not recreate:
        try:
            show_auxiliary_window(existing, maximized=maximized)
            return existing
        except RuntimeError:
            existing = None

    window = factory()
    setattr(owner, attr_name, window)
    show_auxiliary_window(window, maximized=maximized)
    return window
