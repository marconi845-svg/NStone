"""
Design tokens — Production HMI (Flat Metal + ISO state colors).

Moduli: CNC, Polisher, Multifilo, Sludge Treatment.
Superfici piane, niente texture skeuomorfiche; target touch ≥ 48px sui comandi macchina.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QPushButton, QWidget, QLabel

# --- Flat Metal surfaces ---
BG_APP = "#F1F5F9"
BG_PANEL = "#E2E8F0"
BG_INPUT = "#FFFFFF"
BG_HEADER = "#E2E8F0"
BG_STATUS_BAR = "#CBD5E1"

BORDER = "#CBD5E1"
BORDER_STRONG = "#94A3B8"

TEXT_PRIMARY = "#0F172A"
TEXT_SECONDARY = "#475569"
TEXT_MUTED = "#64748B"
TEXT_ON_STATE = "#FFFFFF"

# --- ISO / industrial state ---
STATE_OK = "#16A34A"
STATE_OK_HOVER = "#15803D"
STATE_OK_PRESSED = "#166534"

STATE_WARN = "#D97706"
STATE_WARN_HOVER = "#B45309"
STATE_WARN_PRESSED = "#92400E"

STATE_ALARM = "#DC2626"
STATE_ALARM_HOVER = "#B91C1C"
STATE_ALARM_PRESSED = "#991B1B"

STATE_NEUTRAL = "#475569"
STATE_NEUTRAL_HOVER = "#334155"
STATE_NEUTRAL_PRESSED = "#1E293B"

STATE_INFO = "#2563EB"
STATE_INFO_HOVER = "#1D4ED8"
STATE_INFO_PRESSED = "#1E40AF"

# --- Touch targets ---
TOUCH_MIN_HEIGHT = 48
TOUCH_PADDING = "12px 20px"
TOUCH_FONT = "13px"

# Legacy aliases (dynamic status updates in existing code)
STATUS_OK = STATE_OK
STATUS_WARN = STATE_WARN
STATUS_ERR = STATE_ALARM
STATUS_INFO = STATE_INFO


def production_window_stylesheet() -> str:
    return f"""
        QWidget {{
            background-color: {BG_APP};
            color: {TEXT_PRIMARY};
            font-family: 'Segoe UI', 'Inter', sans-serif;
            font-size: 13px;
        }}
        QGroupBox {{
            background-color: {BG_PANEL};
            border: 1px solid {BORDER_STRONG};
            border-radius: 8px;
            padding: 16px;
            margin-top: 12px;
            color: {TEXT_PRIMARY};
            font-size: 14px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            background-color: {BG_PANEL};
            color: {TEXT_PRIMARY};
        }}
        QLabel {{
            color: {TEXT_PRIMARY};
            background: transparent;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
            background-color: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 13px;
            selection-background-color: {STATE_INFO};
            selection-color: {TEXT_ON_STATE};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            selection-background-color: {BG_PANEL};
        }}
        QTableWidget, QTableView {{
            background-color: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            border-radius: 6px;
            gridline-color: {BORDER};
        }}
        QTableWidget::item:selected, QTableView::item:selected {{
            background-color: #DBEAFE;
            color: {TEXT_PRIMARY};
        }}
        QHeaderView::section {{
            background-color: {BG_PANEL};
            color: {TEXT_PRIMARY};
            padding: 8px;
            border: none;
            border-bottom: 1px solid {BORDER_STRONG};
            font-weight: 600;
            font-size: 12px;
        }}
        QScrollBar:vertical {{
            background-color: {BG_PANEL};
            width: 10px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {BORDER_STRONG};
            min-height: 32px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {STATE_NEUTRAL};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QStatusBar {{
            background-color: {BG_STATUS_BAR};
            color: {TEXT_SECONDARY};
            border-top: 1px solid {BORDER_STRONG};
        }}
    """


def production_scroll_area_stylesheet() -> str:
    return """
        QScrollArea {
            border: none;
            background: transparent;
        }
    """


def production_header_stylesheet() -> str:
    return f"""
        QWidget {{
            background-color: {BG_HEADER};
            border-bottom: 1px solid {BORDER_STRONG};
        }}
    """


def production_status_bar_stylesheet() -> str:
    return f"""
        QWidget {{
            background-color: {BG_STATUS_BAR};
            border-top: 1px solid {BORDER_STRONG};
        }}
    """


def production_monospace_field_stylesheet() -> str:
    return f"""
        QTextEdit, QPlainTextEdit {{
            background-color: {BG_INPUT};
            border: 1px solid {BORDER_STRONG};
            border-radius: 6px;
            color: {TEXT_PRIMARY};
            padding: 8px;
            font-size: 12px;
            font-family: 'Consolas', 'Courier New', monospace;
        }}
    """


def production_section_title_stylesheet() -> str:
    return f"""
        QLabel {{
            color: {TEXT_PRIMARY};
            font-size: 18px;
            font-weight: 700;
        }}
    """


def production_label_stylesheet(
    *,
    variant: str = "body",
    bold: bool = False,
) -> str:
    weight = "600" if bold else "400"
    colors = {
        "body": TEXT_PRIMARY,
        "secondary": TEXT_SECONDARY,
        "muted": TEXT_MUTED,
        "ok": STATE_OK,
        "warn": STATE_WARN,
        "alarm": STATE_ALARM,
        "info": STATE_INFO,
    }
    color = colors.get(variant, TEXT_PRIMARY)
    return f"color: {color}; font-size: 13px; font-weight: {weight}; background: transparent;"


def _button_qss(
    bg: str,
    hover: str,
    pressed: str,
    *,
    fg: str = TEXT_ON_STATE,
    border: str | None = None,
) -> str:
    border_color = border or bg
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {border_color};
            border-radius: 8px;
            padding: {TOUCH_PADDING};
            font-size: {TOUCH_FONT};
            font-weight: 600;
            min-height: {TOUCH_MIN_HEIGHT}px;
        }}
        QPushButton:hover {{
            background-color: {hover};
        }}
        QPushButton:pressed {{
            background-color: {pressed};
        }}
        QPushButton:disabled {{
            background-color: {BG_PANEL};
            color: {TEXT_MUTED};
            border-color: {BORDER};
        }}
    """


_BTN_STYLES: dict[str, str] = {
    "run": _button_qss(STATE_OK, STATE_OK_HOVER, STATE_OK_PRESSED),
    "ok": _button_qss(STATE_OK, STATE_OK_HOVER, STATE_OK_PRESSED),
    "stop": _button_qss(STATE_ALARM, STATE_ALARM_HOVER, STATE_ALARM_PRESSED),
    "alarm": _button_qss(STATE_ALARM, STATE_ALARM_HOVER, STATE_ALARM_PRESSED),
    "hold": _button_qss(
        STATE_WARN, STATE_WARN_HOVER, STATE_WARN_PRESSED, fg=TEXT_ON_STATE
    ),
    "warn": _button_qss(STATE_WARN, STATE_WARN_HOVER, STATE_WARN_PRESSED),
    "reset": _button_qss(STATE_INFO, STATE_INFO_HOVER, STATE_INFO_PRESSED),
    "info": _button_qss(STATE_INFO, STATE_INFO_HOVER, STATE_INFO_PRESSED),
    "primary": _button_qss(STATE_NEUTRAL, STATE_NEUTRAL_HOVER, STATE_NEUTRAL_PRESSED),
    "secondary": _button_qss(
        BG_INPUT,
        BG_PANEL,
        BORDER,
        fg=TEXT_PRIMARY,
        border=BORDER_STRONG,
    ),
    "neutral": _button_qss(
        BG_PANEL,
        BORDER,
        BORDER_STRONG,
        fg=TEXT_PRIMARY,
        border=BORDER_STRONG,
    ),
    "ghost": f"""
        QPushButton {{
            background-color: transparent;
            color: {TEXT_SECONDARY};
            border: 1px solid transparent;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: {TOUCH_FONT};
            font-weight: 600;
            min-height: 40px;
        }}
        QPushButton:hover {{
            background-color: {BG_PANEL};
            color: {TEXT_PRIMARY};
        }}
    """,
}


def apply_production_button(
    button: QPushButton,
    role: str = "secondary",
    *,
    min_height: int | None = None,
) -> None:
    qss = _BTN_STYLES.get(role, _BTN_STYLES["secondary"])
    if min_height is not None:
        qss += f"\nQPushButton {{ min-height: {min_height}px; }}"
    button.setStyleSheet(qss)


def apply_production_theme(window: QWidget) -> None:
    """Applica il tema Production HMI alla finestra radice del modulo."""
    window.setStyleSheet(production_window_stylesheet())


def wire_machine_command_buttons(
    start: QPushButton,
    stop: QPushButton,
    *,
    hold: QPushButton | None = None,
    reset: QPushButton | None = None,
) -> None:
    apply_production_button(start, "run")
    apply_production_button(stop, "stop")
    if hold is not None:
        apply_production_button(hold, "hold")
    if reset is not None:
        apply_production_button(reset, "reset")


def configure_production_module_header(
    header_widget: QWidget,
    dashboard_btn: QPushButton,
    title_label: QLabel,
    ordini_btn: QPushButton | None = None,
) -> None:
    apply_production_button(dashboard_btn, "secondary", min_height=40)
    title_label.setStyleSheet(production_section_title_stylesheet())
    if ordini_btn is not None:
        apply_production_button(ordini_btn, "neutral", min_height=40)
    header_widget.setStyleSheet(production_header_stylesheet())


def state_indicator_style(state: str) -> str:
    """Ritorna stylesheet inline per indicatori PLC / allarme."""
    key = (state or "").lower()
    if key in ("ok", "run", "connected", "online", "green"):
        color = STATE_OK
    elif key in ("warn", "hold", "idle", "waiting", "yellow", "orange"):
        color = STATE_WARN
    elif key in ("alarm", "error", "stop", "offline", "red", "fault"):
        color = STATE_ALARM
    elif key in ("info", "blue"):
        color = STATE_INFO
    else:
        color = TEXT_MUTED
    return production_label_stylesheet(variant="body") + f" color: {color}; font-size: 12px;"

