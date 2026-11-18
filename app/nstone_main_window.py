"""
Nstone LLM - Edge software for natural stone
Finestra principale PyQt5 con tema scuro
"""
import sys
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QLabel, QPushButton, QFrame,
                             QSplashScreen, QMessageBox, QScrollArea)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QFontDatabase, QPalette, QColor, QPixmap
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_asset(*candidates: str) -> str:
    """Risolve un asset brand (logo/splash) rispetto alla root progetto."""
    for name in candidates:
        path = _PROJECT_ROOT / name
        if path.is_file():
            return str(path)
        path = _PROJECT_ROOT / "assets" / name
        if path.is_file():
            return str(path)
    return str(_PROJECT_ROOT / "assets" / candidates[0])


def _header_logo_pixmap(max_height: int = 92) -> QPixmap:
    """Logo NST per header: trasparente, nitido, senza alone bianco."""
    logo_path = _resolve_asset(
        "nst_logo_header.png",
        "nst_logo_transparent.png",
        "nst_logo.png",
    )
    pix = QPixmap(logo_path)
    if pix.isNull():
        return QPixmap()
    return pix.scaledToHeight(max_height, Qt.SmoothTransformation)

from ui.windows.common.settings_window import SettingsWindow
from ui.windows.admin.database_window import DatabaseWindow
from ui.windows.admin.online_stock_window import OnlineStockWindow
from ui.windows.quotations.quotations_window import QuotationsWindow
from ui.windows.quotations.quotations_hub_window import QuotationsHubWindow
from ui.windows.admin.agentic_calling_window import AgenticCallingWindow
from ui.windows.machines.production_window import ProductionWindow
from ui.windows.orders.orders_window import OrdersWindow
from ui.windows.ai.retrieval_fabric_window import RetrievalFabricWindow
from ui.windows.ai.agents_command_center_window import AgentsCommandCenterWindow
from ui.windows.machines.gestione_multifilo_window import GestioneMultifiloWindow
from ui.windows.machines.gestione_lucidatrice_window import GestioneLucidatriceWindow
from ui.windows.machines.gestione_cnc_window import GestioneCNCWindow
from ui.windows.machines.gestione_fanghi_window import GestioneFanghiWindow
from ui.windows.machines.waste_management_window import WasteManagementWindow
from ui.windows.orders.centro_ordini_produzione_window import CentroOrdiniProduzioneWindow
from ui.windows.common.privacy_security_center_window import PrivacySecurityCenterWindow
from ui.windows.common.ai_governance_compliance_window import AiGovernanceComplianceWindow
from ui.common.hardware_panel import HardwarePanel
from ui.common.ollama_monitor_panel import OllamaMonitorPanel
from ui.common.datetime_ui import format_header_datetime
from ui.common.window_helpers import show_section_dialog, show_section_window
from modules.agentic_calling import load_agentic_calling_config
from modules.voice_bridge import start_voice_bridge, stop_voice_bridge
from modules.quotation_auto_monitor import start_quotation_auto_monitor
from ui.common.background_services import shutdown_all
from ui.common.gmail_imap_scheduler import start_gmail_imap_background, stop_gmail_imap_background
from ui.common.icon_button import IconButton
from ui.common.header_pills import HeaderPillsBar


_NAV_PANEL_BUTTON_STYLE = """
    QPushButton {
        background-color: #1a1a2a;
        color: #FFFFFF;
        border: 1px solid #2a2a3a;
        border-radius: 10px;
        font-size: 12px;
        font-weight: bold;
        padding: 15px;
    }
    QPushButton:hover {
        background-color: #2a2a3a;
        border: 1px solid #3a3a4a;
    }
    QPushButton:pressed {
        background-color: #0a0a1a;
    }
"""


