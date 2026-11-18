"""
Machines Monitoring Window
Finestra dedicata al monitoraggio della rete e delle macchine
Monitoraggio sicuro via socket (nessun comando di sistema)
"""
import re
import sys
import socket
from datetime import datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from ui.common.window_helpers import show_auxiliary_window
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QScrollArea, QGroupBox,
                             QTextEdit, QTableWidget, QTableWidgetItem, QSizePolicy,
                             QAbstractItemView, QHeaderView, QMessageBox, QApplication,
                             QDialog)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from core.machine_plc_config import (
    MACHINE_CNC,
    MACHINE_LUCIDATRICE,
    MACHINE_MULTIFILO,
    get_machine,
    load_machines,
    save_machine,
)
from ui.common.plc_db_live_dialog import PlcDbLiveDialog

# Console governance AI (sola lettura su autonomy_audit + policy)
try:
    from modules.action_store import (
        audit_stats_for_action_prefix,
        list_audit_for_action_prefix,
    )
    from core.autonomy_policy import get_policy
    from plc.plc_write_governor import map_is_placeholder
    from core.governance_schemas import build_map_contract_report
    GOVERNANCE_AVAILABLE = True
except ImportError:
    GOVERNANCE_AVAILABLE = False
    print("⚠ Console governance non disponibile (moduli mancanti)")

_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$"
)


# NOTE: Le classi PingWorker e PLCWorker sono disponibili per future implementazioni
# ma NON vengono utilizzate nella versione attuale (ping sincrono senza thread persistenti)
class PingWorker(QThread):
    """Worker thread per verificare la raggiungibilità di una macchina via socket (non utilizzato nella versione attuale)"""
    ping_result = pyqtSignal(str, bool, str)  # nome, stato, timestamp
    
    def __init__(self, nome, ip, porta=502):
        super().__init__()
        self.nome = nome
        self.ip = ip
        self.porta = porta
        self.running = True
    
    def stop(self):
        """Ferma il thread in modo sicuro"""
        self.running = False
    
    def run(self):
        """Esegue il controllo ping via socket"""
        if not self.running:
            return
        
        try:
            # Crea socket TCP
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)  # Timeout 2 secondi
            
            if not self.running:
                sock.close()
                return
            
            # Tenta connessione alla porta PLC
            result = sock.connect_ex((self.ip, self.porta))
            sock.close()
            
            if not self.running:
                return
            
            # Se result == 0, la connessione è riuscita
            stato = (result == 0)
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            if self.running:
                self.ping_result.emit(self.nome, stato, timestamp)
            
        except Exception as e:
            # In caso di errore, considera non raggiungibile
            if self.running:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.ping_result.emit(self.nome, False, timestamp)


class PLCWorker(QThread):
    """Worker thread per verificare lo stato PLC (tentativo connessione) (non utilizzato nella versione attuale)"""
    plc_result = pyqtSignal(str, bool, str)  # nome, stato, timestamp
    
    def __init__(self, nome, ip, porta=502):
        super().__init__()
        self.nome = nome
        self.ip = ip
        self.porta = porta
        self.running = True
    
    def stop(self):
        """Ferma il thread in modo sicuro"""
        self.running = False
    
    def run(self):
        """Esegue il controllo stato PLC via socket"""
        if not self.running:
            return
        
        try:
            # Crea socket TCP
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)  # Timeout più breve per PLC
            
            if not self.running:
                sock.close()
                return
            
            # Tenta connessione
            result = sock.connect_ex((self.ip, self.porta))
            
            if not self.running:
                if result == 0:
                    sock.close()
                return
            
            if result == 0:
                # Connessione riuscita, chiudi immediatamente
                sock.close()
                stato = True
            else:
                stato = False
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            if self.running:
                self.plc_result.emit(self.nome, stato, timestamp)
            
        except Exception as e:
            # In caso di errore, considera PLC non disponibile
            if self.running:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.plc_result.emit(self.nome, False, timestamp)


