"""
Nstone LLM - Finestra Gestione CNC Universale
Interfaccia per gestione e monitoraggio macchine CNC con integrazione PLC
Compatibile con: Siemens 840D, Fanuc FOCAS, Heidenhain TNC, Syntec, OSAI, CNC cinesi aperti
Integrazione RAG Engine per assistenza cognitiva
"""
import sys
from datetime import datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTextEdit,
                             QMessageBox, QGroupBox, QScrollArea, QApplication, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from ui.theme.production_theme import (
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

# Config PLC macchina 'cnc' (sim/live, IP, mappa)
try:
    from core.machine_plc_config import (
        MACHINE_CNC,
        describe_plc_endpoint,
        get_machine,
        save_machine,
    )
    MACHINE_CONFIG_AVAILABLE = True
except ImportError:
    MACHINE_CONFIG_AVAILABLE = False
    print("⚠ Modulo machine_plc_config non disponibile")

# Importa finestra ordini macchina
try:
    from ui.windows.orders.ordini_macchina_window import OrdiniMacchinaWindow
    ORDINI_WINDOW_AVAILABLE = True
except ImportError:
    ORDINI_WINDOW_AVAILABLE = False
    print("⚠ Modulo ordini_macchina_window non disponibile")

# Importa adapter CNC
try:
    from machines.cnc_adapter import CNCAdapter, CNCStatus, MachineState, create_cnc_adapter
    CNC_ADAPTER_AVAILABLE = True
except ImportError:
    CNC_ADAPTER_AVAILABLE = False
    print("⚠ Modulo cnc_adapter non disponibile")

# Importa integrazione CNC
try:
    from machines.cnc_ui_integration import CNCUIUpdater, refresh_cnc_ui
    CNC_UI_AVAILABLE = True
except ImportError:
    CNC_UI_AVAILABLE = False
    print("⚠ Modulo cnc_ui_integration non disponibile")

# Importa RAG Engine
try:
    from llm.rag_engine import RAGEngine
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠ Modulo RAG Engine unavailable")

# Importa widget Ethernet
try:
    from ui.common.ethernet_status_widget import EthernetStatusWidget
    ETHERNET_WIDGET_AVAILABLE = True
except ImportError:
    ETHERNET_WIDGET_AVAILABLE = False
    print("⚠ Widget Ethernet non disponibile")

# Canale scrittura PLC governato (il modello propone, il governor decide)
try:
    from plc.plc_write_governor import (
        WriteGovernor,
        build_write_intent_prompt,
        intent_to_request,
        load_writable_variables,
        parse_model_intent,
    )
    WRITE_GOVERNOR_AVAILABLE = True
except ImportError:
    WRITE_GOVERNOR_AVAILABLE = False
    print("⚠ Modulo plc_write_governor non disponibile")


class CNCRAGWorker(QThread):
    """Worker thread per generare risposte RAG senza bloccare la UI"""
    result_ready = pyqtSignal(dict)  # Emette il risultato quando finisce
    error = pyqtSignal(str)  # Emette errore se qualcosa va storto
    
    def __init__(self, rag_engine, question, machine_context):
        super().__init__()
        self.rag_engine = rag_engine
        self.question = question
        self.machine_context = machine_context
    
    def run(self):
        """Esegue la generazione della risposta"""
        try:
            # Arricchisci la domanda con contesto macchina
            enriched_question = f"""{self.question}

[CNC MACHINE CONTEXT]
{self.machine_context}

Respond in English only.
"""
            
            # Genera risposta con reasoning strutturato
            result = self.rag_engine.generate_answer(
                enriched_question,
                operational=True,
            )
            
            # Aggiungi contesto macchina al risultato per riferimento
            result["machine_context"] = self.machine_context
            
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class CNCWriteIntentWorker(QThread):
    """
    Chiede al modello UN intent JSON di scrittura parametro (o action=none).
    Il modello non tocca mai il PLC: l'output passa da parser rigido e
    plc_write_governor prima di qualsiasi decisione.
    """
    result_ready = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def run(self):
        try:
            from llm.llm_service import get_llm_service
            text = get_llm_service().send_message(
                self.prompt,
                system_instruction=(
                    "You are a strict JSON generator for an industrial "
                    "parameter advisor. Output exactly ONE JSON object and "
                    "nothing else: no prose, no markdown."
                ),
            )
            self.result_ready.emit(text or "")
        except Exception as e:
            self.error.emit(str(e))


def compute_status_cross_checks(status) -> list:
    """
    Cross-check deterministici sullo stato macchina: incongruenze tra campi
    calcolate in Python, così il modello le riceve come FATTI invece di doverle
    intuire. Ritorna lista di stringhe (vuota = nessuna incongruenza).
    """
    flags = []
    state = getattr(getattr(status, 'machine_state', None), 'value', 'UNKNOWN')
    spindle = float(getattr(status, 'spindle_speed', 0.0) or 0.0)
    feed = float(getattr(status, 'feed_rate', 0.0) or 0.0)
    feed_prog = float(getattr(status, 'feed_rate_programmed', 0.0) or 0.0)
    alarm = int(getattr(status, 'alarm_code', 0) or 0)
    
    if state not in ("RUN", "JOG", "MDI") and spindle > 0:
        flags.append(
            f"Spindle at {spindle:.0f} RPM while machine state is {state} "
            "(spindle running outside RUN): verify spindle state vs machine state."
        )
    if state == "RUN" and spindle == 0:
        flags.append("Machine in RUN but spindle at 0 RPM: verify why spindle is stopped.")
    if state == "RUN" and feed == 0:
        flags.append("Machine in RUN but feed rate is 0 mm/min: axis motion appears stopped.")
    if feed_prog > 0 and feed > feed_prog * 1.10:
        flags.append(
            f"Actual feed ({feed:.0f}) exceeds programmed feed ({feed_prog:.0f}) "
            "by more than 10%: verify override."
        )
    if alarm > 0 and state not in ("ERROR", "ALARM"):
        flags.append(
            f"Alarm code {alarm} active but machine state is {state}: "
            "verify alarm handling."
        )
    if alarm == 0 and state in ("ERROR", "ALARM"):
        flags.append(
            f"Machine state is {state} but no alarm code is set: "
            "alarm detail unavailable from PLC."
        )
    return flags


class GestioneCNCWindow(SectionMainWindow):
    """
    Finestra per gestione e monitoraggio macchine CNC universali
    Compatibile con qualsiasi controllo CNC aperto
    Integrazione RAG Engine per assistenza cognitiva
    """
    
    # Istanza unica del RAG Engine (singleton pattern)
    _rag_engine_instance = None
    
    @classmethod
    def get_rag_engine(cls):
        """Ottiene o crea l'istanza unica del RAG Engine"""
        if cls._rag_engine_instance is None:
            cls._rag_engine_instance = RAGEngine()
        return cls._rag_engine_instance
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Universal CNC Management")
        
        # Imposta finestra in modalità schermo intero senza bordi né decorazioni
        self.setup_fullscreen_window()
        
        # Inizializza RAG Engine
        if RAG_AVAILABLE:
            self.rag_engine = self.get_rag_engine()
        else:
            self.rag_engine = None
        
        # Storage per dati macchina corrente
        self._current_cnc_status = None
        
        # Worker thread per RAG
        self.rag_worker = None
        
        # Canale scrittura governato: il modello propone, il governor decide,
        # l'operatore approva. SHADOW MODE: nessuna scrittura reale.
        self._write_governor = None
        self._pending_write_request = None
        self.write_intent_worker = None
        
        # Config PLC macchina 'cnc': decide sorgente dati (sim / live Snap7)
        self._plc_config = None
        if MACHINE_CONFIG_AVAILABLE:
            try:
                self._plc_config = get_machine(MACHINE_CNC)
            except Exception as e:
                print(f"⚠ Config PLC CNC non leggibile: {e}")
        self._live_mode = bool(
            self._plc_config and self._plc_config.get("mode") == "live"
        )
        
        # Adapter CNC legacy (fail-closed: nessun driver reale implementato).
        # Il percorso live reale è cnc_live_integration via setup_cnc_integration.
        self.cnc_adapter = None
        if CNC_ADAPTER_AVAILABLE and not self._live_mode:
            self.cnc_adapter = create_cnc_adapter("GENERIC_PLC")
        
        # Inizializza UI
        self.init_ui()
        self.apply_stylesheet()
        
        # Inizializza integrazione CNC (sceglie live/sim da config)
        self.setup_cnc_integration()
    
    def setup_fullscreen_window(self):
        """Finestra indipendente con barra titolo e riduzione a icona."""
        from ui.common.window_helpers import apply_machine_section_window

        apply_machine_section_window(self)
    
    def init_ui(self):
        """Inizializza l'interfaccia utente con scroll verticale"""
        # ============================================================
        # PUNTO 1: STRUTTURA BASE DELLA FINESTRA
        # ============================================================
        # La finestra GestioneCNCWindow è un QMainWindow.
        # Nessun layout deve essere assegnato direttamente alla finestra.
        # Nessun widget deve essere aggiunto direttamente alla finestra.
        
        # ============================================================
        # PUNTO 2: CREAZIONE QSCROLLAREA COME WIDGET CENTRALE
        # ============================================================
        # Crea QScrollArea: scroll_area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(production_scroll_area_stylesheet())
        
        # ============================================================
        # PUNTO 3: CREAZIONE WIDGET CENTRALE PER IL CONTENUTO
        # ============================================================
        # Crea QWidget: cnc_central_widget
        cnc_central_widget = QWidget()
        cnc_central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        # Assegnarlo alla scroll_area
        scroll_area.setWidget(cnc_central_widget)
        
        # ============================================================
        # PUNTO 4: CREAZIONE LAYOUT PRINCIPALE
        # ============================================================
        # Crea QVBoxLayout: cnc_main_layout
        # Assegnarlo a cnc_central_widget
        cnc_main_layout = QVBoxLayout(cnc_central_widget)
        cnc_main_layout.setContentsMargins(15, 15, 15, 15)
        cnc_main_layout.setSpacing(15)
        
        # ============================================================
        # PUNTO 5: INSERIMENTO DI TUTTE LE SEZIONI CNC
        # ============================================================
        # Inserire in ordine dentro cnc_main_layout:
        # (Header sarà fuori, sopra la scroll area)
        
        # Contenuto principale (layout a 2 colonne)
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        # Colonna sinistra - Machine Controls
        left_column = self.create_controls_column()
        content_layout.addWidget(left_column, 1)
        
        # Colonna destra - Status & Monitoring
        right_column = self.create_status_column()
        content_layout.addWidget(right_column, 1)
        
        cnc_main_layout.addWidget(content_widget, 1)
        
        # Casellario Pezzi in Lavorazione
        try:
            from ui.pezzi_lavorazione_widget import PezziLavorazioneWidget
            self.pezzi_widget = PezziLavorazioneWidget()
            cnc_main_layout.addWidget(self.pezzi_widget)
        except ImportError:
            self.pezzi_widget = None
        
        # Sezione Domanda Operativa (RAG Engine)
        if RAG_AVAILABLE:
            rag_section = self.create_rag_section()
            cnc_main_layout.addWidget(rag_section)

        # Sezione proposte parametri governate (modello → governor → operatore)
        if WRITE_GOVERNOR_AVAILABLE:
            cnc_main_layout.addWidget(self.create_write_proposal_section())
        
        # ============================================================
        # CREAZIONE CONTAINER PER HEADER + SCROLL AREA
        # ============================================================
        # Per QMainWindow, creiamo un container widget che contiene
        # header (fisso) + scroll_area (scrollabile)
        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Header fisso sopra lo scroll
        header = self.create_header()
        container_layout.addWidget(header, 0)  # 0 = dimensione fissa
        
        # Scroll area
        container_layout.addWidget(scroll_area, 1)  # 1 = si espande
        
        # Impostare container come widget centrale della finestra
        self.setCentralWidget(container_widget)
        
        # ============================================================
        # BARRA DI STATO (usando statusBar() di QMainWindow)
        # ============================================================
        # QMainWindow ha già un metodo statusBar()
        # Creiamo un widget custom per la barra di stato
        status_bar_widget = self.create_status_bar()
        
        # Aggiungi la status bar alla finestra usando statusBar()
        self.statusBar().addPermanentWidget(status_bar_widget)
        
        # Salva riferimento per accesso futuro
        self.scroll_area = scroll_area
        self.central_widget = cnc_central_widget
    
    def create_header(self):
        """Crea l'header unificato della finestra"""
        header_widget = QWidget()
        header_widget.setFixedHeight(50)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(15)
        
        # Pulsante Dashboard a sinistra
        self.pulsante_dashboard = QPushButton("Dashboard")
        apply_production_button(self.pulsante_dashboard, "secondary", min_height=40)
        self.pulsante_dashboard.setToolTip("Return to main window")
        self.pulsante_dashboard.clicked.connect(self.tornaAllaDashboard)
        header_layout.addWidget(self.pulsante_dashboard)
        
        titolo_sezione = QLabel("Universal CNC Management")
        titolo_sezione.setStyleSheet(production_section_title_stylesheet())
        header_layout.addWidget(titolo_sezione)
        
        header_layout.addStretch()
        
        self.ordini_btn = QPushButton("Incoming / Production Orders")
        apply_production_button(self.ordini_btn, "neutral", min_height=40)
        self.ordini_btn.setToolTip("View orders assigned to this machine")
        self.ordini_btn.clicked.connect(self.open_ordini_window)
        header_layout.addWidget(self.ordini_btn)
        
        header_widget.setStyleSheet(production_header_stylesheet())
        return header_widget
    
    def create_controls_column(self):
        """Crea la colonna sinistra con controlli macchina"""
        column_widget = QWidget()
        layout = QVBoxLayout(column_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Machine Information
        info_group = QGroupBox("Machine Information")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(15, 15, 15, 15)
        info_layout.setSpacing(8)
        
        self.machine_info_label = QLabel("Machine: Universal CNC")
        self.machine_info_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        info_layout.addWidget(self.machine_info_label)
        
        self.control_type_label = QLabel("Control: Generic")
        self.control_type_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        info_layout.addWidget(self.control_type_label)
        
        self.plc_label = QLabel("PLC: Not configured")
        self.plc_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        info_layout.addWidget(self.plc_label)
        
        # Switch sorgente dati SIM <-> LIVE (salva in config.json e riavvia)
        self.mode_switch_btn = QPushButton()
        self.mode_switch_btn.setCheckable(True)
        self.mode_switch_btn.setFixedHeight(34)
        self.mode_switch_btn.setChecked(self._live_mode)
        self.mode_switch_btn.clicked.connect(self.on_toggle_mode)
        if not MACHINE_CONFIG_AVAILABLE:
            self.mode_switch_btn.setEnabled(False)
            self.mode_switch_btn.setToolTip("machine_plc_config non disponibile")
        self._update_mode_switch_ui()
        info_layout.addWidget(self.mode_switch_btn)
        
        layout.addWidget(info_group)
        
        # Pulsanti comandi macchina
        commands_group = QGroupBox("Machine Commands")
        commands_layout = QVBoxLayout(commands_group)
        commands_layout.setContentsMargins(10, 10, 10, 10)
        commands_layout.setSpacing(10)
        
        self.btn_start = QPushButton("Start")
        apply_production_button(self.btn_start, "run")
        self.btn_start.clicked.connect(self.on_start_clicked)
        commands_layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton("Stop")
        apply_production_button(self.btn_stop, "stop")
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        commands_layout.addWidget(self.btn_stop)
        
        self.btn_hold = QPushButton("Hold")
        apply_production_button(self.btn_hold, "hold")
        self.btn_hold.clicked.connect(self.on_hold_clicked)
        commands_layout.addWidget(self.btn_hold)
        
        self.btn_reset = QPushButton("Reset")
        apply_production_button(self.btn_reset, "reset")
        self.btn_reset.clicked.connect(self.on_reset_clicked)
        commands_layout.addWidget(self.btn_reset)
        
        layout.addWidget(commands_group)
        
        # Machine Status
        status_group = QGroupBox("Machine Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(15, 15, 15, 15)
        status_layout.setSpacing(8)
        
        self.machine_state_label = QLabel("Status: --")
        self.machine_state_label.setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 14px;")
        status_layout.addWidget(self.machine_state_label)
        
        self.program_label = QLabel("Program: --")
        self.program_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        status_layout.addWidget(self.program_label)
        
        self.current_line_label = QLabel("G-code line: --")
        self.current_line_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        status_layout.addWidget(self.current_line_label)
        
        self.alarm_label = QLabel("Alarms: None")
        self.alarm_label.setStyleSheet(state_indicator_style("ok"))
        status_layout.addWidget(self.alarm_label)
        
        layout.addWidget(status_group)
        
        # Connessione PLC Ethernet
        if ETHERNET_WIDGET_AVAILABLE:
            self.ethernet_status_widget = EthernetStatusWidget()
            layout.addWidget(self.ethernet_status_widget)
        
        layout.addStretch()
        
        return column_widget
    
    def create_status_column(self):
        """Crea la colonna destra con stato e monitoraggio"""
        column_widget = QWidget()
        layout = QVBoxLayout(column_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Assi
        axes_group = QGroupBox("Axis Positions")
        axes_layout = QVBoxLayout(axes_group)
        axes_layout.setContentsMargins(15, 15, 15, 15)
        axes_layout.setSpacing(8)
        
        self.axis_x_label = QLabel("X: --")
        self.axis_x_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        axes_layout.addWidget(self.axis_x_label)
        
        self.axis_y_label = QLabel("Y: --")
        self.axis_y_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        axes_layout.addWidget(self.axis_y_label)
        
        self.axis_z_label = QLabel("Z: --")
        self.axis_z_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        axes_layout.addWidget(self.axis_z_label)
        
        layout.addWidget(axes_group)
        
        # Spindle
        spindle_group = QGroupBox("Spindle")
        spindle_layout = QVBoxLayout(spindle_group)
        spindle_layout.setContentsMargins(15, 15, 15, 15)
        spindle_layout.setSpacing(8)
        
        self.spindle_speed_label = QLabel("Speed: -- RPM")
        self.spindle_speed_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        spindle_layout.addWidget(self.spindle_speed_label)
        
        self.spindle_override_label = QLabel("Override: -- %")
        self.spindle_override_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        spindle_layout.addWidget(self.spindle_override_label)
        
        self.spindle_load_label = QLabel("Load: -- %")
        self.spindle_load_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        spindle_layout.addWidget(self.spindle_load_label)
        
        layout.addWidget(spindle_group)
        
        # Feed
        feed_group = QGroupBox("Feed")
        feed_layout = QVBoxLayout(feed_group)
        feed_layout.setContentsMargins(15, 15, 15, 15)
        feed_layout.setSpacing(8)
        
        self.feed_rate_label = QLabel("Speed: -- mm/min")
        self.feed_rate_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        feed_layout.addWidget(self.feed_rate_label)
        
        self.feed_override_label = QLabel("Override: -- %")
        self.feed_override_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        feed_layout.addWidget(self.feed_override_label)
        
        layout.addWidget(feed_group)
        
        # Tool
        tool_group = QGroupBox("Tool")
        tool_layout = QVBoxLayout(tool_group)
        tool_layout.setContentsMargins(15, 15, 15, 15)
        tool_layout.setSpacing(8)
        
        self.tool_number_label = QLabel("Number: --")
        self.tool_number_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        tool_layout.addWidget(self.tool_number_label)
        
        self.tool_load_label = QLabel("Load: -- %")
        self.tool_load_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        tool_layout.addWidget(self.tool_load_label)
        
        layout.addWidget(tool_group)
        
        layout.addStretch()
        
        return column_widget
    
    def create_rag_section(self):
        """Crea la sezione Domanda Operativa con RAG Engine"""
        rag_widget = QGroupBox("🧠 Production Agent")
        rag_layout = QVBoxLayout(rag_widget)
        rag_layout.setContentsMargins(15, 15, 15, 15)
        rag_layout.setSpacing(10)
        
        # Campo domanda
        question_label = QLabel("Question:")
        question_label.setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 14px;")
        rag_layout.addWidget(question_label)
        
        self.question_text = QTextEdit()
        self.question_text.setPlaceholderText(
            "Example: 'Why is the feed rate low?'\n"
            "Example: 'What is the optimal spindle speed?'\n"
            "Example: 'Explain the alarm cause'"
        )
        self.question_text.setMinimumHeight(100)
        self.question_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 12px;
            }
        """)
        rag_layout.addWidget(self.question_text)
        
        # Pulsante
        button_layout = QHBoxLayout()
        self.ask_button = QPushButton("Agent Analysis")
        self.ask_button.setStyleSheet("""
            QPushButton {
                background-color: #3a2a4a;
                border: 1px solid #5a4a6a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a3a5a;
                border: 1px solid #6a5a7a;
            }
            QPushButton:pressed {
                background-color: #2a1a3a;
            }
            QPushButton:disabled {
                background-color: #1a1a2a;
                color: #666666;
            }
        """)
        self.ask_button.clicked.connect(self.on_ask_neural_engine)
        button_layout.addWidget(self.ask_button)
        button_layout.addStretch()
        rag_layout.addLayout(button_layout)
        
        # Area risposta
        answer_label = QLabel("Agent Response:")
        answer_label.setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 14px;")
        rag_layout.addWidget(answer_label)
        
        self.answer_text = QTextEdit()
        self.answer_text.setReadOnly(True)
        self.answer_text.setPlaceholderText("Agent analysis will appear here...")
        self.answer_text.setMinimumHeight(150)
        self.answer_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        rag_layout.addWidget(self.answer_text)
        
        # Area reasoning strutturato
        reasoning_label = QLabel("Structured Reasoning (Level 2):")
        reasoning_label.setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 14px;")
        rag_layout.addWidget(reasoning_label)
        
        self.reasoning_text = QTextEdit()
        self.reasoning_text.setReadOnly(True)
        self.reasoning_text.setPlaceholderText(
            "1. QUESTION INTERPRETATION\n"
            "2. RELEVANT DATA FOUND\n"
            "3. LOGICAL DECISION\n"
            "4. FINAL ANSWER"
        )
        self.reasoning_text.setMinimumHeight(200)
        self.reasoning_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        rag_layout.addWidget(self.reasoning_text)
        
        # Bottone Suggerimenti Operativi
        button_layout_suggestions = QHBoxLayout()
        self.suggestions_button = QPushButton("💡 Open Operational Suggestions")
        self.suggestions_button.setToolTip("View neural-engine suggestions and validate proposed actions")
        self.suggestions_button.setStyleSheet("""
            QPushButton {
                background-color: #3a2a4a;
                border: 1px solid #5a4a6a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a3a5a;
                border: 1px solid #6a5a7a;
            }
            QPushButton:pressed {
                background-color: #2a1a3a;
            }
        """)
        self.suggestions_button.clicked.connect(self.open_suggestions_window)
        button_layout_suggestions.addWidget(self.suggestions_button)
        button_layout_suggestions.addStretch()
        rag_layout.addLayout(button_layout_suggestions)
        
        return rag_widget
    
    # ------------------------------------------------------------------
    # Proposte parametri governate (Fase 2+3 canale scrittura)
    # ------------------------------------------------------------------
    
    def create_write_proposal_section(self):
        """
        Pannello 'il modello propone, il governor decide, l'operatore approva'.
        SHADOW MODE: anche una proposta approvata NON scrive sul PLC; la
        decisione finisce solo nell'audit (autonomy_audit).
        """
        group = QGroupBox("🛡️ AI Parameter Proposal — governed (SHADOW)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        info = QLabel(
            "The model can only PROPOSE a parameter change from the whitelist. "
            "A deterministic validator (range, step, cooldown, machine state, "
            "emergency, autonomy policy) decides. Nothing is written to the PLC "
            "in shadow mode."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #8a8a9a; font-size: 11px;")
        layout.addWidget(info)
        
        btn_row = QHBoxLayout()
        self.propose_write_button = QPushButton("Request Parameter Proposal")
        self.propose_write_button.setStyleSheet("""
            QPushButton {
                background-color: #2a3a4a;
                border: 1px solid #4a5a6a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a4a5a; }
            QPushButton:pressed { background-color: #1a2a3a; }
            QPushButton:disabled { background-color: #1a1a2a; color: #666666; }
        """)
        self.propose_write_button.clicked.connect(self.on_propose_write)
        btn_row.addWidget(self.propose_write_button)
        
        self.approve_write_button = QPushButton("✔ Approve (operator)")
        self.approve_write_button.setEnabled(False)
        self.approve_write_button.setStyleSheet("""
            QPushButton {
                background-color: #2a4a2a;
                border: 1px solid #4a6a4a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a5a3a; }
            QPushButton:disabled { background-color: #1a1a2a; color: #666666; }
        """)
        self.approve_write_button.clicked.connect(self.on_approve_write)
        btn_row.addWidget(self.approve_write_button)
        
        self.discard_write_button = QPushButton("✖ Discard")
        self.discard_write_button.setEnabled(False)
        self.discard_write_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a2a;
                border: 1px solid #6a4a4a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5a3a3a; }
            QPushButton:disabled { background-color: #1a1a2a; color: #666666; }
        """)
        self.discard_write_button.clicked.connect(self.on_discard_write)
        btn_row.addWidget(self.discard_write_button)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        self.proposal_text = QTextEdit()
        self.proposal_text.setReadOnly(True)
        self.proposal_text.setMinimumHeight(180)
        self.proposal_text.setPlaceholderText(
            "Model proposal and validator verdict will appear here...\n"
            "Every check (whitelist, range, step, cooldown, machine state, "
            "emergency, policy) is shown explicitly."
        )
        self.proposal_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        layout.addWidget(self.proposal_text)
        
        return group
    
    def _get_write_governor(self):
        """
        Governor per la macchina corrente. SHADOW sempre attivo da codice:
        l'enforce arriverà solo in commissioning, con mappa OEM reale e
        decisione esplicita (non un default).
        """
        if self._write_governor is not None:
            return self._write_governor
        if self._live_mode:
            profile = (self._plc_config or {}).get("map_profile") or "oem_cnc_v1"
            # Mappa placeholder → il governor rifiuta tutto: onesto in live.
            self._write_governor = WriteGovernor("cnc", profile_id=profile, shadow=True)
        else:
            # Bench SIM: whitelist OEM per esercitare il ciclo completo.
            # Nessun PLC esiste in sim, e shadow=True lo ribadisce.
            variables = load_writable_variables("oem_cnc_v1", "cnc")
            self._write_governor = WriteGovernor(
                "cnc", variables=variables, placeholder=False, shadow=True
            )
        return self._write_governor
    
    def _governor_status(self):
        """
        Stato macchina nel formato del governor (stato + raw values).
        In live usa i raw della mappa; in sim sintetizza dai campi del
        simulatore SOLO ciò che esiste davvero (mai valori inventati).
        """
        status = self._current_cnc_status
        if status is None:
            return None
        raw = dict(getattr(status, 'raw_values', None) or {})
        state = getattr(status, 'machine_state', None)
        state_str = str(getattr(state, 'value', state or 'UNKNOWN')).upper()
        if 'feed_override' not in raw:
            fo = getattr(status, 'feed_rate_override', None)
            if isinstance(fo, (int, float)):
                raw['feed_override'] = float(fo)
        return {"machine_state": state_str, "raw_values": raw}
    
    def on_propose_write(self):
        """Chiede al modello un intent di scrittura (JSON) sulla whitelist."""
        if self._current_cnc_status is None:
            QMessageBox.warning(self, "No data", "No machine data available yet.")
            return
        
        governor = self._get_write_governor()
        whitelist = governor.whitelist()
        if not whitelist:
            QMessageBox.warning(
                self, "Whitelist vuota",
                "Nessuna variabile scrivibile dichiarata nella mappa DB.",
            )
            return
        
        goal = ""
        if hasattr(self, 'question_text'):
            goal = self.question_text.toPlainText().strip()
        if not goal:
            goal = (
                "Analyze the machine status and propose AT MOST ONE parameter "
                "correction, only if the data justifies it."
            )
        
        prompt = build_write_intent_prompt(
            self.build_machine_context(), goal, whitelist
        )
        
        self._pending_write_request = None
        self.approve_write_button.setEnabled(False)
        self.discard_write_button.setEnabled(False)
        self.propose_write_button.setEnabled(False)
        self.proposal_text.setPlainText("⏳ Asking the model for a proposal...")
        
        self.write_intent_worker = CNCWriteIntentWorker(prompt)
        self.write_intent_worker.result_ready.connect(self.on_write_intent_ready)
        self.write_intent_worker.error.connect(self.on_write_intent_error)
        self.write_intent_worker.start()
    
    def on_write_intent_ready(self, raw_text: str):
        """Parser rigido → anteprima decisione governor (nessun side effect)."""
        self.propose_write_button.setEnabled(True)
        
        intent, err = parse_model_intent(raw_text)
        if intent is None:
            self.proposal_text.setPlainText(
                "❌ PROPOSAL REJECTED BY PARSER (model output not compliant)\n"
                f"Reason: {err}\n\n--- raw model output ---\n{raw_text.strip()}"
            )
            self._audit_proposal(None, allowed=False, reason=f"parser: {err}")
            return
        
        if intent.get("action") == "none":
            self.proposal_text.setPlainText(
                "ℹ️ MODEL PROPOSES NO CHANGE\n"
                f"Reason: {intent.get('reason') or '(not stated)'}"
            )
            self._audit_proposal(intent, allowed=True, reason="action=none")
            return
        
        governor = self._get_write_governor()
        request = intent_to_request(intent, "cnc")
        # Anteprima con human_approved=True: il pulsante Approve È
        # l'approvazione; qui si mostra cosa deciderebbe il governor.
        decision = governor.evaluate(
            request,
            current_status=self._governor_status(),
            human_approved=True,
            plc_mode="live" if self._live_mode else "sim",
            plc_ip=str((self._plc_config or {}).get("ip", "")),
        )
        
        lines = [
            "MODEL PROPOSAL:",
            f"  variable : {request.variable}",
            f"  value    : {request.value}",
            f"  reason   : {request.reason}",
            f"  urgency  : {request.urgency}",
            "",
            "VALIDATOR CHECKS (deterministic):",
        ]
        for c in decision.checks:
            mark = "✅" if c.passed else "❌"
            detail = f" — {c.detail}" if c.detail else ""
            lines.append(f"  {mark} {c.name}{detail}")
        lines.append("")
        if decision.allowed:
            lines.append(
                "VERDICT: WRITABLE pending operator approval. "
                "SHADOW MODE: approving will only record the decision, "
                "nothing is written to the PLC."
            )
            self._pending_write_request = request
            self.approve_write_button.setEnabled(True)
            self.discard_write_button.setEnabled(True)
        else:
            lines.append(f"VERDICT: REJECTED — {decision.reason}")
            lines.append("The Approve button stays disabled (fail-closed).")
        self.proposal_text.setPlainText("\n".join(lines))
        
        self._audit_proposal(intent, allowed=decision.allowed, reason=decision.reason)
    
    def on_write_intent_error(self, error_msg: str):
        self.propose_write_button.setEnabled(True)
        self.proposal_text.setPlainText(f"❌ Model call failed: {error_msg}")
    
    def on_approve_write(self):
        """Approvazione operatore: esegue tramite governor (audit incluso)."""
        request = self._pending_write_request
        if request is None:
            return
        
        answer = QMessageBox.question(
            self,
            "Approve parameter write?",
            f"Variable: {request.variable}\nValue: {request.value}\n"
            f"Reason: {request.reason}\n\n"
            "SHADOW MODE: the decision is recorded in the audit log, "
            "no bytes are written to the PLC.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        
        governor = self._get_write_governor()
        # Rivaluta sullo stato ATTUALE: tra proposta e approvazione la
        # macchina può essere cambiata (fail-closed anche qui).
        decision = governor.execute(
            request,
            None,  # shadow: nessun client PLC necessario
            current_status=self._governor_status(),
            human_approved=True,
            plc_mode="live" if self._live_mode else "sim",
            plc_ip=str((self._plc_config or {}).get("ip", "")),
        )
        
        if decision.allowed:
            self.proposal_text.append(
                f"\n✅ APPROVED BY OPERATOR — {decision.execute_message}\n"
                "Decision recorded in autonomy audit."
            )
        else:
            self.proposal_text.append(
                f"\n❌ REJECTED AT APPROVAL TIME — {decision.reason}\n"
                "(machine state changed since the proposal; fail-closed)"
            )
        self._pending_write_request = None
        self.approve_write_button.setEnabled(False)
        self.discard_write_button.setEnabled(False)
    
    def on_discard_write(self):
        self._pending_write_request = None
        self.approve_write_button.setEnabled(False)
        self.discard_write_button.setEnabled(False)
        self.proposal_text.append("\n🗑️ Proposal discarded by operator (not executed).")
    
    def _audit_proposal(self, intent, *, allowed: bool, reason: str):
        """Traccia ogni proposta (anche rifiutate dal parser) per la fase shadow."""
        try:
            from modules.action_store import log_audit
            log_audit(
                "plc_write_proposal",
                allowed,
                reason,
                agent="model",
                payload={"machine_id": "cnc", "intent": intent or {},
                         "mode": "live" if self._live_mode else "sim"},
            )
        except Exception:
            pass
    
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
        
        # Indicatori cognitivi
        if RAG_AVAILABLE:
            self.neural_engine_indicator = QLabel("🧠 Neural Engine: Active")
            self.neural_engine_indicator.setStyleSheet(state_indicator_style("ok"))
            layout.addWidget(self.neural_engine_indicator)
            
            self.memory_indicator = QLabel("💾 Memory: Updated")
            self.memory_indicator.setStyleSheet(state_indicator_style("ok"))
            layout.addWidget(self.memory_indicator)
            
            self.context_indicator = QLabel("📊 Context: Built")
            self.context_indicator.setStyleSheet(state_indicator_style("ok"))
            layout.addWidget(self.context_indicator)
        
        layout.addStretch()
        
        # Diagnostica PLC (ping / latenza / CPU) — popolata solo in modalità live
        self.plc_diag_label = QLabel("")
        self.plc_diag_label.setStyleSheet(production_label_stylesheet(variant="muted") + " font-size: 12px;")
        layout.addWidget(self.plc_diag_label)
        
        # Stato CNC (badge SIM/LIVE sempre esplicito)
        self.cnc_status_label = QLabel("CNC: Not connected")
        self.cnc_status_label.setStyleSheet(state_indicator_style("alarm"))
        layout.addWidget(self.cnc_status_label)
        
        return status_bar
    
    def _update_mode_switch_ui(self):
        """Aggiorna testo/colore dello switch SIM/LIVE."""
        if not hasattr(self, 'mode_switch_btn'):
            return
        if self._live_mode:
            ip = self._plc_config.get("ip", "?") if self._plc_config else "?"
            self.mode_switch_btn.setText(f"🔴 LIVE — PLC reale ({ip})  [clicca per SIM]")
            self.mode_switch_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a4a3a; border: 1px solid #51CF66;
                    border-radius: 6px; color: #51CF66;
                    font-size: 12px; font-weight: bold; padding: 6px;
                }
                QPushButton:hover { background-color: #3a5a4a; }
            """)
            self.mode_switch_btn.setToolTip(
                "Sorgente dati: PLC reale via Snap7 (read-only).\n"
                "Clicca per tornare al simulatore locale."
            )
        else:
            self.mode_switch_btn.setText("🟡 SIM — simulatore locale  [clicca per LIVE]")
            self.mode_switch_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a4a2a; border: 1px solid #FFD93D;
                    border-radius: 6px; color: #FFD93D;
                    font-size: 12px; font-weight: bold; padding: 6px;
                }
                QPushButton:hover { background-color: #5a5a3a; }
            """)
            self.mode_switch_btn.setToolTip(
                "Sorgente dati: simulatore CNC locale (demo/bench).\n"
                "Clicca per collegarti al PLC reale configurato."
            )
    
    def _teardown_cnc_integration(self):
        """Ferma e rimuove la sorgente dati attiva (sim o live)."""
        if hasattr(self, 'cnc_live_updater'):
            try:
                self.cnc_live_updater.stop()
            except Exception:
                pass
            del self.cnc_live_updater
        if hasattr(self, 'cnc_simulator_updater'):
            try:
                self.cnc_simulator_updater.stop()
            except Exception:
                pass
            del self.cnc_simulator_updater
        if hasattr(self, 'cnc_updater') and self.cnc_updater:
            try:
                self.cnc_updater.stop()
            except Exception:
                pass
            self.cnc_updater = None
        self._current_cnc_status = None
        if hasattr(self, 'plc_diag_label'):
            self.plc_diag_label.setText("")
    
    def on_toggle_mode(self, checked: bool):
        """Switch SIM <-> LIVE: salva in config.json e riavvia la sorgente dati."""
        if not MACHINE_CONFIG_AVAILABLE:
            return
        
        target_live = bool(checked)
        if target_live:
            ip = self._plc_config.get("ip", "?") if self._plc_config else "?"
            answer = QMessageBox.question(
                self,
                "Passare a LIVE?",
                f"Collegarsi al PLC reale su {ip}:102 (Snap7, sola lettura)?\n\n"
                "I comandi macchina resteranno bloccati dalla policy "
                "(pilota read-only).",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self.mode_switch_btn.blockSignals(True)
                self.mode_switch_btn.setChecked(False)
                self.mode_switch_btn.blockSignals(False)
                return
        
        try:
            save_machine(MACHINE_CNC, {"mode": "live" if target_live else "sim"})
            self._plc_config = get_machine(MACHINE_CNC)
        except Exception as e:
            QMessageBox.warning(self, "Config", f"Impossibile salvare la modalità: {e}")
            self.mode_switch_btn.blockSignals(True)
            self.mode_switch_btn.setChecked(self._live_mode)
            self.mode_switch_btn.blockSignals(False)
            return
        
        self._live_mode = target_live
        self._teardown_cnc_integration()
        # Il governor dipende da modalità e mappa: va ricostruito, e le
        # proposte in sospeso non sopravvivono al cambio di sorgente dati.
        self._write_governor = None
        self._pending_write_request = None
        if hasattr(self, 'approve_write_button'):
            self.approve_write_button.setEnabled(False)
            self.discard_write_button.setEnabled(False)
            self.proposal_text.clear()
        self._update_mode_switch_ui()
        self.on_cnc_connection_changed(False)
        self.setup_cnc_integration()
        print(f"🔀 CNC: modalità cambiata → {'LIVE' if target_live else 'SIM'}")
    
    def setup_cnc_integration(self):
        """
        Configura la sorgente dati CNC in base a config.json (machines.cnc.mode):
          - live: Snap7 read-only verso PLC reale (cnc_live_integration).
                  NESSUN fallback al simulatore: in live niente dati finti.
          - sim:  simulatore locale (pattern identico a Multifilo/Lucidatrice).
        """
        # Mostra endpoint PLC configurato nella colonna info
        if self._plc_config and hasattr(self, 'plc_label'):
            try:
                self.plc_label.setText(f"PLC: {describe_plc_endpoint(self._plc_config)}")
            except Exception:
                pass
        
        if self._live_mode:
            try:
                from machines.cnc_live_integration import CNCLiveUpdater
                self.cnc_live_updater = CNCLiveUpdater(self._plc_config, parent=self)
                self.cnc_live_updater.status_updated.connect(self.on_cnc_status_updated)
                self.cnc_live_updater.connection_changed.connect(self.on_cnc_connection_changed)
                self.cnc_live_updater.diagnostics_updated.connect(self.on_plc_diagnostics)
                self.cnc_live_updater.start(interval_ms=200)
                self._current_cnc_status = None
                self.on_cnc_connection_changed(False)  # onesto finché il PLC non risponde
                print("✅ CNC LIVE attivato (Snap7 read-only)")
            except ImportError as e:
                # Fail-closed: in modalità live non si ripiega mai sul simulatore
                print(f"⚠ CNC live non disponibile: {e} — nessun fallback al simulatore")
                self.on_cnc_connection_changed(False)
            return
        
        # Modalità SIM
        try:
            from machines.cnc_simulator_integration import CNCSimulatorUpdater, CNCSimulatorStatus
            self.cnc_simulator_updater = CNCSimulatorUpdater(parent=self)
            self.cnc_simulator_updater.status_updated.connect(self.on_cnc_status_updated)
            self.cnc_simulator_updater.connection_changed.connect(self.on_cnc_connection_changed)
            self.cnc_simulator_updater.start(interval_ms=100)
            self._current_cnc_status = None
            print("✅ Simulatore CNC attivato")
        except ImportError:
            # Fallback a integrazione CNC esistente (adapter fail-closed:
            # mostrerà onestamente "Not connected")
            if CNC_UI_AVAILABLE:
                try:
                    from machines.cnc_ui_integration import CNCUIUpdater, refresh_cnc_ui
                    self.cnc_updater = CNCUIUpdater(self)
                    if self.cnc_adapter:
                        self.cnc_updater.set_cnc_adapter(self.cnc_adapter)
                    self.cnc_updater.status_updated.connect(
                        lambda status: refresh_cnc_ui(self, status)
                    )
                    self.cnc_updater.start(100)
                except Exception as e:
                    print(f"⚠ Errore setup integrazione CNC: {e}")
            else:
                print("⚠ Simulatore CNC e integrazione CNC non disponibili")
    
    def on_cnc_status_updated(self, status):
        """Callback chiamato quando arrivano dati macchina (sim o live)"""
        self._current_cnc_status = status
        
        # Mappa DB placeholder (oem_cnc_v1 non ancora compilata): dirlo chiaro
        if getattr(status, 'map_placeholder', False) and hasattr(self, 'cnc_status_label'):
            current_text = self.cnc_status_label.text()
            if "Connected" in current_text and "mappa" not in current_text:
                self.cnc_status_label.setText(current_text + " — mappa DB da compilare")
        
        # Aggiorna indicatori contesto
        if RAG_AVAILABLE and hasattr(self, 'context_indicator'):
            self.context_indicator.setText("📊 Context: Built")
            self.context_indicator.setStyleSheet(state_indicator_style("ok"))
        
        # Aggiorna casellario pezzi.
        # Campi gestionali (materiale, pezzi, …): il simulatore li popola, il
        # PLC live no — getattr con default onesti, mai inventare valori.
        if hasattr(self, 'pezzi_widget') and self.pezzi_widget is not None:
            self.pezzi_widget.update_pezzi(
                materiale=getattr(status, 'materiale', 'n/d'),
                spessore=getattr(status, 'spessore', 0.0),
                dimensioni_l=getattr(status, 'dimensioni_l', 0.0),
                dimensioni_h=getattr(status, 'dimensioni_h', 0.0),
                dimensioni_p=getattr(status, 'dimensioni_p', 0.0),
                pezzi_totali=getattr(status, 'pezzi_totali', 0),
                pezzi_completati=getattr(status, 'pezzi_completati', 0),
                pezzi_in_lavorazione=getattr(status, 'pezzi_in_lavorazione', 0),
                avanzamento_pezzo=getattr(status, 'avanzamento_pezzo', 0.0),
                avanzamento_lotto=getattr(status, 'avanzamento_lotto', 0.0)
            )
        
        # Aggiorna UI
        self.refresh_cnc_ui(status)
    
    def on_cnc_connection_changed(self, connected: bool):
        """Callback quando cambia lo stato di connessione (badge SIM/LIVE esplicito)"""
        mode_tag = "LIVE" if self._live_mode else "SIM"
        if hasattr(self, 'cnc_status_label'):
            if connected:
                if self._live_mode:
                    endpoint = self._plc_config.get("ip", "?") if self._plc_config else "?"
                    self.cnc_status_label.setText(f"CNC LIVE: Connected ({endpoint})")
                    self.cnc_status_label.setStyleSheet("color: #51CF66; font-size: 12px; font-weight: bold;")
                else:
                    # Ambra, mai verde: il simulatore non deve sembrare una macchina vera
                    self.cnc_status_label.setText("CNC SIM: Connected (simulatore)")
                    self.cnc_status_label.setStyleSheet("color: #FFD93D; font-size: 12px; font-weight: bold;")
            else:
                self.cnc_status_label.setText(f"CNC {mode_tag}: Not connected")
                self.cnc_status_label.setStyleSheet("color: #FF6B6B; font-size: 12px; font-weight: bold;")
        
        # Abilita/disabilita pulsanti comandi.
        # In LIVE i comandi restano bloccati salvo esplicito via da autonomy_policy
        # (pilota read-only fail-closed).
        allow_commands = connected and self._commands_allowed()
        tooltip = ""
        if connected and not allow_commands:
            tooltip = "Pilota read-only: scritture PLC bloccate da policy di autonomia"
        for btn_name in ("btn_start", "btn_stop", "btn_hold", "btn_reset"):
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.setEnabled(allow_commands)
                btn.setToolTip(tooltip)
    
    def _commands_allowed(self) -> bool:
        """
        In SIM i comandi sono liberi (bench). In LIVE decide autonomy_policy:
        senza approvazione operatore la scrittura PLC è negata (fail-closed),
        e se la policy non è importabile si nega comunque.
        """
        if not self._live_mode:
            return True
        try:
            from core.autonomy_policy import Action, ActionContext, get_policy
            result = get_policy().allow(
                Action.PLC_WRITE,
                ActionContext(
                    machine_id="cnc",
                    plc_mode="live",
                    plc_ip=str(self._plc_config.get("ip", "")) if self._plc_config else "",
                ),
            )
            return result.allowed
        except ImportError:
            return False
    
    def on_plc_diagnostics(self, stats: dict):
        """Mostra diagnostica connessione PLC (ping / latenza lettura / CPU)."""
        if not hasattr(self, 'plc_diag_label'):
            return
        parts = []
        if stats.get("ping_ok") is True:
            parts.append(f"ping {stats.get('ping_ms', '?')} ms")
        elif stats.get("ping_ok") is False:
            parts.append("ping KO")
        latency = stats.get("read_latency_ms")
        if latency is not None:
            parts.append(f"read {latency} ms")
        cpu = stats.get("cpu_state") or "—"
        if cpu != "—":
            parts.append(f"CPU {cpu}")
        order_code = stats.get("plc_order_code")
        if order_code:
            parts.append(order_code)
        last_error = stats.get("last_error")
        if last_error and not stats.get("snap7_connected"):
            parts.append(f"({last_error})")
        
        self.plc_diag_label.setText(" · ".join(parts) if parts else "")
        color = "#51CF66" if stats.get("snap7_connected") else "#FF6B6B"
        self.plc_diag_label.setStyleSheet(f"color: {color}; font-size: 12px;")
    
    def refresh_cnc_ui(self, status):
        """Aggiorna tutti i widget UI con i dati del simulatore"""
        if status is None:
            return
        
        # Machine Status
        if hasattr(self, 'machine_state_label'):
            self.machine_state_label.setText(f"Status: {status.machine_state.value}")
            # Colore in base allo stato
            if status.machine_state.value == "RUN":
                self.machine_state_label.setStyleSheet("color: #51CF66; font-size: 14px; font-weight: bold;")
            elif status.machine_state.value == "ERROR":
                self.machine_state_label.setStyleSheet("color: #FF6B6B; font-size: 14px; font-weight: bold;")
            elif status.machine_state.value == "HOLD":
                self.machine_state_label.setStyleSheet("color: #FFD93D; font-size: 14px; font-weight: bold;")
            else:
                self.machine_state_label.setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 14px;")
        
        if hasattr(self, 'program_label'):
            self.program_label.setText(f"Program: {status.program_name}")
        
        if hasattr(self, 'current_line_label'):
            self.current_line_label.setText(f"G-code line: {status.current_line}/{status.total_lines}")
        
        if hasattr(self, 'alarm_label'):
            if status.alarm_code > 0:
                self.alarm_label.setText(f"Alarm: {status.alarm_code} - {status.alarm_message}")
                self.alarm_label.setStyleSheet(state_indicator_style("alarm"))
            else:
                self.alarm_label.setText("Alarms: None")
                self.alarm_label.setStyleSheet(state_indicator_style("ok"))
        
        # Axis Positions
        if hasattr(self, 'axis_x_label'):
            self.axis_x_label.setText(f"X: {status.position.x:.3f} mm")
        if hasattr(self, 'axis_y_label'):
            self.axis_y_label.setText(f"Y: {status.position.y:.3f} mm")
        if hasattr(self, 'axis_z_label'):
            self.axis_z_label.setText(f"Z: {status.position.z:.3f} mm")
        
        # Spindle
        if hasattr(self, 'spindle_speed_label'):
            self.spindle_speed_label.setText(f"Speed: {status.spindle_speed:.0f} RPM")
        if hasattr(self, 'spindle_override_label'):
            self.spindle_override_label.setText(f"Override: {status.spindle_speed_override:.1f} %")
        if hasattr(self, 'spindle_load_label'):
            self.spindle_load_label.setText(f"Load: {status.spindle_load:.1f} %")
        
        # Feed
        if hasattr(self, 'feed_rate_label'):
            self.feed_rate_label.setText(f"Speed: {status.feed_rate:.2f} mm/min")
        if hasattr(self, 'feed_override_label'):
            self.feed_override_label.setText(f"Override: {status.feed_rate_override:.1f} %")
        
        # Tool
        if hasattr(self, 'tool_number_label'):
            self.tool_number_label.setText(f"Number: {status.tool_number}")
        if hasattr(self, 'tool_load_label'):
            self.tool_load_label.setText(f"Load: {status.tool_load:.1f} %")
        
        # PLC (se widget Ethernet disponibile)
        if hasattr(self, 'ethernet_status_widget') and self.ethernet_status_widget:
            plc_connected = bool(getattr(status, 'plc_connected', False))
            self.ethernet_status_widget.update_status({
                "connected": plc_connected,
                "state": "Connesso" if plc_connected else "Disconnesso",
                "ip": getattr(status, 'plc_ip', '') or "--",
                "port": getattr(status, 'plc_port', 0) or "--",
                "latency_ms": round(float(getattr(status, 'plc_latency', 0.0)), 1),
                "last_packet_time": (
                    datetime.now().strftime("%H:%M:%S") if plc_connected else None
                ),
                "total_packets": getattr(status, 'plc_packets_received', 0),
                "failed_packets": getattr(status, 'plc_errors', 0),
            })
    
    def _active_updater(self):
        """Updater dati attivo: live (Snap7) o simulatore."""
        return (
            getattr(self, 'cnc_live_updater', None)
            or getattr(self, 'cnc_simulator_updater', None)
        )
    
    def _send_machine_command(self, label: str, method_name: str):
        """
        Invia un comando macchina all'updater attivo.
        In LIVE il comando è bloccato a monte dalla policy (fail-closed);
        l'updater live rifiuta comunque ogni scrittura (difesa in profondità).
        """
        if self._live_mode and not self._commands_allowed():
            QMessageBox.warning(
                self,
                "Comando bloccato",
                "Pilota read-only: le scritture verso il PLC reale sono "
                "disabilitate dalla policy di autonomia.",
            )
            return
        try:
            updater = self._active_updater()
            if updater is None:
                QMessageBox.warning(self, "Error", "CNC data source unavailable")
                return
            success = getattr(updater, method_name)()
            if success:
                target = "PLC" if self._live_mode else "simulator"
                QMessageBox.information(self, "Command", f"{label} command sent to {target}")
            else:
                QMessageBox.warning(self, "Error", f"Unable to send {label} command")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{label} command error: {e}")
    
    def on_start_clicked(self):
        """Gestisce il click sul pulsante Start"""
        self._send_machine_command("Start", "send_start")
    
    def on_stop_clicked(self):
        """Gestisce il click sul pulsante Stop"""
        self._send_machine_command("Stop", "send_stop")
    
    def on_hold_clicked(self):
        """Gestisce il click sul pulsante Hold"""
        self._send_machine_command("Hold", "send_hold")
    
    def on_reset_clicked(self):
        """Gestisce il click sul pulsante Reset"""
        self._send_machine_command("Reset", "send_reset")
    
    def build_machine_context(self) -> str:
        """
        Costruisce il contesto macchina CNC per il RAG Engine.
        Disciplina anti-allucinazione: dichiara sempre la FONTE dei dati
        (SIM/LIVE) e non presenta mai come misura un valore non letto dal PLC.
        """
        if self._current_cnc_status is None:
            return "[CNC MACHINE STATUS]\nNo machine data available."
        
        status = self._current_cnc_status
        is_live = getattr(status, 'source', 'sim') == 'live'
        context_parts = ["[CNC MACHINE STATUS]"]
        context_parts.append("")
        
        # Fonte dati: il modello deve sapere cosa sta guardando
        if is_live:
            context_parts.append("DATA SOURCE: LIVE PLC (Snap7, read-only pilot)")
        else:
            context_parts.append("DATA SOURCE: LOCAL SIMULATOR (bench data, not a real machine)")
        context_parts.append("")
        
        # Mappa placeholder: connessi ma senza valori di processo. Fermarsi qui
        # evita di dare al modello zeri mai letti spacciati per misure.
        if is_live and getattr(status, 'map_placeholder', False):
            context_parts.append(
                f"PLC CONNECTION: connected to {status.plc_ip}:{status.plc_port}, "
                f"read latency {status.plc_latency:.1f} ms."
            )
            context_parts.append(
                "DB MAP: NOT COMPILED YET (placeholder). No process values are "
                "being read from the PLC."
            )
            context_parts.append(
                "IMPORTANT: machine state, spindle, feed, axes and tool data are "
                "UNKNOWN. Do not assess or invent them; only comment on "
                "connection health and next commissioning steps."
            )
            return "\n".join(context_parts)
        
        # Stato macchina
        context_parts.append(f"Machine state: {status.machine_state.value}")
        context_parts.append(f"Program: {status.program_name or 'N/A'}")
        context_parts.append(f"G-code line: {status.current_line}")
        context_parts.append(f"Current block: {status.current_block or 'N/A'}")
        context_parts.append("")
        
        # Axes
        context_parts.append("AXIS POSITIONS:")
        context_parts.append(f"  - X: {status.position.x:.3f} mm")
        context_parts.append(f"  - Y: {status.position.y:.3f} mm")
        context_parts.append(f"  - Z: {status.position.z:.3f} mm")
        context_parts.append("")
        
        # Spindle
        context_parts.append("SPINDLE:")
        context_parts.append(f"  - Speed: {status.spindle_speed:.0f} RPM")
        context_parts.append(f"  - Override: {status.spindle_speed_override:.1f} %")
        context_parts.append(f"  - Load: {status.spindle_load:.1f} %")
        context_parts.append(f"  - Temperature: {status.spindle_temperature:.1f} °C")
        context_parts.append("")
        
        # Feed
        context_parts.append("FEED:")
        context_parts.append(f"  - Speed: {status.feed_rate:.2f} mm/min")
        context_parts.append(f"  - Override: {status.feed_rate_override:.1f} %")
        context_parts.append(f"  - Programmed: {status.feed_rate_programmed:.2f} mm/min")
        context_parts.append("")
        
        # Tool
        context_parts.append("TOOL:")
        context_parts.append(f"  - Number: {status.tool_number}")
        context_parts.append(f"  - Load: {status.tool_load:.1f} %")
        context_parts.append(f"  - Length offset: {status.tool_length_offset:.3f} mm")
        context_parts.append(f"  - Radius offset: {status.tool_radius_offset:.3f} mm")
        context_parts.append("")
        
        # Allarmi
        if status.alarm_code > 0:
            context_parts.append(f"ALARM: Code {status.alarm_code} - {status.alarm_message}")
        else:
            context_parts.append("Alarms: None")
        context_parts.append("")
        
        # PLC
        if status.plc_connected:
            context_parts.append(f"PLC: Connected ({status.plc_ip}:{status.plc_port}, latency: {status.plc_latency:.1f} ms)")
        else:
            context_parts.append("PLC: Not connected")
        
        # Valori raw letti dalla mappa DB (solo live con mappa compilata):
        # nomi variabile OEM -> valore realmente letto dal PLC.
        raw_values = getattr(status, 'raw_values', None)
        if is_live and raw_values:
            context_parts.append("")
            context_parts.append("RAW PLC VALUES (variable name -> value read from DB map):")
            for name, value in raw_values.items():
                shown = "n/d (not read)" if value is None else value
                context_parts.append(f"  - {name}: {shown}")
            context_parts.append(
                "Values marked 'n/d (not read)' are UNKNOWN: do not assess or invent them."
            )
        
        # Cross-check deterministici (calcolati in Python, non dal modello)
        context_parts.append("")
        flags = compute_status_cross_checks(status)
        if flags:
            context_parts.append("CONSISTENCY CHECKS (computed deterministically, treat as facts):")
            for f in flags:
                context_parts.append(f"  - {f}")
        else:
            context_parts.append("CONSISTENCY CHECKS: no cross-field inconsistency detected.")
        
        return "\n".join(context_parts)
    
    def _generate_auto_suggestion(self) -> str:
        """Genera suggerimento automatico basato su stato macchina"""
        if not self._current_cnc_status:
            return ""
        
        status = self._current_cnc_status
        
        # Se feedrate basso → suggerire cause
        if status.feed_rate < 100.0 and status.machine_state.value == "RUN":
            return "Why is the feed rate low? What are the possible causes?"
        
        if status.spindle_speed == 0.0 and status.machine_state.value == "RUN":
            return "Why is the spindle stopped? How can I restart it?"
        
        if status.alarm_code > 0:
            return f"Explain the cause of alarm {status.alarm_code}: {status.alarm_message}"
        
        if status.feed_rate < status.feed_rate_programmed * 0.5 and status.machine_state.value == "RUN":
            return "Production seems slow. How can I optimize machining parameters?"
        
        if status.machine_state.value == "ERROR":
            return "The machine is in error state. What are the steps to resolve the issue?"
        
        return "How can I improve machining efficiency?"
    
    def on_ask_neural_engine(self):
        """Gestisce la richiesta al motore neurale"""
        from modules.ollama_prewarm import request_production_agent_prewarm

        request_production_agent_prewarm("cnc")
        if not RAG_AVAILABLE or self.rag_engine is None:
            QMessageBox.warning(
                self,
                "RAG Engine unavailable",
                "Neural engine is unavailable. Check configuration."
            )
            return
        
        question = self.question_text.toPlainText().strip()
        if not question:
            QMessageBox.warning(
                self,
                "Empty question",
                "Enter a question for the production agent."
            )
            return
        
        # Disabilita pulsante durante elaborazione
        self.ask_button.setEnabled(False)
        self.ask_button.setText("Processing...")
        
        # Pulisci aree risposta
        self.answer_text.clear()
        self.reasoning_text.clear()
        
        # Aggiorna indicatori
        if hasattr(self, 'neural_engine_indicator'):
            self.neural_engine_indicator.setText("🧠 Neural Engine: Processing...")
            self.neural_engine_indicator.setStyleSheet(state_indicator_style("warn"))
        
        # Costruisci contesto macchina
        machine_context = self.build_machine_context()
        
        # Crea worker thread
        self.rag_worker = CNCRAGWorker(
            self.rag_engine,
            question,
            machine_context
        )
        self.rag_worker.result_ready.connect(self.on_rag_finished)
        self.rag_worker.error.connect(self.on_rag_error)
        self.rag_worker.start()
    
    def on_rag_finished(self, result: dict):
        """Callback quando la risposta RAG è pronta"""
        # Mostra risposta
        answer = result.get("answer", "No answer generated.")
        self.answer_text.setPlainText(answer)
        
        # Mostra reasoning strutturato
        reasoning = result.get("reasoning", "")
        if reasoning:
            self.reasoning_text.setPlainText(reasoning)
        else:
            self.reasoning_text.setPlainText("Reasoning unavailable.")
        
        # Aggiorna indicatori
        self.update_cognitive_status_indicators(True, True, True)
        
        # Riabilita pulsante
        self.ask_button.setEnabled(True)
        self.ask_button.setText("Agent Analysis")
    
    def on_rag_error(self, error_msg: str):
        """Callback quando si verifica un errore"""
        self.answer_text.setPlainText(f"Error generating answer:\n{error_msg}")
        self.reasoning_text.setPlainText("Error during reasoning.")
        
        # Aggiorna indicatori
        self.update_cognitive_status_indicators(False, False, False)
        
        # Riabilita pulsante
        self.ask_button.setEnabled(True)
        self.ask_button.setText("Agent Analysis")
    
    def update_cognitive_status_indicators(self, neural_active: bool, memory_updated: bool, context_built: bool):
        """Aggiorna gli indicatori cognitivi nella barra di stato"""
        if hasattr(self, 'neural_engine_indicator'):
            if neural_active:
                self.neural_engine_indicator.setText("🧠 Neural Engine: Active")
                self.neural_engine_indicator.setStyleSheet(state_indicator_style("ok"))
            else:
                self.neural_engine_indicator.setText("🧠 Neural Engine: Error")
                self.neural_engine_indicator.setStyleSheet(state_indicator_style("alarm"))
        
        if hasattr(self, 'memory_indicator'):
            if memory_updated:
                self.memory_indicator.setText("💾 Memory: Updated")
                self.memory_indicator.setStyleSheet(state_indicator_style("ok"))
            else:
                self.memory_indicator.setText("💾 Memory: Not updated")
                self.memory_indicator.setStyleSheet(state_indicator_style("warn"))
        
        if hasattr(self, 'context_indicator'):
            if context_built:
                self.context_indicator.setText("📊 Context: Built")
                self.context_indicator.setStyleSheet(state_indicator_style("ok"))
            else:
                self.context_indicator.setText("📊 Context: Unavailable")
                self.context_indicator.setStyleSheet(state_indicator_style("warn"))
    
    def open_ordini_window(self):
        """Apre la finestra ordini in arrivo per questa macchina"""
        if not ORDINI_WINDOW_AVAILABLE:
            QMessageBox.warning(self, "Module unavailable", 
                               "orders_macchina_window module is unavailable.")
            return
        
        try:
            if not hasattr(self, 'ordini_window') or self.ordini_window is None:
                self.ordini_window = OrdiniMacchinaWindow("CNC", self)
            self.ordini_window.show()
            self.ordini_window.raise_()
            self.ordini_window.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", 
                               f"Unable to open orders window:\n{str(e)}")
    
    def tornaAllaDashboard(self):
        """Porta il focus alla dashboard (finestra macchina resta aperta o in icona)."""
        self.go_back_to_dashboard()
    
    def open_suggestions_window(self):
        """Apre la finestra Suggerimenti Operativi"""
        try:
            from ui.windows.ai.suggerimenti_cnc_window import SuggerimentiCNCWindow
            
            suggestions_window = SuggerimentiCNCWindow(
                cnc_status=self._current_cnc_status,
                rag_engine=self.rag_engine if RAG_AVAILABLE else None,
                parent=self
            )
            suggestions_window.show()
            suggestions_window.raise_()
            suggestions_window.activateWindow()
        except ImportError as e:
            QMessageBox.warning(
                self,
                "Module unavailable",
                f"Cannot open Operational Suggestions window:\n{str(e)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error opening window:\n{str(e)}"
            )
    
    def apply_stylesheet(self):
        """Applica tema Production HMI (Flat Metal + ISO)."""
        apply_production_theme(self)
    
    def closeEvent(self, event):
        """Pulizia quando la finestra viene chiusa"""
        if hasattr(self, 'cnc_live_updater'):
            self.cnc_live_updater.stop()
        if hasattr(self, 'cnc_simulator_updater'):
            self.cnc_simulator_updater.stop()
        if hasattr(self, 'cnc_updater') and self.cnc_updater:
            self.cnc_updater.stop()
        if self.rag_worker and self.rag_worker.isRunning():
            self.rag_worker.terminate()
            self.rag_worker.wait()
        if self.write_intent_worker and self.write_intent_worker.isRunning():
            self.write_intent_worker.terminate()
            self.write_intent_worker.wait()
        if self.cnc_adapter:
            self.cnc_adapter.disconnect()
        super().closeEvent(event)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = GestioneCNCWindow()
    window.show()
    sys.exit(app.exec_())