class NStoneMainWindow(QMainWindow):
    """Finestra principale NStone LLM"""

    @staticmethod
    def _create_nav_panel_button(
        label: str,
        min_height: int = 70,
        subtitle: str = "",
    ) -> QPushButton:
        """Pulsante laterale (stesso stile pannello destro: niente frame wrapper)."""
        text = f"{label}\n{subtitle}" if subtitle else label
        btn = QPushButton(text)
        btn.setMinimumHeight(max(min_height, 88) if subtitle else min_height)
        btn.setStyleSheet(_NAV_PANEL_BUTTON_STYLE)
        return btn
    
    def __init__(self):
        super().__init__()
        self.online_stock_window = None
        self.quotations_window = None
        self.quotations_hub_window = None
        self.agentic_calling_window = None
        self.production_window = None
        self.retrieval_fabric_window = None
        self.orders_window = None
        self.agents_command_center_window = None
        self.privacy_security_center_window = None
        self.ai_governance_compliance_window = None
        self.waste_management_window = None
        self.gestione_multifilo_window = None
        self.lucidatrice_calibratrice_window = None
        self.gestione_cnc_window = None
        self.machines_monitoring_window = None
        self.centro_ordini_produzione_window = None
        self._closing = False
        self._startup_lifecycle = None
        self._system_was_suspended = False
        self.init_ui()
        self.setup_timer()
        QTimer.singleShot(800, self._maybe_start_voice_bridge)

    def _start_background_services(self) -> None:
        """Servizi automatici: poll Gmail IMAP + elaborazione preventivi NUOVA."""
        if self._closing or not self.isVisible():
            return
        try:
            from ui.common.gmail_imap_scheduler import start_gmail_imap_background

            start_gmail_imap_background(immediate_poll=False)
            print("Gmail IMAP: poll automatico attivo (config orders.gmail_poll_seconds)")
        except Exception as exc:
            print(f"Gmail IMAP scheduler non avviato: {exc}")
        try:
            start_quotation_auto_monitor()
            print("Quotation auto: elaborazione NUOVA attiva")
        except Exception as exc:
            print(f"Quotation auto monitor non avviato: {exc}")
        try:
            from modules.ollama_prewarm import schedule_idle_prewarm

            schedule_idle_prewarm()
            print("Ollama pre-warm: scheduled (lazy background)")
        except Exception as exc:
            print(f"Ollama pre-warm non schedulato: {exc}")

    def _maybe_start_quotation_auto(self) -> None:
        """Compat — usa _start_background_services."""
        self._start_background_services()

    def _maybe_start_voice_bridge(self) -> None:
        if self._closing or not self.isVisible():
            return
        cfg = load_agentic_calling_config()
        if not cfg.get("enabled", True):
            return
        if not cfg.get("voice_bridge_auto_start", True):
            return
        result = start_voice_bridge()
        if result.started:
            print(f"Voice Bridge: {result.message}")
        else:
            print(f"Voice Bridge non avviato: {result.message}")

    def _shutdown_section_windows(self) -> None:
        """Ferma timer/worker delle sezioni hub ancora aperte."""
        for attr in (
            "quotations_hub_window",
            "quotations_window",
            "orders_window",
            "agentic_calling_window",
            "production_window",
            "retrieval_fabric_window",
            "agents_command_center_window",
            "gestione_multifilo_window",
            "lucidatrice_calibratrice_window",
            "gestione_cnc_window",
            "waste_management_window",
            "centro_ordini_produzione_window",
        ):
            win = getattr(self, attr, None)
            if win is None:
                continue
            if hasattr(win, "_ui_active"):
                win._ui_active = False
            if hasattr(win, "on_section_hidden"):
                try:
                    win.on_section_hidden()
                except Exception:
                    pass

    _SECTION_WINDOW_ATTRS = (
        "quotations_hub_window",
        "quotations_window",
        "orders_window",
        "agentic_calling_window",
        "production_window",
        "retrieval_fabric_window",
        "agents_command_center_window",
        "gestione_multifilo_window",
        "lucidatrice_calibratrice_window",
        "gestione_cnc_window",
        "waste_management_window",
        "centro_ordini_produzione_window",
    )

    def _pause_sections_for_system_suspend(self) -> None:
        """Sleep PC: pausa timer/worker, sezione Ordini può restare aperta ore."""
        for attr in self._SECTION_WINDOW_ATTRS:
            win = getattr(self, attr, None)
            if win is None:
                continue
            if hasattr(win, "pause_for_system_suspend"):
                try:
                    win.pause_for_system_suspend()
                except Exception:
                    pass
            elif hasattr(win, "pause_session_timers"):
                try:
                    win.pause_session_timers()
                except Exception:
                    pass

    def _resume_sections_after_system_suspend(self) -> None:
        for attr in self._SECTION_WINDOW_ATTRS:
            win = getattr(self, attr, None)
            if win is None:
                continue
            if hasattr(win, "resume_after_system_suspend"):
                try:
                    win.resume_after_system_suspend()
                except Exception:
                    pass
            elif hasattr(win, "resume_session_timers"):
                try:
                    win.resume_session_timers()
                except Exception:
                    pass

    def _on_application_state_changed(self, state) -> None:
        """Sospensione PC (sleep): pausa thread Qt; alla ripresa riattiva senza chiudere Ordini."""
        from PyQt5.QtCore import Qt

        if state == Qt.ApplicationSuspended:
            self._system_was_suspended = True
            self._pause_sections_for_system_suspend()
        elif state == Qt.ApplicationActive and getattr(self, "_system_was_suspended", False):
            self._system_was_suspended = False
            if not self._closing:
                self._resume_sections_after_system_suspend()

    def closeEvent(self, event) -> None:
        self._closing = True
        lifecycle = getattr(self, "_startup_lifecycle", None)
        if lifecycle is not None:
            lifecycle.abort()
        self._shutdown_section_windows()
        try:
            from ui.common.worker_lifecycle import ORDERS_WORKER_ATTRS, wait_workers

            for attr in ("orders_window",):
                win = getattr(self, attr, None)
                if win is not None:
                    wait_workers(win, ORDERS_WORKER_ATTRS, timeout_ms=3000)
        except Exception:
            pass
        shutdown_all()
        stop_gmail_imap_background()
        stop_voice_bridge()
        try:
            from modules.ollama_prewarm import cancel_prewarm

            cancel_prewarm()
        except Exception:
            pass
        if hasattr(self, "timer"):
            self.timer.stop()
        super().closeEvent(event)
        
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        self.setWindowTitle("NStone - Workforce Hub")
        self.setMinimumSize(1400, 900)
        
        # Widget centrale
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principale verticale
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
        """)
        main_layout.addWidget(header)
        
        # Layout orizzontale per le tre colonne
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)
        
        # Colonna sinistra
        left_panel = self.create_left_panel()
        content_layout.addWidget(left_panel, 1)
        
        # Area centrale con scroll area unica
        center_area_content = self.create_center_area()
        
        # Scroll area unica per tutta l'area centrale
        center_scroll = QScrollArea()
        center_scroll.setWidgetResizable(True)
        center_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        center_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        center_scroll.setWidget(center_area_content)
        center_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background-color: #1a1a2a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a4a6a;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5a5a7a;
            }
        """)
        
        content_layout.addWidget(center_scroll, 3)
        
        # Colonna destra
        right_panel = self.create_right_panel()
        content_layout.addWidget(right_panel, 1)
        
        main_layout.addLayout(content_layout, 1)
        
        # Footer
        footer = self.create_footer()
        footer.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
        """)
        main_layout.addWidget(footer)
        
        # Applica stylesheet
        self.apply_stylesheet()
        
    def create_header(self):
        """Header: logo (col sx), pillole (col centro 3/5), autonomia + utente (col dx)."""
        header_frame = QFrame()
        header_frame.setFixedHeight(108)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 6, 20, 6)
        header_layout.setSpacing(20)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        logo_label.setStyleSheet("background: transparent; border: none;")
        logo_pix = _header_logo_pixmap(92)
        if not logo_pix.isNull():
            logo_label.setPixmap(logo_pix)
            logo_label.setFixedHeight(logo_pix.height())
        else:
            logo_label.setText("NST")
            logo_label.setStyleSheet(
                "color: #d4b8ff; font-size: 28px; font-weight: bold; background: transparent;"
            )

        left_header = QWidget()
        left_header.setStyleSheet("background: transparent;")
        left_header_layout = QHBoxLayout(left_header)
        left_header_layout.setContentsMargins(15, 0, 15, 0)
        left_header_layout.setSpacing(0)
        left_header_layout.addWidget(logo_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        left_header_layout.addStretch(1)
        header_layout.addWidget(left_header, 1)

        center_header = QWidget()
        center_header.setStyleSheet("background: transparent;")
        center_header_layout = QHBoxLayout(center_header)
        center_header_layout.setContentsMargins(0, 0, 0, 0)
        center_header_layout.setSpacing(0)
        center_header_layout.addStretch(1)
        center_header_layout.addWidget(HeaderPillsBar(), 0, Qt.AlignCenter)
        center_header_layout.addStretch(1)
        header_layout.addWidget(center_header, 3)

        right_header = QWidget()
        right_header.setStyleSheet("background: transparent;")
        right_col = QVBoxLayout(right_header)
        right_col.setContentsMargins(15, 0, 15, 0)
        right_col.setSpacing(2)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.policy_banner_label = QLabel()
        self.policy_banner_label.setAlignment(Qt.AlignRight)
        self.policy_banner_label.setStyleSheet(
            "color: #c8a8e8; font-size: 10px; font-weight: bold;"
        )
        self.update_policy_banner()
        right_col.addWidget(self.policy_banner_label)

        self.current_user_label = QLabel()
        self.current_user_label.setAlignment(Qt.AlignRight)
        self.current_user_label.setStyleSheet(
            "color: #9a8ab8; font-size: 10px; font-weight: bold;"
        )
        self.update_current_user_banner()
        right_col.addWidget(self.current_user_label)
        header_layout.addWidget(right_header, 1)

        return header_frame
    
    def create_left_panel(self):
        """Crea il pannello sinistro con indicatori di stato"""
        panel = QFrame()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(15, 20, 15, 20)
        panel_layout.setSpacing(15)
        
        self.btn_ai_governance = self._create_nav_panel_button(
            "AI GOVERNANCE & COMPLIANCE",
            subtitle="L. 132/2025 · GDPR · EU AI Act",
        )
        self.btn_ai_governance.clicked.connect(self.on_ai_governance_compliance_clicked)
        panel_layout.addWidget(self.btn_ai_governance)

        self.btnAgentsCommandCenter = self._create_nav_panel_button(
            "AGENTS COMMAND CENTER",
            subtitle="Restricted Access · Authorized Operators Only",
        )
        self.btnAgentsCommandCenter.clicked.connect(self.on_agents_command_center_clicked)
        panel_layout.addWidget(self.btnAgentsCommandCenter)

        self.btn_privacy_security_center = self._create_nav_panel_button(
            "PRIVACY & SECURITY CENTER"
        )
        self.btn_privacy_security_center.clicked.connect(self.on_privacy_security_center_clicked)
        panel_layout.addWidget(self.btn_privacy_security_center)

        self.hardware_panel = HardwarePanel()
        panel_layout.addWidget(self.hardware_panel)
        
        panel_layout.addStretch()
        
        return panel
    
    def create_center_area(self):
        """Crea l'area centrale con titolo, sottotitolo e pulsanti"""
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setSpacing(30)
        
        # Titolo principale (logo hub rimosso)
        logo_frame = QFrame()
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setAlignment(Qt.AlignCenter)
        logo_layout.setSpacing(10)

        title_label = QLabel("NStone workforce hub")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Inter", 48, QFont.Bold))
        title_label.setStyleSheet("""
            color: #FFFFFF;
            padding: 10px;
        """)
        logo_layout.addWidget(title_label)
        
        # Sottotitolo
        subtitle_label = QLabel("Edge software for natural stone")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setFont(QFont("Inter", 16))
        subtitle_label.setStyleSheet("""
            color: #CCCCCC;
            padding: 5px;
        """)
        logo_layout.addWidget(subtitle_label)
        
        center_layout.addWidget(logo_frame)
        
        # Griglia di pulsanti 2x3
        buttons_grid = QGridLayout()
        buttons_grid.setSpacing(20)
        
        buttons = [
            ("Online Stock", "stock", 0, 0),
            ("Quotations", "quotations", 0, 1),
            ("Orders", "orders", 1, 0),
            ("Slab/Block Inspector", "inspector", 1, 1),
            ("Agentic Calling", "calling", 2, 0),
            ("Production Order Center", "production_orders", 2, 1),
        ]

        for text, icon_key, row, col in buttons:
            button = IconButton(text, icon_key=icon_key)
            button.clicked_with_text.connect(self.on_module_button_clicked)
            buttons_grid.addWidget(button, row, col)

        # Pulsanti tecnici inseriti nella stessa griglia
        self.btnGestioneCNC = IconButton("CNC Management", icon_key="cnc")
        self.btnGestioneCNC.clicked.connect(self.openGestioneCNC)
        buttons_grid.addWidget(self.btnGestioneCNC, 3, 0)

        self.btnGestioneLucidatriceCalibratrice = IconButton(
            "Polisher / Calibrator", icon_key="polisher"
        )
        self.btnGestioneLucidatriceCalibratrice.clicked.connect(
            self.openGestioneLucidatriceCalibratrice
        )
        buttons_grid.addWidget(self.btnGestioneLucidatriceCalibratrice, 3, 1)

        self.production_management_btn = IconButton(
            "Multiwire Management", icon_key="multifilo"
        )
        self.production_management_btn.clicked.connect(self.open_gestione_multifilo)
        buttons_grid.addWidget(self.production_management_btn, 4, 0)

        self.waste_management_btn = IconButton(
            "Finished Goods / Yield", icon_key="yield"
        )
        self.waste_management_btn.clicked.connect(self.open_waste_management)
        buttons_grid.addWidget(self.waste_management_btn, 4, 1)

        self.btnGestioneFanghi = IconButton("Sludge Treatment", icon_key="sludge")
        self.btnGestioneFanghi.clicked.connect(self.open_gestione_fanghi)
        buttons_grid.addWidget(self.btnGestioneFanghi, 5, 0)

        self.btnRetrievalFabric = IconButton("Retrieval Fabric", icon_key="retrieval_fabric")
        self.btnRetrievalFabric.clicked.connect(self.open_retrieval_fabric)
        buttons_grid.addWidget(self.btnRetrievalFabric, 5, 1)
        
        center_layout.addLayout(buttons_grid)
        center_layout.addStretch()
        
        return center_widget
    
    def create_right_panel(self):
        """Crea il pannello destro con pulsanti opzioni"""
        panel = QFrame()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(15, 20, 15, 20)
        panel_layout.setSpacing(15)
        
        self.dataset_button = self._create_nav_panel_button(
            "ADVANCED DATASET OPTIONS",
            subtitle="Restricted Access · Authorized Operators Only",
        )
        self.dataset_button.clicked.connect(self.open_settings)
        panel_layout.addWidget(self.dataset_button)

        self.db_button = self._create_nav_panel_button("DATABASE ACCESS")
        self.db_button.clicked.connect(self.open_database)
        panel_layout.addWidget(self.db_button)

        self.machines_monitoring_button = self._create_nav_panel_button("MACHINES MONITORING")
        self.machines_monitoring_button.clicked.connect(self.apriMachinesMonitoring)
        panel_layout.addWidget(self.machines_monitoring_button)

        self.ollama_monitor_panel = OllamaMonitorPanel()
        panel_layout.addWidget(self.ollama_monitor_panel)
        
        panel_layout.addStretch()
        
        return panel
    
    def create_footer(self):
        """Footer: data/ora centrata."""
        footer_frame = QFrame()
        footer_frame.setFixedHeight(44)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 8, 20, 8)

        self.datetime_label = QLabel()
        self.datetime_label.setAlignment(Qt.AlignCenter)
        self.datetime_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        self.update_datetime()
        footer_layout.addWidget(self.datetime_label)

        return footer_frame
    
    def apply_stylesheet(self):
        """Applica lo stylesheet con tema scuro e gradiente viola"""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0a0a15, stop:1 #050510);
            }
            QWidget {
                background: transparent;
            }
            QFrame {
                background: transparent;
                border: none;
            }
        """)
        
        # Applica gradiente viola scuro al widget centrale
        self.centralWidget().setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
        """)
    
    def setup_timer(self):
        """Configura il timer per aggiornare data/ora e banner policy"""
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_main_timer_tick)
        self.timer.start(1000)

    def _on_main_timer_tick(self):
        self.update_datetime()
        self.update_policy_banner()
        self.update_current_user_banner()

    def update_current_user_banner(self):
        """Show the workstation active user below date/time (autonomy banner style)."""
        if not hasattr(self, "current_user_label"):
            return
        try:
            from modules.app_users_db import current_user_banner_text

            self.current_user_label.setText(current_user_banner_text())
        except Exception:
            self.current_user_label.setText("👤 Active user unavailable")

    def update_policy_banner(self):
        """Mostra livello autonomia effettivo (Agents Command Center)."""
        if not hasattr(self, "policy_banner_label"):
            return
        try:
            from core.autonomy_policy import get_policy

            self.policy_banner_label.setText(f"⚙ {get_policy().banner_text()}")
        except Exception:
            self.policy_banner_label.setText("⚙ Autonomy policy unavailable")
    
    def update_datetime(self):
        """Update footer date/time."""
        if hasattr(self, "datetime_label"):
            self.datetime_label.setText(format_header_datetime())
    
    def open_settings(self):
        """Open system settings (maximized)."""
        try:
            settings_dialog = SettingsWindow(self)
            settings_dialog.settings_saved.connect(self.on_settings_saved)
            show_section_dialog(settings_dialog)
        except Exception as exc:
            from PyQt5.QtWidgets import QMessageBox
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Advanced Dataset Options",
                f"Unable to open settings:\n\n{exc}",
            )
    
    def on_settings_saved(self, settings):
        """Gestisce il salvataggio delle impostazioni"""
        settings_copy = settings.copy()
        if "api_key" in settings_copy:
            settings_copy["api_key"] = "***" if settings_copy["api_key"] else ""
        print("Impostazioni salvate con successo")
        if hasattr(self, "ollama_monitor_panel") and self.ollama_monitor_panel:
            self.ollama_monitor_panel.refresh_from_config()
    
    def open_database(self):
        """Open database access (maximized)."""
        database_dialog = DatabaseWindow(self)
        show_section_dialog(database_dialog)
    
    def apriMachinesMonitoring(self):
        """Apre la finestra Machines Monitoring"""
        if not hasattr(self, 'machines_monitoring_window') or self.machines_monitoring_window is None:
            from ui.windows.machines.machines_monitoring_window import MachinesMonitoringWindow
            self.machines_monitoring_window = MachinesMonitoringWindow(self)
        show_section_window(self.machines_monitoring_window)
    
    def on_module_button_clicked(self, button_text):
        """Gestisce il click sui pulsanti dei moduli"""
        if button_text == "Online Stock":
            self.open_online_stock()
        elif button_text == "Quotations":
            self.open_quotations_hub()
        elif button_text == "Agentic Calling":
            self.open_agentic_calling()
        elif button_text == "Slab/Block Inspector":
            self.open_production()
        elif button_text == "Production Order Center":
            self.open_centro_ordini_produzione()
        elif button_text == "Orders":
            self.open_orders()
    
    def open_online_stock(self):
        """Apre la finestra Online Stock a schermo intero"""
        if not hasattr(self, 'online_stock_window') or self.online_stock_window is None:
            self.online_stock_window = OnlineStockWindow(self)
        show_section_window(self.online_stock_window)
    
    def open_quotations(self):
        """Apre la finestra Quotations"""
        if not hasattr(self, 'quotations_window') or self.quotations_window is None:
            self.quotations_window = QuotationsWindow(self)
        show_section_window(self.quotations_window)
    
    def open_quotations_hub(self):
        """Apre la finestra Quotations Hub"""
        if not hasattr(self, 'quotations_hub_window') or self.quotations_hub_window is None:
            self.quotations_hub_window = QuotationsHubWindow(self)
        show_section_window(self.quotations_hub_window)
    
    def open_agentic_calling(self):
        """Open Agentic Calling (FreeSWITCH + Ollama voice extensions)."""
        if (
            not hasattr(self, "agentic_calling_window")
            or self.agentic_calling_window is None
        ):
            self.agentic_calling_window = AgenticCallingWindow(self)
        show_section_window(self.agentic_calling_window)
    
    def open_production(self):
        """Apre la finestra Slab/Block Inspector"""
        if not hasattr(self, 'production_window') or self.production_window is None:
            self.production_window = ProductionWindow(self)
        show_section_window(self.production_window)
    
    def open_retrieval_fabric(self):
        """Apre Retrieval Fabric — domain knowledge (MD listini, procedure)."""
        if (
            not hasattr(self, "retrieval_fabric_window")
            or self.retrieval_fabric_window is None
        ):
            self.retrieval_fabric_window = RetrievalFabricWindow(self)
        show_section_window(self.retrieval_fabric_window)
    
    def open_orders(self):
        """Apre la finestra Orders"""
        if not hasattr(self, 'orders_window') or self.orders_window is None:
            self.orders_window = OrdersWindow(self)
        show_section_window(self.orders_window)
    
    def on_agents_command_center_clicked(self):
        """Apre Agents Command Center (autonomia, agenti, tattiche commerciali)."""
        if (
            not hasattr(self, "agents_command_center_window")
            or self.agents_command_center_window is None
        ):
            self.agents_command_center_window = AgentsCommandCenterWindow(self)
        show_section_window(self.agents_command_center_window)
    
    def on_privacy_security_center_clicked(self):
        """Apre la finestra Privacy & Security Center"""
        if not hasattr(self, 'privacy_security_center_window') or self.privacy_security_center_window is None:
            self.privacy_security_center_window = PrivacySecurityCenterWindow(self)
        show_section_window(self.privacy_security_center_window)

    def on_ai_governance_compliance_clicked(self):
        """Apre AI Governance & Compliance Center (L. 132/2025, GDPR, AI Act)."""
        if (
            not hasattr(self, "ai_governance_compliance_window")
            or self.ai_governance_compliance_window is None
        ):
            self.ai_governance_compliance_window = AiGovernanceComplianceWindow(self)
        show_section_window(self.ai_governance_compliance_window)
        self.update_current_user_banner()
    
    def open_waste_management(self):
        """Apre la finestra Gestione Sprechi Materiale"""
        if not hasattr(self, 'waste_management_window') or self.waste_management_window is None:
            self.waste_management_window = WasteManagementWindow(self)
        show_section_window(self.waste_management_window)
    
    def open_gestione_multifilo(self):
        """Apre la finestra Gestione Multifilo"""
        if not hasattr(self, 'gestione_multifilo_window') or self.gestione_multifilo_window is None:
            self.gestione_multifilo_window = GestioneMultifiloWindow(self)
        show_section_window(self.gestione_multifilo_window)
    
    def openGestioneLucidatriceCalibratrice(self):
        """Apre la finestra Gestione Lucidatrice/Calibratrice"""
        if not hasattr(self, 'lucidatrice_calibratrice_window') or self.lucidatrice_calibratrice_window is None:
            self.lucidatrice_calibratrice_window = GestioneLucidatriceWindow(self)
        show_section_window(self.lucidatrice_calibratrice_window)
    
    def openGestioneCNC(self):
        """Apre la finestra Gestione CNC"""
        if not hasattr(self, 'gestione_cnc_window') or self.gestione_cnc_window is None:
            self.gestione_cnc_window = GestioneCNCWindow(self)
        show_section_window(self.gestione_cnc_window)
    
    def open_gestione_fanghi(self):
        """Apre la finestra Gestione Fanghi"""
        if not hasattr(self, 'gestione_fanghi_window') or self.gestione_fanghi_window is None:
            self.gestione_fanghi_window = GestioneFanghiWindow(self)
        show_section_window(self.gestione_fanghi_window)
    
    def open_centro_ordini_produzione(self):
        """Apre la finestra Centro Ordini Produzione"""
        if not hasattr(self, 'centro_ordini_produzione_window') or self.centro_ordini_produzione_window is None:
            self.centro_ordini_produzione_window = CentroOrdiniProduzioneWindow(self)
        show_section_window(self.centro_ordini_produzione_window)


