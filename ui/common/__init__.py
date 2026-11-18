"""
Modulo UI comune - Widget riutilizzabili per tutte le finestre macchina
"""

from .datetime_ui import format_header_datetime
from .ethernet_status_widget import EthernetStatusWidget
from .hardware_panel import HardwarePanel
from .ollama_monitor_panel import OllamaMonitorPanel
from .plc_db_live_dialog import PlcDbLiveDialog
from .section_window import SectionDialog, SectionMainWindow
from .window_helpers import (
    apply_machine_section_window,
    configure_independent_window,
    default_window_geometry,
    ensure_initial_maximized,
    ensure_resizable_window,
    open_or_raise_window,
    present_window,
    register_dashboard,
    resolve_dashboard,
    return_to_dashboard,
    show_auxiliary_window,
    show_section_dialog,
    show_section_window,
)

__all__ = [
    'EthernetStatusWidget',
    'HardwarePanel',
    'OllamaMonitorPanel',
    'PlcDbLiveDialog',
    'SectionDialog',
    'SectionMainWindow',
    'configure_independent_window',
    'default_window_geometry',
    'ensure_initial_maximized',
    'ensure_resizable_window',
    'format_header_datetime',
    'apply_machine_section_window',
    'present_window',
    'register_dashboard',
    'resolve_dashboard',
    'return_to_dashboard',
    'open_or_raise_window',
    'show_auxiliary_window',
    'show_section_dialog',
    'show_section_window',
]




