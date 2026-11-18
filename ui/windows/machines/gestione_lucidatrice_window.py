"""
Nstone LLM - Finestra Gestione Lucidatrice/Calibratrice
Interfaccia per gestione e monitoraggio macchina Lucidatrice/Calibratrice con integrazione PLC
Integrazione RAG Engine per assistenza cognitiva
"""
import sys
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTextEdit,
                             QMessageBox, QGroupBox, QScrollArea)
from ui.windows.orders.ordini_macchina_window import OrdiniMacchinaWindow
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication
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
    configure_production_module_header,
    wire_machine_command_buttons,
)
from PyQt5.QtGui import QFont

from core.machine_plc_config import (
    MACHINE_LUCIDATRICE,
    describe_plc_endpoint,
    get_machine,
)

# Importa integrazione PLC Snap7 (pattern identico a Multifilo)
try:
    from machines.lucidatrice_snap7_integration import (LucidatriceSnap7Updater, LucidatriceStatus,
                                                refresh_lucidatrice_ui)
    PLC_SNAP7 = True
    PLC_AVAILABLE = True
except ImportError:
    PLC_SNAP7 = False
    try:
        from machines.lucidatrice_ui_integration import LucidatriceUIUpdater, refresh_lucidatrice_ui
        PLC_AVAILABLE = True
    except ImportError:
        PLC_AVAILABLE = False
        print("⚠ Modulo lucidatrice_snap7_integration non disponibile")

# Importa componenti UI modulari
try:
    from ui.gestione_lucidatrice.components import (LucidatriceStatusWidget, 
                                                     LucidatriceProduzioneWidget,
                                                     LucidatriceParametriWidget)
    COMPONENTS_AVAILABLE = True
except ImportError:
    COMPONENTS_AVAILABLE = False
    print("⚠ Componenti UI modulari non disponibili")

# Importa RAG Engine
try:
    from llm.rag_engine import RAGEngine
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠ Modulo RAG Engine unavailable")


class LucidatriceRAGWorker(QThread):
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