def main():
    """Funzione principale per avviare l'applicazione"""
    try:
        from ui.common.crash_diagnostics import install_crash_diagnostics

        log_path = install_crash_diagnostics(also_console=True)
        print(f"Crash log: {log_path}")
    except Exception as exc:
        print(f"Crash diagnostics non attive: {exc}")

    from PyQt5.QtWidgets import QApplication
    
    # IMPORTANTE: Gli attributi DPI devono essere impostati PRIMA di creare QApplication
    # Abilita DPI scaling e anti-aliasing globale
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)  # Rendering hardware
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # Font globale: Inter (Windows Fonts) se presente, altrimenti fallback
    installed = set(QFontDatabase().families())
    font_families = ["Inter", "Segoe UI", "Roboto", "Noto Sans", "Arial"]
    font = QFont("Segoe UI", 10)
    for font_family in font_families:
        if font_family in installed:
            font = QFont(font_family, 10)
            break
    
    # Configurazione ottimale per qualità testo
    font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
    font.setHintingPreference(QFont.PreferFullHinting)
    font.setKerning(True)
    
    # Applica il font globalmente a tutta l'applicazione
    app.setFont(font)
    
    # Imposta il tema scuro per l'applicazione
    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(10, 10, 21))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(10, 10, 21))
    palette.setColor(QPalette.AlternateBase, QColor(21, 10, 26))
    app.setPalette(palette)
    
    # Mostra splash screen
    splash_path = _resolve_asset("splash screen nstoneLLM.png", "splash.png")
    splash = None
    if os.path.exists(splash_path):
        try:
            pixmap = QPixmap(splash_path)
            if not pixmap.isNull():
                # Ridimensiona mantenendo le proporzioni
                scaled_pixmap = pixmap.scaled(1000, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                splash = QSplashScreen(scaled_pixmap, Qt.WindowStaysOnTopHint)
                splash.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.SplashScreen | Qt.FramelessWindowHint)
                splash.show()
                app.processEvents()  # Mostra la splash screen immediatamente
        except Exception as e:
            print(f"Errore nel caricamento della splash screen: {e}")
    
    # Crea la finestra principale (non mostrarla ancora)
    window = NStoneMainWindow()
    from ui.common.startup_lifecycle import StartupLifecycle

    app.applicationStateChanged.connect(window._on_application_state_changed)
    lifecycle = StartupLifecycle(window, splash)
    window._startup_lifecycle = lifecycle
    if splash is not None:
        splash.destroyed.connect(lifecycle.on_splash_destroyed)
        lifecycle.schedule_show_main(3000)
    else:
        lifecycle._show_main()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