class MachinesMonitoringWindow(SectionMainWindow):
    """
    Finestra per monitoraggio della rete e delle macchine
    Monitora connessioni PLC, ping, pacchetti di rete
    """

    COL_PING = 5
    COL_SAVE = 6
    COL_DB = 7
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔌 Machines Monitoring")
        
        self._loading_table = False
        self.macchine = self._build_macchine_list()
        
        # Liste per tracciare workers e timers (per chiusura sicura)
        self.workers = []
        self.timers = []
        
        # Flag per indicare se la finestra è in fase di chiusura
        self.is_closing = False
        
        # Imposta finestra in modalità schermo intero senza bordi né decorazioni
        self.setup_fullscreen_window()
        
        # Inizializza UI
        self.init_ui()
        self.apply_stylesheet()
        
        # Popola la tabella con le macchine
        self.populate_table()
        
        # Popola la console governance e la tiene aggiornata
        if GOVERNANCE_AVAILABLE:
            self.refresh_governance()
            gov_timer = QTimer(self)
            gov_timer.timeout.connect(self.refresh_governance)
            gov_timer.start(30000)
            self.timers.append(gov_timer)
        
        # Esegue un singolo ping automatico iniziale
        self.ping_automatico_iniziale()

    def _build_macchine_list(self):
        """Elenco macchine da config.json (Snap7): Multifilo, Lucidatrice, CNC."""
        cfg = load_machines()
        mf = cfg[MACHINE_MULTIFILO]
        lu = cfg[MACHINE_LUCIDATRICE]
        cnc = cfg[MACHINE_CNC]
        return [
            {
                "nome": "Multiwire",
                "machine_id": MACHINE_MULTIFILO,
                "ip": mf["ip"],
                "porta": mf["port"],
            },
            {
                "nome": "Polisher",
                "machine_id": MACHINE_LUCIDATRICE,
                "ip": lu["ip"],
                "porta": lu["port"],
            },
            {
                "nome": "CNC",
                "machine_id": MACHINE_CNC,
                "ip": cnc["ip"],
                "porta": cnc["port"],
            },
        ]

    @staticmethod
    def _is_valid_ipv4(ip: str) -> bool:
        return bool(_IPV4_RE.match(ip.strip()))

    def _machine_row(self, nome: str):
        for i, m in enumerate(self.macchine):
            if m["nome"] == nome:
                return i, m
        return None, None

    def _read_ip_from_table(self, row: int) -> str:
        item = self.machines_table.item(row, 1)
        if item is None:
            return self.macchine[row]["ip"]
        text = item.text().strip()
        if ":" in text:
            text = text.split(":", 1)[0].strip()
        return text or self.macchine[row]["ip"]

    def _sync_macchina_from_row(self, row: int) -> None:
        if row < 0 or row >= len(self.macchine):
            return
        ip = self._read_ip_from_table(row)
        if self._is_valid_ipv4(ip):
            self.macchine[row]["ip"] = ip

    def _macchina_for_ping(self, nome: str):
        row, macchina = self._machine_row(nome)
        if macchina is None:
            return None
        self._sync_macchina_from_row(row)
        return dict(macchina)

    def _on_ip_cell_changed(self, row: int, column: int) -> None:
        if self._loading_table or column != 1:
            return
        if row < 0 or row >= len(self.macchine):
            return

        nome = self.macchine[row]["nome"]
        ip = self._read_ip_from_table(row)
        item = self.machines_table.item(row, 1)

        if not self._is_valid_ipv4(ip):
            if item is not None:
                item.setForeground(QColor("#FF6B6B"))
            self.append_log(f"{nome}: invalid IP ({ip!r}) — use format e.g. 192.168.10.20")
            return

        self.macchine[row]["ip"] = ip
        if item is not None:
            item.setText(ip)
            item.setForeground(QColor("#FFFFFF"))
            item.setToolTip(
                f"TCP port: {self.macchine[row]['porta']} — "
                "double-click to edit address"
            )
        self.append_log(f"{nome}: IP updated in table → {ip}")

    def _action_button_style(self, accent: str = "purple") -> str:
        if accent == "green":
            bg, border, hover_bg, hover_border, pressed = (
                "#2a4a3a", "#4a6a5a", "#3a5a4a", "#5a7a6a", "#1a3a2a"
            )
        elif accent == "blue":
            bg, border, hover_bg, hover_border, pressed = (
                "#1a3a5a", "#3a5a7a", "#2a4a6a", "#4a6a8a", "#0a2a4a"
            )
        else:
            bg, border, hover_bg, hover_border, pressed = (
                "#3a2a4a", "#5a4a6a", "#4a3a5a", "#6a5a7a", "#2a1a3a"
            )
        return f"""
            QPushButton {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border: 1px solid {hover_border};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
            QPushButton:disabled {{
                background-color: #2a2a3a;
                border: 1px solid #3a3a4a;
                color: #666666;
            }}
        """

    def save_macchina_config(self, nome: str) -> None:
        """Salva IP (e porta nota) della macchina in config.json."""
        row, macchina = self._machine_row(nome)
        if macchina is None:
            self.append_log(f"Error: machine '{nome}' not found")
            return

        machine_id = macchina.get("machine_id")
        if not machine_id:
            self.append_log(f"{nome}: config save not available for this machine")
            return

        self._sync_macchina_from_row(row)
        ip = macchina["ip"]
        if not self._is_valid_ipv4(ip):
            self.append_log(f"{nome}: cannot save — invalid IP ({ip!r})")
            return

        try:
            path = save_machine(
                machine_id,
                {"ip": ip, "port": macchina["porta"]},
            )
            self.append_log(
                f"{nome}: config saved → {ip}:{macchina['porta']} ({path})"
            )
        except (ValueError, OSError) as e:
            self.append_log(f"{nome}: config save error — {e}")

    def _create_button_cell(self, button: QPushButton) -> QWidget:
        """Pulsante a piena cella: riempie larghezza e altezza disponibili."""
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        button.setMinimumSize(0, 0)
        layout.addWidget(button)
        return container

    def _create_ping_button(self, macchina: dict) -> QWidget:
        ping_button = QPushButton("Ping")
        ping_button.setStyleSheet(self._action_button_style("purple"))
        ping_button.setToolTip(f"TCP network test on {macchina['nome']}")
        ping_button.clicked.connect(
            lambda checked, nome=macchina["nome"]: self.ping_singola_macchina(nome)
        )
        return self._create_button_cell(ping_button)

    def _create_save_button(self, macchina: dict) -> QWidget:
        save_button = QPushButton("Save")
        save_button.setStyleSheet(self._action_button_style("green"))
        if macchina.get("machine_id"):
            save_button.setToolTip(
                f"Save IP to config.json for {macchina['nome']}"
            )
            save_button.clicked.connect(
                lambda checked, nome=macchina["nome"]: self.save_macchina_config(nome)
            )
        else:
            save_button.setEnabled(False)
            save_button.setToolTip("Config save not available for this machine")
        return self._create_button_cell(save_button)

    def _create_db_button(self, macchina: dict) -> QWidget:
        db_button = QPushButton("DB")
        db_button.setStyleSheet(self._action_button_style("blue"))
        machine_id = macchina.get("machine_id")
        if machine_id:
            db_button.setToolTip(
                f"Open live DB1/DB2 diagnostics for {macchina['nome']} "
                f"(IP in table or saved config)"
            )
            db_button.clicked.connect(
                lambda checked, nome=macchina["nome"]: self.open_plc_db_live(nome)
            )
        else:
            db_button.setEnabled(False)
            db_button.setToolTip("Live DB not available for this machine")
        return self._create_button_cell(db_button)

    def open_plc_db_live(self, nome: str) -> None:
        """Apre finestra modale lettura DB Snap7 (Multifilo, Lucidatrice, CNC)."""
        row, macchina = self._machine_row(nome)
        if macchina is None:
            return
        machine_id = macchina.get("machine_id")
        if not machine_id:
            QMessageBox.information(
                self,
                "Live DB",
                "DB diagnostics are not available for this machine.",
            )
            return

        self._sync_macchina_from_row(row)
        cfg = get_machine(machine_id)
        ip = macchina["ip"]
        if self._is_valid_ipv4(ip):
            plc_settings = {**cfg, "ip": ip}
            if ip.startswith("130.0.0."):
                QMessageBox.warning(
                    self,
                    "Live DB — check IP",
                    f"You are using {ip}.\n\n"
                    "For local Snap7 simulation you usually need "
                    "127.0.0.1 (not 130.0.0.1).\n\n"
                    "Fix IP in the table and press Save, or close and retry.",
                )
        else:
            plc_settings = cfg
            QMessageBox.warning(
                self,
                "Live DB",
                f"Invalid IP in table; using saved config ({cfg['ip']}).",
            )

        profile = plc_settings.get("map_profile", "sim_v1")
        self.append_log(
            f"{nome}: DB live fullscreen → {plc_settings['ip']}:{plc_settings['port']} "
            f"map {profile}"
        )

        loading = QDialog(self)
        loading.setWindowTitle("DB live")
        loading.setStyleSheet(
            "QDialog { background-color: #0a0a15; color: #e8e8f0; }"
            "QLabel { color: #e8e8f0; font-size: 13px; }"
        )
        loading.setFixedSize(380, 96)
        loading_lay = QVBoxLayout(loading)
        loading_lbl = QLabel(f"Loading PLC diagnostics for {macchina['nome']}…")
        loading_lbl.setAlignment(Qt.AlignCenter)
        loading_lay.addWidget(loading_lbl)
        loading.show()
        QApplication.processEvents()

        try:
            dialog = PlcDbLiveDialog(
                machine_id=machine_id,
                machine_name=macchina["nome"],
                plc_settings=plc_settings,
                parent=self,
            )
        finally:
            loading.close()

        show_auxiliary_window(dialog)

    def _configure_machines_table_layout(self) -> None:
        """Tutte le colonne in Stretch; Ping/Save riempiono la cella."""
        table = self.machines_table
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.setWordWrap(False)

        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setMinimumSectionSize(80)
        for col in range(table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Stretch)

        vheader = table.verticalHeader()
        vheader.setDefaultSectionSize(48)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QHeaderView.Stretch)

    def _finalize_machines_table_layout(self) -> None:
        """Dopo il popolamento: stretch uniforme su colonne e righe."""
        table = self.machines_table
        header = table.horizontalHeader()
        for col in range(table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        header.setStretchLastSection(False)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def setup_fullscreen_window(self):
        """Finestra indipendente con barra titolo e riduzione a icona."""
        from ui.common.window_helpers import apply_machine_section_window

        apply_machine_section_window(self)
    
    def init_ui(self):
        """Inizializza l'interfaccia utente con scroll verticale completo"""
        # ============================================================
        # CREAZIONE SCROLL AREA PER TUTTA LA SEZIONE
        # ============================================================
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
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
                background-color: #4a3a5a;
                min-height: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5a4a6a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Container per tutto il contenuto (scrollabile)
        container_widget = QWidget()
        container_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        container_layout = QVBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Header (dentro lo scroll)
        header = self.create_header()
        container_layout.addWidget(header)
        
        # Widget per il contenuto principale
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 15, 15, 15)
        content_layout.setSpacing(15)
        
        # Contenuto della sezione (pulsanti, tabella, log)
        self.create_content(content_layout)
        
        container_layout.addWidget(content_widget)
        
        # Footer/Status bar (dentro lo scroll)
        status_bar_widget = self.create_status_bar()
        container_layout.addWidget(status_bar_widget)
        
        # Imposta il container nella scroll area
        scroll_area.setWidget(container_widget)
        
        # Imposta la scroll area come widget centrale
        self.setCentralWidget(scroll_area)
        
        # Salva riferimento per accesso futuro
        self.scroll_area = scroll_area
        self.container_widget = container_widget
    
    def create_header(self):
        """Crea l'header unificato della finestra"""
        header_widget = QWidget()
        header_widget.setFixedHeight(50)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(15)
        
        # Pulsante Dashboard a sinistra
        self.pulsante_dashboard = QPushButton("Dashboard")
        self.pulsante_dashboard.setFixedHeight(32)
        self.pulsante_dashboard.setStyleSheet("""
            QPushButton {
                background-color: #3a2a4a;
                border: 1px solid #5a4a6a;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: bold;
                padding: 6px 15px;
            }
            QPushButton:hover {
                background-color: #4a3a5a;
                border: 1px solid #6a5a7a;
            }
            QPushButton:pressed {
                background-color: #2a1a3a;
            }
        """)
        self.pulsante_dashboard.setToolTip("Return to main window")
        self.pulsante_dashboard.clicked.connect(self.tornaAllaDashboard)
        header_layout.addWidget(self.pulsante_dashboard)
        
        # Titolo sezione a destra del pulsante
        titolo_sezione = QLabel("🔌 Machines Monitoring")
        titolo_sezione.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(titolo_sezione)
        
        # Spazio flessibile per spingere tutto a sinistra
        header_layout.addStretch()
        
        return header_widget
    
    def create_content(self, main_layout):
        """Crea il contenuto principale della sezione"""
        # Sezione: Lista IP delle macchine
        machines_group = QGroupBox("Monitored Machines")
        machines_layout = QVBoxLayout(machines_group)
        machines_layout.setContentsMargins(15, 15, 15, 15)
        machines_layout.setSpacing(10)
        
        # Layout orizzontale per pulsante ping manuale
        ping_button_layout = QHBoxLayout()
        ping_button_layout.addStretch()
        
        # Pulsante Ping Manuale
        self.btn_ping_manual = QPushButton("Manual Ping")
        self.btn_ping_manual.setFixedHeight(35)
        self.btn_ping_manual.setStyleSheet("""
            QPushButton {
                background-color: #3a2a4a;
                border: 1px solid #5a4a6a;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #4a3a5a;
                border: 1px solid #6a5a7a;
            }
            QPushButton:pressed {
                background-color: #2a1a3a;
            }
        """)
        self.btn_ping_manual.setToolTip("Run an immediate ping on all machines")
        self.btn_ping_manual.clicked.connect(self.ping_manual)
        ping_button_layout.addWidget(self.btn_ping_manual)
        
        machines_layout.addLayout(ping_button_layout)
        
        # Tabella macchine
        self.machines_table = QTableWidget()
        self.machines_table.setColumnCount(8)
        self.machines_table.setHorizontalHeaderLabels([
            "Machine", "IP Address", "Ping Status", "PLC Status",
            "Last Packet", "Ping", "Save", "DB",
        ])
        self.machines_table.setRowCount(0)
        self.machines_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #4a4a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 8px;
                border: 1px solid #3a3a4a;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        self._configure_machines_table_layout()
        self.machines_table.setAlternatingRowColors(True)
        self.machines_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.machines_table.cellChanged.connect(self._on_ip_cell_changed)
        machines_layout.addWidget(self.machines_table, 1)
        
        main_layout.addWidget(machines_group, 1)
        
        # Sezione: Console governance AI (sola lettura)
        if GOVERNANCE_AVAILABLE:
            main_layout.addWidget(self.create_governance_group(), 1)
        
        # Sezione: Log di rete
        log_group = QGroupBox("Network Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(15, 15, 15, 15)
        log_layout.setSpacing(10)
        
        self.network_log = QTextEdit()
        self.network_log.setReadOnly(True)
        self.network_log.setPlaceholderText("Network logs will appear here...")
        self.network_log.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #00FF00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 10px;
            }
        """)
        self.network_log.setMinimumHeight(200)
        log_layout.addWidget(self.network_log, 1)
        
        main_layout.addWidget(log_group, 1)
    
    def create_governance_group(self):
        """
        Console governance AI (SOLA LETTURA).
        Mostra: modalità canale scrittura, livello autonomia, kill switch,
        stato mappa, statistiche shadow e le ultime decisioni del governor.
        Nessun controllo da qui: si osserva, non si comanda.
        """
        group = QGroupBox("🛡️ AI Governance — deterministic write channel")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Riga badge di stato
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(10)
        
        def make_badge(text, color):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"background-color: #0a0a1a; border: 1px solid {color}; "
                f"border-radius: 4px; color: {color}; padding: 6px 10px; "
                "font-size: 12px; font-weight: bold;"
            )
            return lbl
        
        self.gov_mode_badge = make_badge("WRITE CHANNEL: —", "#FFD93D")
        self.gov_autonomy_badge = make_badge("AUTONOMY: —", "#8be9fd")
        self.gov_kill_badge = make_badge("KILL SWITCH: —", "#51CF66")
        self.gov_map_badge = make_badge("OEM MAP: —", "#FFD93D")
        for badge in (self.gov_mode_badge, self.gov_autonomy_badge,
                      self.gov_kill_badge, self.gov_map_badge):
            badges_layout.addWidget(badge)
        badges_layout.addStretch()
        
        self.gov_refresh_btn = QPushButton("Refresh")
        self.gov_refresh_btn.setFixedHeight(30)
        self.gov_refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a2a4a;
                border: 1px solid #5a4a6a;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 15px;
            }
            QPushButton:hover { background-color: #4a3a5a; }
            QPushButton:pressed { background-color: #2a1a3a; }
        """)
        self.gov_refresh_btn.clicked.connect(self.refresh_governance)
        badges_layout.addWidget(self.gov_refresh_btn)
        layout.addLayout(badges_layout)

        # Salute dei contratti dati (Pydantic + regole mappa), separata dai
        # badge operativi per non affollare la riga superiore.
        contracts_layout = QHBoxLayout()
        contracts_layout.setSpacing(10)
        self.gov_contract_badge = make_badge("DATA CONTRACTS: —", "#8be9fd")
        contracts_layout.addWidget(self.gov_contract_badge)
        self.gov_contract_summary = QLabel("—")
        self.gov_contract_summary.setStyleSheet(
            "color: #8a8a9a; font-size: 12px; padding: 2px;"
        )
        contracts_layout.addWidget(self.gov_contract_summary, 1)
        self.gov_contract_details_btn = QPushButton("View validation details")
        self.gov_contract_details_btn.setFixedHeight(30)
        self.gov_contract_details_btn.setStyleSheet("""
            QPushButton {
                background-color: #243447;
                border: 1px solid #406080;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 12px;
            }
            QPushButton:hover { background-color: #304860; }
            QPushButton:pressed { background-color: #182838; }
        """)
        self.gov_contract_details_btn.clicked.connect(
            self.show_contract_validation_details
        )
        contracts_layout.addWidget(self.gov_contract_details_btn)
        layout.addLayout(contracts_layout)
        
        # Statistiche shadow
        self.gov_stats_label = QLabel("—")
        self.gov_stats_label.setStyleSheet(
            "color: #8a8a9a; font-size: 12px; padding: 2px;"
        )
        layout.addWidget(self.gov_stats_label)
        
        # Tabella decisioni recenti
        self.gov_table = QTableWidget()
        self.gov_table.setColumnCount(5)
        self.gov_table.setHorizontalHeaderLabels(
            ["Time", "Type", "Source", "Verdict", "Reason"]
        )
        self.gov_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.gov_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.gov_table.setAlternatingRowColors(True)
        self.gov_table.setMinimumHeight(220)
        self.gov_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
                font-size: 11px;
            }
            QTableWidget::item { padding: 6px; border: none; }
            QTableWidget::item:selected { background-color: #4a4a6a; }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 6px;
                border: 1px solid #3a3a4a;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        header = self.gov_table.horizontalHeader()
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.gov_table, 1)
        
        return group
    
    def refresh_governance(self):
        """Rilegge policy, stato mappa e audit (sola lettura, mai bloccante)."""
        if not GOVERNANCE_AVAILABLE or not hasattr(self, 'gov_table'):
            return
        
        # Badge canale scrittura: SHADOW è l'unico stato possibile da codice
        # (l'enforce non esiste finché non lo si abilita consapevolmente).
        self.gov_mode_badge.setText("WRITE CHANNEL: SHADOW — no real writes")
        self.gov_mode_badge.setStyleSheet(
            "background-color: #0a0a1a; border: 1px solid #FFD93D; "
            "border-radius: 4px; color: #FFD93D; padding: 6px 10px; "
            "font-size: 12px; font-weight: bold;"
        )
        
        # Policy autonomia + kill switch
        try:
            policy = get_policy()
            policy.reload()
            self.gov_autonomy_badge.setText(f"AUTONOMY: {policy.banner_text()}")
            paused = bool(policy.settings["autonomy"].get("agents_paused"))
            if paused:
                self.gov_kill_badge.setText("KILL SWITCH: ACTIVE")
                kill_color = "#FF6B6B"
            else:
                self.gov_kill_badge.setText("KILL SWITCH: off")
                kill_color = "#51CF66"
            self.gov_kill_badge.setStyleSheet(
                f"background-color: #0a0a1a; border: 1px solid {kill_color}; "
                f"border-radius: 4px; color: {kill_color}; padding: 6px 10px; "
                "font-size: 12px; font-weight: bold;"
            )
        except Exception as e:
            self.gov_autonomy_badge.setText(f"AUTONOMY: errore lettura ({e})")
        
        # Stato mappa OEM: placeholder = scritture impossibili per definizione
        try:
            if map_is_placeholder("oem_cnc_v1"):
                self.gov_map_badge.setText("OEM MAP: placeholder — writes blocked")
                map_color = "#FFD93D"
            else:
                self.gov_map_badge.setText("OEM MAP: commissioned")
                map_color = "#51CF66"
            self.gov_map_badge.setStyleSheet(
                f"background-color: #0a0a1a; border: 1px solid {map_color}; "
                f"border-radius: 4px; color: {map_color}; padding: 6px 10px; "
                "font-size: 12px; font-weight: bold;"
            )
        except Exception:
            self.gov_map_badge.setText("OEM MAP: n/d")

        # Contratti dati: forma della mappa/whitelist validata da Pydantic.
        try:
            report = build_map_contract_report("oem_cnc_v1")
            self._contract_report = report
            valid = bool(report.get("valid"))
            placeholder = bool(report.get("placeholder"))
            if not valid:
                contract_text = "DATA CONTRACTS: INVALID"
                contract_color = "#FF6B6B"
            elif placeholder:
                contract_text = "DATA CONTRACTS: VALID (placeholder)"
                contract_color = "#FFD93D"
            else:
                contract_text = "DATA CONTRACTS: VALID"
                contract_color = "#51CF66"
            self.gov_contract_badge.setText(contract_text)
            self.gov_contract_badge.setStyleSheet(
                f"background-color: #0a0a1a; border: 1px solid {contract_color}; "
                f"border-radius: 4px; color: {contract_color}; padding: 6px 10px; "
                "font-size: 12px; font-weight: bold;"
            )
            total = int(report.get("writable_total", 0))
            valid_count = int(report.get("writable_valid", 0))
            excluded = int(report.get("writable_excluded", 0))
            version = report.get("version") or "?"
            protocol = report.get("override_protocol") or {}
            protocol_version = protocol.get("version") or "n/d"
            live_transport = bool(protocol.get("live_transport_implemented"))
            checked_at = datetime.now().strftime("%H:%M:%S")
            self.gov_contract_summary.setText(
                f"Governance schema v1 · map v{version} · "
                f"writable variables {valid_count}/{total} valid"
                f"{f' · {excluded} excluded fail-closed' if excluded else ''} · "
                f"override {protocol_version} · "
                f"live {'enabled' if live_transport else 'disabled'} · "
                f"checked {checked_at}"
            )
        except Exception as e:
            self._contract_report = {
                "valid": False,
                "errors": [{"db": None, "variable": "", "message": str(e)}],
            }
            self.gov_contract_badge.setText("DATA CONTRACTS: ERROR")
            self.gov_contract_summary.setText(f"Validation unavailable: {e}")
        
        # Statistiche e tabella decisioni
        try:
            stats = audit_stats_for_action_prefix("plc_write")
            proposals = audit_stats_for_action_prefix("plc_write_proposal")
            executions = {
                "total": stats["total"] - proposals["total"],
                "allowed": stats["allowed"] - proposals["allowed"],
            }
            self.gov_stats_label.setText(
                f"Shadow history — proposals: {proposals['total']} "
                f"({proposals['allowed']} valid, {proposals['rejected']} rejected) · "
                f"operator approvals: {executions['allowed']} · "
                "all decisions audited, zero bytes written to any PLC"
            )
            
            rows = list_audit_for_action_prefix("plc_write", limit=50)
            self.gov_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                ts = str(row.get("ts", ""))
                try:
                    dt = datetime.fromisoformat(ts).astimezone()
                    ts_text = dt.strftime("%d/%m %H:%M:%S")
                except ValueError:
                    ts_text = ts[:19]
                action = str(row.get("action", ""))
                type_text = (
                    "proposal" if action == "plc_write_proposal"
                    else "write decision"
                )
                allowed = bool(row.get("allowed"))
                verdict_item = QTableWidgetItem(
                    "ALLOWED" if allowed else "REJECTED"
                )
                verdict_item.setForeground(
                    QColor("#51CF66") if allowed else QColor("#FF6B6B")
                )
                
                self.gov_table.setItem(i, 0, QTableWidgetItem(ts_text))
                self.gov_table.setItem(i, 1, QTableWidgetItem(type_text))
                self.gov_table.setItem(
                    i, 2, QTableWidgetItem(str(row.get("agent") or "—"))
                )
                self.gov_table.setItem(i, 3, verdict_item)
                self.gov_table.setItem(
                    i, 4, QTableWidgetItem(str(row.get("reason") or ""))
                )
        except Exception as e:
            self.gov_stats_label.setText(f"Audit non leggibile: {e}")

    def show_contract_validation_details(self):
        """Dettagli tecnici, sola lettura, dell'ultima validazione mappa."""
        report = getattr(self, "_contract_report", None)
        if not report:
            self.refresh_governance()
            report = getattr(self, "_contract_report", {})

        dialog = QDialog(self)
        dialog.setWindowTitle("Data Contract Validation — OEM CNC")
        dialog.resize(760, 520)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        status = "VALID" if report.get("valid") else "INVALID"
        if report.get("valid") and report.get("placeholder"):
            status += " — PLACEHOLDER (real writes remain blocked)"
        summary = QLabel(
            f"Status: {status}\n"
            f"Profile: {report.get('profile_id', 'oem_cnc_v1')} · "
            f"schema: {report.get('schema') or 'n/d'} · "
            f"version: {report.get('version') or 'n/d'}\n"
            f"Writable variables: {report.get('writable_valid', 0)} valid / "
            f"{report.get('writable_total', 0)} declared / "
            f"{report.get('writable_excluded', 0)} excluded fail-closed"
        )
        summary.setWordWrap(True)
        summary.setStyleSheet(
            "color: #FFFFFF; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(summary)

        details = QTextEdit()
        details.setReadOnly(True)
        errors = report.get("errors") or []
        if errors:
            lines = ["VALIDATION ERRORS:"]
            for error in errors:
                db = error.get("db")
                variable = error.get("variable") or "—"
                location = f"DB{db}" if db is not None else "MAP"
                lines.append(
                    f"❌ {location} · {variable}: {error.get('message', '')}"
                )
        else:
            protocol = report.get("override_protocol") or {}
            lines = [
                "✅ No structural contract errors detected.",
                "",
                "SMALL OVERRIDE PROTOCOL:",
                f"• version: {protocol.get('version') or 'n/d'}",
                f"• allowed variables: {protocol.get('allowed_variables') or []}",
                f"• request DB / ack DB: "
                f"{protocol.get('request_db', 'n/d')} / "
                f"{protocol.get('ack_db', 'n/d')}",
                f"• read-back required: "
                f"{bool(protocol.get('readback_required'))}",
                f"• LIVE transport implemented: "
                f"{bool(protocol.get('live_transport_implemented'))}",
                "",
                "Validated rules:",
                "• writable variables only in sw_to_plc blocks",
                "• supported PLC types: BOOL, BYTE, INT, REAL",
                "• non-negative offsets and cooldowns",
                "• min ≤ max",
                "• min_delta ≤ max_step",
                "• no duplicate writable offsets within a DB",
                "",
                "NOTE: structural validity does not certify OEM offsets or limits. "
                "The OEM map is still a commissioning placeholder, therefore the "
                "governor blocks all real writes.",
            ]
        details.setPlainText("\n".join(lines))
        details.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 10px;
            }
        """)
        layout.addWidget(details, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(dialog.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)
        dialog.exec_()
    
    def populate_table(self):
        """Popola la tabella con le macchine configurate"""
        self._loading_table = True
        self.machines_table.setRowCount(len(self.macchine))
        
        for row, macchina in enumerate(self.macchine):
            # Nome Macchina
            nome_item = QTableWidgetItem(macchina["nome"])
            nome_item.setFlags(nome_item.flags() & ~Qt.ItemIsEditable)
            nome_item.setTextAlignment(Qt.AlignCenter)
            self.machines_table.setItem(row, 0, nome_item)
            
            # IP Address — modificabile (doppio clic / F2 / clic sulla cella selezionata)
            ip_item = QTableWidgetItem(macchina["ip"])
            ip_item.setFlags(ip_item.flags() | Qt.ItemIsEditable)
            ip_item.setTextAlignment(Qt.AlignCenter)
            ip_item.setToolTip(
                f"TCP port: {macchina['porta']} — double-click to edit IP address"
            )
            ip_item.setBackground(QColor("#1a2438"))
            self.machines_table.setItem(row, 1, ip_item)
            
            # Stato Ping (inizialmente "In attesa...")
            ping_item = QTableWidgetItem("Waiting...")
            ping_item.setFlags(ping_item.flags() & ~Qt.ItemIsEditable)
            ping_item.setTextAlignment(Qt.AlignCenter)
            ping_item.setForeground(QColor("#FFD93D"))  # Giallo
            self.machines_table.setItem(row, 2, ping_item)
            
            # Stato PLC (inizialmente "In attesa...")
            plc_item = QTableWidgetItem("Waiting...")
            plc_item.setFlags(plc_item.flags() & ~Qt.ItemIsEditable)
            plc_item.setTextAlignment(Qt.AlignCenter)
            plc_item.setForeground(QColor("#FFD93D"))  # Giallo
            self.machines_table.setItem(row, 3, plc_item)
            
            # Ultimo Pacchetto (inizialmente vuoto)
            timestamp_item = QTableWidgetItem("--")
            timestamp_item.setFlags(timestamp_item.flags() & ~Qt.ItemIsEditable)
            timestamp_item.setTextAlignment(Qt.AlignCenter)
            self.machines_table.setItem(row, 4, timestamp_item)
            
            # Colonne Ping e Save (larghezza fissa, pulsanti centrati)
            self.machines_table.setCellWidget(
                row, self.COL_PING, self._create_ping_button(macchina)
            )
            self.machines_table.setCellWidget(
                row, self.COL_SAVE, self._create_save_button(macchina)
            )
            self.machines_table.setCellWidget(
                row, self.COL_DB, self._create_db_button(macchina)
            )

        self._loading_table = False
        self._finalize_machines_table_layout()
        
        # Aggiorna contatore macchine
        self.machines_count_label.setText(f"Machines: {len(self.macchine)}")
    
    def ping_automatico_iniziale(self):
        """Esegue un singolo ping automatico all'apertura della finestra"""
        # Verifica che la finestra esista ancora
        if not hasattr(self, 'machines_table') or self.machines_table is None:
            return
        
        # Scrivi nel log
        self.append_log("Running initial automatic ping...")
        
        # Esegui ping per ogni macchina (senza thread, immediato)
        from PyQt5.QtWidgets import QApplication
        for macchina in self.macchine:
            m = self._macchina_for_ping(macchina["nome"])
            if m:
                self.ping_single_machine(m, automatico=True)
            # Processa eventi UI per evitare blocchi
            QApplication.processEvents()
        
        # Scrivi nel log
        self.append_log("Initial automatic ping completed.")
    
    def update_ping_status(self, nome, stato, timestamp):
        """Aggiorna lo stato ping nella tabella (thread-safe)"""
        # Verifica che la finestra esista ancora
        if not hasattr(self, 'machines_table') or self.machines_table is None:
            return
        
        try:
            # Trova la riga della macchina
            row = None
            for i, macchina in enumerate(self.macchine):
                if macchina["nome"] == nome:
                    row = i
                    break
            
            if row is None:
                return
            
            # Aggiorna cella "Stato Ping"
            if self.machines_table.item(row, 2) is not None:
                ping_item = self.machines_table.item(row, 2)
                if stato:
                    ping_item.setText("✓ Reachable")
                    ping_item.setForeground(QColor("#51CF66"))  # Verde
                else:
                    ping_item.setText("✗ Unreachable")
                    ping_item.setForeground(QColor("#FF6B6B"))  # Rosso
            
            # Aggiorna timestamp
            if self.machines_table.item(row, 4) is not None:
                timestamp_item = self.machines_table.item(row, 4)
                timestamp_item.setText(timestamp)
            
            # Scrivi nel log
            if hasattr(self, 'network_log') and self.network_log is not None:
                stato_text = "reachable" if stato else "unreachable"
                self.append_log(f"[{timestamp}] {nome}: Ping {stato_text}")
        except Exception as e:
            # Ignora errori se la finestra è stata distrutta
            pass
    
    def update_plc_status(self, nome, stato, timestamp):
        """Aggiorna lo stato PLC nella tabella (thread-safe)"""
        # Verifica che la finestra esista ancora
        if not hasattr(self, 'machines_table') or self.machines_table is None:
            return
        
        try:
            # Trova la riga della macchina
            row = None
            for i, macchina in enumerate(self.macchine):
                if macchina["nome"] == nome:
                    row = i
                    break
            
            if row is None:
                return
            
            # Aggiorna cella "Stato PLC"
            if self.machines_table.item(row, 3) is not None:
                plc_item = self.machines_table.item(row, 3)
                if stato:
                    plc_item.setText("✓ Connected")
                    plc_item.setForeground(QColor("#51CF66"))  # Verde
                else:
                    plc_item.setText("✗ Not connected")
                    plc_item.setForeground(QColor("#FF6B6B"))  # Rosso
            
            # Scrivi nel log
            if hasattr(self, 'network_log') and self.network_log is not None:
                stato_text = "connected" if stato else "not connected"
                self.append_log(f"[{timestamp}] {nome}: PLC {stato_text}")
        except Exception as e:
            # Ignora errori se la finestra è stata distrutta
            pass
    
    def append_log(self, testo):
        """Aggiunge testo al log con timestamp e scroll automatico"""
        # Verifica che il log esista ancora
        if not hasattr(self, 'network_log') or self.network_log is None:
            return
        
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {testo}\n"
            
            self.network_log.append(log_entry)
            
            # Scroll automatico alla fine
            scrollbar = self.network_log.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            # Ignora errori se la finestra è stata distrutta
            pass
    
    def ping_manual(self):
        """Esegue un ping manuale immediato su tutte le macchine"""
        # Verifica che la finestra esista ancora
        if not hasattr(self, 'machines_table') or self.machines_table is None:
            return
        
        # Disabilita il pulsante durante l'esecuzione
        self.btn_ping_manual.setEnabled(False)
        self.btn_ping_manual.setText("Pinging...")
        
        # Scrivi nel log
        self.append_log("Running manual ping...")
        
        # Esegui ping per ogni macchina (manuale, non automatico)
        from PyQt5.QtWidgets import QApplication
        for macchina in self.macchine:
            m = self._macchina_for_ping(macchina["nome"])
            if m:
                self.ping_single_machine(m, automatico=False)
            # Processa eventi UI per evitare blocchi
            QApplication.processEvents()
        
        # Riabilita il pulsante
        self.btn_ping_manual.setEnabled(True)
        self.btn_ping_manual.setText("Manual Ping")
        
        # Scrivi nel log
        self.append_log("Manual ping completed.")
    
    def ping_singola_macchina(self, nome):
        """Esegue un ping su una singola macchina identificata per nome"""
        macchina = self._macchina_for_ping(nome)
        
        if macchina is None:
            self.append_log(f"Error: machine '{nome}' not found")
            return
        
        # Esegue il ping (non automatico, quindi manuale)
        self.ping_single_machine(macchina, automatico=False)
        self.append_log(f"Single ping → {nome}: done")
    
    def ping_single_machine(self, macchina, automatico=False):
        """Esegue un ping sicuro su una singola macchina (senza thread)"""
        nome = macchina["nome"]
        ip = macchina["ip"]
        porta = macchina["porta"]
        
        try:
            # Crea socket TCP con timeout breve
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)  # Timeout 300ms per ping veloce
            
            # Tenta connessione alla porta PLC
            result = sock.connect_ex((ip, porta))
            sock.close()
            
            # Se result == 0, la connessione è riuscita
            stato = (result == 0)
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Aggiorna tabella
            self.update_ping_status(nome, stato, timestamp)
            
            # Scrivi nel log (distingue tra manuale e automatico)
            tipo_ping = "automatic" if automatico else "manual"
            if stato:
                self.append_log(f"Ping {tipo_ping} → {nome}: OK")
            else:
                self.append_log(f"Ping {tipo_ping} → {nome}: FAIL")
            
        except Exception as e:
            # In caso di errore, considera non raggiungibile
            timestamp = datetime.now().strftime("%H:%M:%S")
            stato = False
            
            # Aggiorna tabella
            self.update_ping_status(nome, stato, timestamp)
            
            # Scrivi nel log
            tipo_ping = "automatic" if automatico else "manual"
            self.append_log(f"Ping {tipo_ping} → {nome}: FAIL (error: {str(e)})")
    
    def create_status_bar(self):
        """Crea la barra di stato"""
        status_bar = QFrame()
        status_bar.setFixedHeight(40)
        status_bar.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border-top: 1px solid #3a3a4a;
            }
        """)
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(15, 5, 15, 5)
        
        # Indicatore stato monitoraggio
        self.monitoring_status_label = QLabel("🔌 Monitoring: Active")
        self.monitoring_status_label.setStyleSheet("color: #51CF66; font-size: 12px;")
        layout.addWidget(self.monitoring_status_label)
        
        layout.addStretch()
        
        # Contatore macchine
        self.machines_count_label = QLabel("Machines: 0")
        self.machines_count_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        layout.addWidget(self.machines_count_label)
        
        return status_bar
    
    def tornaAllaDashboard(self):
        """Porta il focus alla dashboard (monitor resta aperto o in icona)."""
        self.go_back_to_dashboard()
    
    def closeEvent(self, event):
        """Gestisce la chiusura della finestra in modo sicuro"""
        # Imposta flag di chiusura per evitare nuovi thread
        self.is_closing = True
        
        # Ferma tutti i timer
        for timer in self.timers:
            try:
                timer.stop()
                timer.disconnect()  # Disconnette tutti i segnali
            except Exception as e:
                pass  # Ignora errori durante la chiusura
        
        # Ferma tutti i thread
        for worker in self.workers:
            try:
                # Disconnette i segnali prima di fermare (verifica tipo worker)
                if isinstance(worker, PingWorker):
                    try:
                        worker.ping_result.disconnect()
                    except:
                        pass
                elif isinstance(worker, PLCWorker):
                    try:
                        worker.plc_result.disconnect()
                    except:
                        pass
                
                # Ferma il thread
                worker.stop()
                
                # Attende terminazione sicura (max 3 secondi)
                if not worker.wait(3000):
                    # Se non termina in 3 secondi, termina forzatamente
                    worker.terminate()
                    worker.wait(1000)
            except Exception as e:
                pass  # Ignora errori durante la chiusura
        
        # Pulisce le liste
        self.workers.clear()
        self.timers.clear()
        
        # Mostra la finestra principale (parent) se esiste
        if self.parent() is not None:
            try:
                parent_window = self.parent()
                parent_window.show()
                parent_window.raise_()
                parent_window.activateWindow()
            except Exception as e:
                pass  # Ignora errori durante la chiusura
        
        # Accetta l'evento di chiusura
        event.accept()
    
    def apply_stylesheet(self):
        """Applica lo stylesheet alla finestra"""
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2a, stop:0.5 #2a2a3a, stop:1 #1a1a2a);
            }
            QGroupBox {
                background-color: #1a1a2a;
                border: 2px solid #3a3a4a;
                border-radius: 8px;
                padding: 15px;
                margin-top: 10px;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: #1a1a2a;
            }
            QLabel {
                color: #FFFFFF;
            }
        """)