[CONTESTO MACCHINA LUCIDATRICE/CALIBRATRICE]
{self.machine_context}
"""
            
            # Genera risposta con reasoning strutturato
            # Il RAG Engine costruirà anche il contesto dal database
            # Nota: il salvataggio automatico in memoria evolutiva avviene già in generate_answer()
            # con tag vuoto. I tag possono essere aggiunti in futuro se necessario.
            result = self.rag_engine.generate_answer(
                enriched_question,
                include_reasoning=True,
                operational=True,
            )
            
            # Aggiungi contesto macchina al risultato per riferimento
            result["machine_context"] = self.machine_context
            
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class GestioneLucidatriceWindow(SectionDialog):
    """
    Finestra per gestione e monitoraggio macchina Lucidatrice/Calibratrice
    Integrazione con PLC Siemens S7-1200/S7-1500
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
        self.setWindowTitle("🔧 Polisher / Calibrator Management")
        self.setModal(False)
        
        # Imposta finestra in modalità schermo intero senza bordi né decorazioni
        self.setup_fullscreen_window()
        
        # Inizializza RAG Engine
        if RAG_AVAILABLE:
            self.rag_engine = self.get_rag_engine()
        else:
            self.rag_engine = None
        
        # Storage per dati macchina corrente
        self._current_machine_status = None
        self._plc_config = get_machine(MACHINE_LUCIDATRICE)
        
        # Worker thread per RAG
        self.rag_worker = None
        
        # Inizializza UI
        self.init_ui()
        self.apply_stylesheet()
        
        # Inizializza integrazione PLC
        if PLC_AVAILABLE:
            self.setup_plc_integration()
    
    def setup_fullscreen_window(self):
        """Finestra indipendente con barra titolo e riduzione a icona."""
        from ui.common.window_helpers import apply_machine_section_window

        apply_machine_section_window(self)
    
    def init_ui(self):
        """Inizializza l'interfaccia utente con scroll verticale"""
        # Crea QScrollArea come contenitore principale
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(production_scroll_area_stylesheet())
        
        # Crea widget centrale con layout verticale (senza header, che sarà fuori)
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Contenuto principale (layout a 2 colonne)
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        # Colonna sinistra - Controlli e Parametri
        left_column = self.create_left_column()
        content_layout.addWidget(left_column, 1)
        
        # Colonna destra - Stato e Produzione
        right_column = self.create_right_column()
        content_layout.addWidget(right_column, 1)
        
        main_layout.addWidget(content_widget, 1)
        
        # Tabella Materiale in Lavorazione (sopra Domanda Operativa)
        try:
            from ui.materiale_lavorazione_widget import MaterialeLavorazioneWidget
            self.materiale_widget = MaterialeLavorazioneWidget()
            main_layout.addWidget(self.materiale_widget)
        except ImportError:
            self.materiale_widget = None
        
        # Sezione Domanda Operativa (RAG Engine)
        if RAG_AVAILABLE:
            rag_section = self.create_rag_section()
            main_layout.addWidget(rag_section)
        
        # Imposta il widget centrale nella scroll area
        scroll_area.setWidget(central_widget)
        
        # Crea layout principale per la finestra (header fisso + scroll area + status bar)
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.setSpacing(0)
        
        # Header fisso sopra lo scroll
        header = self.create_header()
        window_layout.addWidget(header, 0)  # 0 = dimensione fissa
        
        # Scroll area
        window_layout.addWidget(scroll_area, 1)  # 1 = si espande
        
        # Barra di stato (fissa, non scrollabile)
        status_bar = self.create_status_bar()
        window_layout.addWidget(status_bar, 0)  # 0 = dimensione fissa
        
        # Salva riferimento per accesso futuro
        self.scroll_area = scroll_area
        self.central_widget = central_widget
    
    def create_header(self):
        """Crea l'header unificato della finestra"""
        header_widget = QWidget()
        header_widget.setFixedHeight(50)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(15)
        
        # Pulsante Dashboard a sinistra
        self.pulsante_dashboard = QPushButton("Dashboard")
        self.pulsante_dashboard.setToolTip("Torna alla finestra principale")
        self.pulsante_dashboard.clicked.connect(self.tornaAllaDashboard)
        header_layout.addWidget(self.pulsante_dashboard)
        
        titolo_sezione = QLabel("Polisher / Calibrator Management")
        header_layout.addWidget(titolo_sezione)
        
        header_layout.addStretch()
        
        self.ordini_btn = QPushButton("Incoming / Production Orders")
        self.ordini_btn.setToolTip("Visualizza ordini inviati a questa macchina")
        self.ordini_btn.clicked.connect(self.open_ordini_window)
        header_layout.addWidget(self.ordini_btn)
        
        configure_production_module_header(
            header_widget, self.pulsante_dashboard, titolo_sezione, self.ordini_btn
        )
        return header_widget
    
    def create_left_column(self):
        """Crea la colonna sinistra con controlli e parametri"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(15)
        
        # Titolo colonna
        title = QLabel("Controls & Parameters")
        title.setStyleSheet(production_section_title_stylesheet())
        column_layout.addWidget(title)
        
        info_group = QGroupBox("Machine Information")
        info_layout = QVBoxLayout(info_group)
        
        self.machine_info_text = QTextEdit()
        self.machine_info_text.setReadOnly(True)
        self.machine_info_text.setPlainText(self._machine_info_plaintext())
        self.machine_info_text.setStyleSheet(production_monospace_field_stylesheet())
        info_layout.addWidget(self.machine_info_text)
        column_layout.addWidget(info_group)
        
        commands_group = QGroupBox("Machine Commands")
        commands_layout = QVBoxLayout(commands_group)
        commands_layout.setContentsMargins(10, 10, 10, 10)
        commands_layout.setSpacing(10)
        
        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_start.setEnabled(False)
        commands_layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_stop.setEnabled(False)
        commands_layout.addWidget(self.btn_stop)
        
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.clicked.connect(self.on_reset_clicked)
        self.btn_reset.setEnabled(False)
        commands_layout.addWidget(self.btn_reset)
        wire_machine_command_buttons(self.btn_start, self.btn_stop, reset=self.btn_reset)
        
        column_layout.addWidget(commands_group)
        
        # Widget Parametri (se disponibili)
        if COMPONENTS_AVAILABLE:
            self.parametri_widget = LucidatriceParametriWidget()
        else:
            # Widget standard
            self.parametri_widget = QGroupBox("Work Parameters")
            parametri_layout = QVBoxLayout(self.parametri_widget)
            self.parametri_text = QTextEdit()
            self.parametri_text.setReadOnly(True)
            self.parametri_text.setMaximumHeight(150)
            self.parametri_text.setPlaceholderText(
                "Speed setpoint: --\n"
                "Pressure setpoint: --\n"
                "Abrasive setpoint: --\n"
                "Work mode: --"
            )
            self.parametri_text.setStyleSheet("""
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
            parametri_layout.addWidget(self.parametri_text)
        
        column_layout.addWidget(self.parametri_widget)
        column_layout.addStretch()
        
        return column_widget
    
    def create_right_column(self):
        """Crea la colonna destra con stato e produzione"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(15)
        
        # Titolo colonna
        title = QLabel("Status & Monitoring")
        title.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        column_layout.addWidget(title)
        
        # Usa componenti modulari se disponibili, altrimenti crea widget standard
        if COMPONENTS_AVAILABLE:
            self.status_widget = LucidatriceStatusWidget()
            self.produzione_widget = LucidatriceProduzioneWidget()
        else:
            # Widget standard per Stato
            self.status_widget = QGroupBox("Machine Status")
            status_layout = QVBoxLayout(self.status_widget)
            self.status_text = QTextEdit()
            self.status_text.setReadOnly(True)
            self.status_text.setMaximumHeight(150)
            self.status_text.setPlaceholderText(
                "Status: STOP\n"
                "Belt speed: --\n"
                "Head pressure: --\n"
                "Motor temperature: --\n"
                "Water consumption: --\n"
                "Alarms: none"
            )
            self.status_text.setStyleSheet("""
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
            status_layout.addWidget(self.status_text)
            
            # Widget standard per Produzione
            self.produzione_widget = QGroupBox("Production")
            produzione_layout = QVBoxLayout(self.produzione_widget)
            self.produzione_text = QTextEdit()
            self.produzione_text.setReadOnly(True)
            self.produzione_text.setMaximumHeight(150)
            self.produzione_text.setPlaceholderText(
                "Meters processed: --\n"
                "Hourly output: --\n"
                "Surface quality: --\n"
                "Piece counter: 0"
            )
            self.produzione_text.setStyleSheet("""
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
            produzione_layout.addWidget(self.produzione_text)
        
        column_layout.addWidget(self.status_widget)
        column_layout.addWidget(self.produzione_widget)
        column_layout.addStretch()
        
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
            "Example: 'Why is belt speed low?'\n"
            "Example: 'What is the current hourly output?'\n"
            "Example: 'Explain the alarm cause'"
        )
        self.question_text.setMaximumHeight(80)
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
                background-color: #2a1a3a;
                border: 1px solid #4a3a5a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a2a4a;
                border: 1px solid #5a4a6a;
            }
            QPushButton:pressed {
                background-color: #1a0a2a;
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
        answer_label = QLabel("Start Agent Analysis:")
        answer_label.setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 14px;")
        rag_layout.addWidget(answer_label)
        
        self.answer_text = QTextEdit()
        self.answer_text.setReadOnly(True)
        self.answer_text.setPlaceholderText("Neural engine answer will appear here...")
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
            "1. INTERPRETAZIONE DELLA DOMANDA\n"
            "2. DATI RILEVANTI TROVATI\n"
            "3. DECISIONE LOGICA\n"
            "4. RISPOSTA FINALE"
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
        self.suggestions_button.setToolTip("Visualizza i suggerimenti generati dal motore neurale e valida le azioni proposte")
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
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(15, 5, 15, 5)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(production_label_stylesheet() + " font-size: 12px;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        # Indicatore connessione PLC
        self.plc_indicator = QLabel("PLC: Offline")
        self.plc_indicator.setStyleSheet(state_indicator_style("alarm"))
        status_layout.addWidget(self.plc_indicator)
        
        # Indicatori stato cognitivo (se RAG disponibile)
        if RAG_AVAILABLE:
            status_layout.addWidget(QLabel("|"))  # Separatore
            
            self.neural_engine_indicator = QLabel("🧠 Neural Engine: Active")
            self.neural_engine_indicator.setStyleSheet(state_indicator_style("ok"))
            status_layout.addWidget(self.neural_engine_indicator)
            
            self.memory_indicator = QLabel("💾 Memory: --")
            self.memory_indicator.setStyleSheet(state_indicator_style("warn"))
            status_layout.addWidget(self.memory_indicator)
            
            self.context_indicator = QLabel("📊 Context: --")
            self.context_indicator.setStyleSheet(state_indicator_style("info"))
            status_layout.addWidget(self.context_indicator)
        
        return status_bar

    def _machine_info_plaintext(self) -> str:
        """Testo box informazioni (IP da config.json / Machines Monitoring)."""
        return (
            "Machine: Marble Polisher/Calibrator\n"
            "Tipo: Lucidatura e calibrazione superfici\n"
            "PLC: Siemens S7-1200/S7-1500\n"
            "Connessione: Snap7 (porta S7 da config)\n"
            f"{describe_plc_endpoint(self._plc_config)}\n"
            "Config: Machines Monitoring → Salva"
        )

    def _apply_plc_config_to_ui(self) -> None:
        self._plc_config = get_machine(MACHINE_LUCIDATRICE)
        if hasattr(self, "machine_info_text"):
            self.machine_info_text.setPlainText(self._machine_info_plaintext())

    def setup_plc_integration(self):
        """Configura l'integrazione con il PLC - Pattern identico a Multifilo"""
        if not PLC_AVAILABLE:
            self.status_label.setText("PLC unavailable — offline mode")
            if hasattr(self, 'plc_indicator'):
                self.plc_indicator.setText("PLC: Unavailable")
            return

        self._plc_config = get_machine(MACHINE_LUCIDATRICE)
        cfg = self._plc_config
        self._apply_plc_config_to_ui()

        try:
            if PLC_SNAP7:
                self.lucidatrice_updater = LucidatriceSnap7Updater(
                    plc_ip=cfg["ip"],
                    rack=cfg["rack"],
                    slot=cfg["slot"],
                    parent=self,
                )
            else:
                self.lucidatrice_updater = LucidatriceUIUpdater(
                    plc_ip=cfg["ip"],
                    db_number=2,
                    parent=self,
                )
            
            # Collega il segnale di aggiornamento
            self.lucidatrice_updater.status_updated.connect(self.on_lucidatrice_status_updated)
            
            # Collega segnale connessione
            if hasattr(self.lucidatrice_updater, 'connection_changed'):
                self.lucidatrice_updater.connection_changed.connect(self.on_plc_connection_changed)
            
            # Avvia l'aggiornamento automatico (200ms per Snap7, 100ms per Rust)
            interval = 200 if PLC_SNAP7 else 100
            self.lucidatrice_updater.start(interval_ms=interval)
        except Exception as e:
            print(f"⚠ Errore configurazione PLC: {e}")
            if hasattr(self, 'status_label'):
                self.status_label.setText(f"PLC connection error: {e}")
            if hasattr(self, 'plc_indicator'):
                self.plc_indicator.setText("PLC: Error")
            QMessageBox.warning(
                self,
                "PLC Error",
                f"Impossibile connettersi al PLC:\n{e}\n\n"
                f"Assicurati che il server Snap7 sia in esecuzione:\n"
                f"python snap7_lucidatrice_server.py"
            )
    
    def on_lucidatrice_status_updated(self, status):
        """Callback chiamato quando i dati PLC sono aggiornati - Pattern identico a Multifilo"""
        # Salva stato corrente per RAG Engine
        self._current_machine_status = status
        
        # Aggiorna indicatori contesto
        if RAG_AVAILABLE and hasattr(self, 'context_indicator'):
            self.context_indicator.setText("📊 Context: Built")
            self.context_indicator.setStyleSheet(state_indicator_style("ok"))
        
        # Aggiorna tabella materiale
        if hasattr(self, 'materiale_widget') and self.materiale_widget is not None:
            if PLC_SNAP7 and isinstance(status, LucidatriceStatus):
                self.materiale_widget.update_materiale(
                    materiale=status.materiale,
                    quantita_lastre=status.quantita_lastre,
                    spessore=status.spessore,
                    finitura=status.finitura,
                    colore_tipo=status.colore_tipo,
                    cliente_commessa=status.cliente_commessa,
                    stato_avanzamento=status.avanzamento,
                    tempo_stimato=status.tempo_stimato,
                    tempo_rimanente=status.tempo_residuo
                )
        
        # Aggiorna UI in base al tipo di status
        if PLC_SNAP7 and isinstance(status, LucidatriceStatus):
            # Status Snap7 - Pattern identico a Multifilo
            if COMPONENTS_AVAILABLE:
                # Usa componenti modulari
                self.status_widget.update_status(
                    stato_macchina=status.stato,
                    velocita_nastro=status.velocita_nastro,
                    velocita_trave=status.velocita_trave,
                    pressione_teste=status.pressione_testine,
                    contropressione_teste=status.contropressione_teste,
                    temperatura_motori=status.temperatura_motori,
                    consumo_acqua=status.consumo_acqua,
                    allarmi=status.allarmi
                )
                self.produzione_widget.update_produzione(
                    metri_lavorati=status.metri_lavorati,
                    produzione_ora=status.produzione_oraria,  # Disponibile in Snap7
                    qualita_superficie=status.qualita_superficie,
                    contatore_pezzi=status.contatore_pezzi  # Disponibile in Snap7
                )
                self.parametri_widget.update_parametri(
                    setpoint_velocita=None,  # Non disponibile in Snap7
                    setpoint_pressione=None,  # Non disponibile in Snap7
                    setpoint_abrasivi=None,  # Non disponibile in Snap7
                    modalita_lavoro=None,  # Non disponibile in Snap7
                    posizione_trave=status.posizione_trave,
                    velocita_nastro=status.velocita_nastro,
                    pressione_testine=status.pressione_testine,
                    assorbimento_motore_principale=status.assorbimento_motore_principale,
                    assorbimento_motore_nastro=status.assorbimento_motore_nastro,
                    assorbimento_testine=status.assorbimento_testine,
                    velocita_trave=status.velocita_trave
                )
            else:
                # Usa refresh_lucidatrice_ui per widget standard
                if hasattr(self, 'status_text') and hasattr(self, 'produzione_text'):
                    refresh_lucidatrice_ui(status, self.status_text, self.produzione_text)
        else:
            # Status Rust (compatibilità)
            if COMPONENTS_AVAILABLE:
                self.status_widget.update_status(
                    stato_macchina=getattr(status, 'stato_macchina', None),
                    velocita_nastro=getattr(status, 'velocita_nastro', None),
                    pressione_teste=getattr(status, 'pressione_teste', None),
                    temperatura_motori=getattr(status, 'temperatura_motori', None),
                    consumo_acqua=getattr(status, 'consumo_acqua', None),
                    allarmi=getattr(status, 'allarmi', None)
                )
                self.produzione_widget.update_produzione(
                    metri_lavorati=getattr(status, 'metri_lavorati', None),
                    produzione_ora=getattr(status, 'produzione_oraria', None) or getattr(status, 'produzione_ora', None),
                    qualita_superficie=getattr(status, 'qualita_superficie', None),
                    contatore_pezzi=getattr(status, 'contatore_pezzi', None)
                )
                self.parametri_widget.update_parametri(
                    setpoint_velocita=getattr(status, 'setpoint_velocita', None),
                    setpoint_pressione=getattr(status, 'setpoint_pressione', None),
                    setpoint_abrasivi=getattr(status, 'setpoint_abrasivi', None),
                    modalita_lavoro=getattr(status, 'modalita_lavoro', None)
                )
            else:
                # Usa funzione di refresh standard
                if hasattr(self, 'status_text') and hasattr(self, 'produzione_text') and hasattr(self, 'parametri_text'):
                    refresh_lucidatrice_ui(
                        status,
                        self.status_text,
                        self.produzione_text,
                        self.parametri_text
                    )
    
    def on_plc_connection_changed(self, connected: bool):
        """Callback quando cambia lo stato di connessione PLC - Pattern identico a Multifilo"""
        if hasattr(self, 'plc_indicator'):
            if connected:
                self.plc_indicator.setText("PLC: Online")
                self.plc_indicator.setStyleSheet(state_indicator_style("ok"))
            else:
                self.plc_indicator.setText("PLC: Offline")
                self.plc_indicator.setStyleSheet(state_indicator_style("alarm"))
        
        # Abilita/disabilita pulsanti comandi - Pattern identico a Multifilo
        if hasattr(self, 'btn_start'):
            self.btn_start.setEnabled(connected)
        if hasattr(self, 'btn_stop'):
            self.btn_stop.setEnabled(connected)
        if hasattr(self, 'btn_reset'):
            self.btn_reset.setEnabled(connected)
    
    def on_start_clicked(self):
        """Gestisce il click sul pulsante Start - Pattern identico a Multifilo"""
        if not PLC_AVAILABLE or not hasattr(self, 'lucidatrice_updater'):
            QMessageBox.warning(self, "Error", "PLC unavailable")
            return
        
        if PLC_SNAP7 and hasattr(self.lucidatrice_updater, 'send_start'):
            success = self.lucidatrice_updater.send_start()
            if not success:
                QMessageBox.warning(self, "Error", "Unable to send Start command")
        else:
            QMessageBox.information(self, "Info", "Start command unavailable in offline mode")
    
    def on_stop_clicked(self):
        """Gestisce il click sul pulsante Stop - Pattern identico a Multifilo"""
        if not PLC_AVAILABLE or not hasattr(self, 'lucidatrice_updater'):
            QMessageBox.warning(self, "Error", "PLC unavailable")
            return
        
        if PLC_SNAP7 and hasattr(self.lucidatrice_updater, 'send_stop'):
            success = self.lucidatrice_updater.send_stop()
            if not success:
                QMessageBox.warning(self, "Error", "Unable to send Stop command")
        else:
            QMessageBox.information(self, "Info", "Stop command unavailable in offline mode")
    
    def on_reset_clicked(self):
        """Gestisce il click sul pulsante Reset - Pattern identico a Multifilo"""
        if not PLC_AVAILABLE or not hasattr(self, 'lucidatrice_updater'):
            QMessageBox.warning(self, "Error", "PLC unavailable")
            return
        
        if PLC_SNAP7 and hasattr(self.lucidatrice_updater, 'send_reset'):
            success = self.lucidatrice_updater.send_reset()
            if not success:
                QMessageBox.warning(self, "Error", "Unable to send Reset command")
        else:
            QMessageBox.information(self, "Info", "Reset command unavailable in offline mode")
    
    def build_machine_context(self) -> str:
        """Costruisce il contesto dai dati macchina corrente"""
        if self._current_machine_status is None:
            return "[MACHINE CONTEXT]\nNo machine data available."
        
        status = self._current_machine_status
        context_parts = ["[CONTESTO MACCHINA LUCIDATRICE/CALIBRATRICE]"]
        context_parts.append("")
        
        # Stato macchina
        stato_map = {
            0: "Idle (ferma / in attesa)",
            1: "Run (in lavorazione)",
            2: "Alarm (allarme attivo)",
            3: "Errore testine",
            4: "Errore nastro",
        }
        stato_code = getattr(status, 'stato', None)
        stato_text = stato_map.get(stato_code, f"Sconosciuto ({stato_code})")
        context_parts.append("STATO MACCHINA:")
        context_parts.append(f"  - Stato operativo: {stato_text}")
        context_parts.append(f"  - Connessa al PLC: {'Sì' if getattr(status, 'connessa', False) else 'No'}")
        context_parts.append(f"  - Avanzamento lavorazione: {getattr(status, 'avanzamento', 0.0):.1f}%")
        context_parts.append(f"  - Tempo residuo stimato: {getattr(status, 'tempo_residuo', 0)}s")
        allarmi = getattr(status, 'allarmi', 0)
        context_parts.append(f"  - Allarmi: {'Nessun allarme' if allarmi == 0 else f'Codice allarme: {allarmi}'}")
        context_parts.append(f"  - Emergenza: {'ATTIVA' if getattr(status, 'emergenza', False) else 'No'}")
        context_parts.append(f"  - Pressione fuori range: {'Sì' if getattr(status, 'pressione_fuori_range', False) else 'No'}")
        context_parts.append(f"  - Assorbimento anomalo: {'Sì' if getattr(status, 'assorbimento_anomalo', False) else 'No'}")
        context_parts.append("")
        
        # Parametri operativi (range nominali del processo in RUN)
        context_parts.append("PARAMETRI OPERATIVI (range nominale in RUN tra parentesi):")
        context_parts.append(f"  - Velocità nastro: {getattr(status, 'velocita_nastro', 0.0):.2f} m/min (nominale 5–50 m/min)")
        context_parts.append(f"  - Pressione testine: {getattr(status, 'pressione_testine', 0.0):.2f} bar (nominale 1–10 bar)")
        context_parts.append(f"  - Assorbimento motore principale: {getattr(status, 'assorbimento_motore_principale', 0.0):.2f} A (nominale 3–20 A)")
        context_parts.append(f"  - Assorbimento motore nastro: {getattr(status, 'assorbimento_motore_nastro', 0.0):.2f} A (nominale 2–15 A)")
        context_parts.append(f"  - Assorbimento testine: {getattr(status, 'assorbimento_testine', 0.0):.2f} A (nominale 1–12 A)")
        context_parts.append(f"  - Posizione trave: {getattr(status, 'posizione_trave', 0.0):.1f} mm (corsa 0–3000 mm)")
        context_parts.append(f"  - Velocità trave: {getattr(status, 'velocita_trave', 0.0):.2f} mm/s")
        context_parts.append(f"  - Temperatura motori: {getattr(status, 'temperatura_motori', 0.0):.1f} °C")
        context_parts.append(f"  - Consumo acqua: {getattr(status, 'consumo_acqua', 0.0):.2f} L/min")
        context_parts.append(f"  - Contropressione teste: {getattr(status, 'contropressione_teste', 0.0):.2f} bar")
        context_parts.append("")
        
        # Produzione
        context_parts.append("PRODUZIONE:")
        context_parts.append(f"  - Metri lavorati: {getattr(status, 'metri_lavorati', 0.0):.2f} m")
        context_parts.append(f"  - Produzione oraria: {getattr(status, 'produzione_oraria', 0.0):.2f} m/h")
        context_parts.append(f"  - Qualità superficie: {getattr(status, 'qualita_superficie', 0.0):.2f} %")
        context_parts.append(f"  - Contatore pezzi: {int(getattr(status, 'contatore_pezzi', 0))}")
        context_parts.append("")
        
        # Materiale in lavorazione
        context_parts.append("MATERIALE IN LAVORAZIONE:")
        context_parts.append(f"  - Materiale: {getattr(status, 'materiale', 'N/D')}")
        context_parts.append(f"  - Lastre rimanenti: {getattr(status, 'quantita_lastre', 'N/D')}")
        context_parts.append(f"  - Spessore: {getattr(status, 'spessore', 0.0)} mm")
        context_parts.append(f"  - Finitura: {getattr(status, 'finitura', 'N/D')}")
        context_parts.append("")
        
        last_update = getattr(status, 'ultimo_aggiornamento', None)
        if last_update is not None:
            try:
                context_parts.append(f"Ultimo aggiornamento dati PLC: {last_update.strftime('%H:%M:%S')}")
            except AttributeError:
                context_parts.append(f"Ultimo aggiornamento dati PLC: {last_update}")
            context_parts.append("")
        
        context_parts.append("Nota: in stato Idle è normale che velocità, pressione e assorbimenti tendano a zero.")
        context_parts.append("")
        
        return "\n".join(context_parts)
    
    def on_ask_neural_engine(self):
        """Gestisce la richiesta al motore neurale"""
        from modules.ollama_prewarm import request_production_agent_prewarm

        request_production_agent_prewarm("lucidatrice")
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
                "Inserisci una domanda per il motore neurale."
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
        self.rag_worker = LucidatriceRAGWorker(
            self.rag_engine,
            question,
            machine_context
        )
        self.rag_worker.result_ready.connect(self.on_rag_finished)
        self.rag_worker.error.connect(self.on_rag_error)
        self.rag_worker.start()
    
    def on_rag_finished(self, result):
        """Callback quando la generazione RAG è completata"""
        # Riabilita pulsante
        self.ask_button.setEnabled(True)
        self.ask_button.setText("Agent Analysis")
        
        # Aggiorna indicatori
        if hasattr(self, 'neural_engine_indicator'):
            self.neural_engine_indicator.setText("🧠 Neural Engine: Active")
            self.neural_engine_indicator.setStyleSheet(state_indicator_style("ok"))
        
        if hasattr(self, 'memory_indicator'):
            self.memory_indicator.setText("💾 Memory: Updated")
            self.memory_indicator.setStyleSheet(state_indicator_style("ok"))
        
        # Mostra risposta
        answer = result.get("answer", "Nessuna risposta generata.")
        self.answer_text.setPlainText(answer)
        
        # Mostra reasoning strutturato
        reasoning = result.get("reasoning", "")
        if reasoning:
            self.reasoning_text.setPlainText(reasoning)
        else:
            # Estrai reasoning dalla risposta se presente
            if "INTERPRETAZIONE DELLA DOMANDA" in answer:
                self.reasoning_text.setPlainText(answer)
            else:
                self.reasoning_text.setPlainText("Reasoning unavailable.")
        
        # Mostra contesto se disponibile
        context = result.get("context", "")
        if context:
            # Il contesto è già incluso nella risposta, ma possiamo mostrarlo separatamente se necessario
            pass
    
    def on_rag_error(self, error_msg):
        """Callback quando si verifica un errore nella generazione RAG"""
        # Riabilita pulsante
        self.ask_button.setEnabled(True)
        self.ask_button.setText("Agent Analysis")
        
        # Aggiorna indicatori
        if hasattr(self, 'neural_engine_indicator'):
            self.neural_engine_indicator.setText("🧠 Neural Engine: Error")
            self.neural_engine_indicator.setStyleSheet(state_indicator_style("alarm"))
        
        # Mostra errore
        QMessageBox.critical(
            self,
            "Neural Engine Error",
            f"An error occurred while generating the answer:\n\n{error_msg}"
        )
        
        self.answer_text.setPlainText(f"Errore: {error_msg}")
        self.reasoning_text.setPlainText("Error during reasoning generation.")
    
    def apply_stylesheet(self):
        """Applica tema Production HMI (Flat Metal + ISO)."""
        apply_production_theme(self)
    
    def closeEvent(self, event):
        """Pulizia quando la finestra viene chiusa"""
        if hasattr(self, 'lucidatrice_updater'):
            self.lucidatrice_updater.stop()
        super().closeEvent(event)
    
    def open_ordini_window(self):
        """Apre la finestra ordini in arrivo per questa macchina"""
        if not hasattr(self, 'ordini_window') or self.ordini_window is None:
            self.ordini_window = OrdiniMacchinaWindow("Lucidatrice", self)
        self.ordini_window.show()
        self.ordini_window.raise_()
        self.ordini_window.activateWindow()
    
    def tornaAllaDashboard(self):
        """Porta il focus alla dashboard (finestra macchina resta aperta o in icona)."""
        self.go_back_to_dashboard()
    
    def open_suggestions_window(self):
        """Apre la finestra Suggerimenti Operativi"""
        try:
            from ui.windows.ai.suggerimenti_lucidatrice_window import SuggerimentiLucidatriceWindow
            
            # Passa lo stato macchina corrente e il RAG Engine
            suggestions_window = SuggerimentiLucidatriceWindow(
                machine_status=self._current_machine_status,
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


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = GestioneLucidatriceWindow()
    window.show()
    sys.exit(app.exec_())

