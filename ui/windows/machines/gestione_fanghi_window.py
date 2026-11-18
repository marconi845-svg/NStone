"""
Nstone LLM - Finestra Gestione Fanghi — Depurazione
Interfaccia per gestione e monitoraggio impianto fanghi e filtropressa
Integrazione RAG Engine per assistenza cognitiva
"""
import sys
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTextEdit, QLineEdit, QComboBox,
                             QMessageBox, QGroupBox, QScrollArea, QApplication, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
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
from PyQt5.QtGui import QFont, QColor

# Importa integrazione Fanghi
try:
    from machines.fanghi_simulator_integration import FanghiSimulatorUpdater
    FANGHI_AVAILABLE = True
except ImportError:
    FANGHI_AVAILABLE = False
    print("⚠ Modulo fanghi_simulator_integration non disponibile")

# Importa RAG Engine
try:
    from llm.rag_engine import RAGEngine
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠ Modulo RAG Engine unavailable")


class FanghiRAGWorker(QThread):
    """Worker thread per generare risposte RAG senza bloccare la UI"""
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, rag_engine, question, machine_context):
        super().__init__()
        self.rag_engine = rag_engine
        self.question = question
        self.machine_context = machine_context
    
    def run(self):
        """Esegue la generazione della risposta"""
        try:
            enriched_question = f"""{self.question}

[CONTESTO IMPIANTO FANGHI]
{self.machine_context}
"""
            result = self.rag_engine.generate_answer(
                enriched_question,
                operational=True,
            )
            result["machine_context"] = self.machine_context
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class GestioneFanghiWindow(SectionMainWindow):
    """
    Finestra per gestione e monitoraggio impianto fanghi e filtropressa
    Integrazione RAG Engine per assistenza cognitiva
    """
    
    _rag_engine_instance = None
    
    @classmethod
    def get_rag_engine(cls):
        """Ottiene o crea l'istanza unica del RAG Engine"""
        if cls._rag_engine_instance is None:
            cls._rag_engine_instance = RAGEngine()
        return cls._rag_engine_instance
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.fanghi_updater = None
        self._current_fanghi_status = None
        self.rag_worker = None
        
        self.setWindowTitle("💧 Sludge Treatment")
        self.setMinimumSize(1200, 800)
        
        self.init_ui()
        self.setup_fanghi_integration()
        from ui.common.window_helpers import register_dashboard
        register_dashboard(self, parent)
        self.apply_production_stylesheet()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente con scroll verticale"""
        # Scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(production_scroll_area_stylesheet())
        
        # Widget centrale
        central_widget = QWidget()
        central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        scroll_area.setWidget(central_widget)
        
        # Layout principale
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Sezione A: Sludge Plant Information
        impianto_section = self.create_impianto_section()
        main_layout.addWidget(impianto_section)
        
        # Sezione B: Analisi Fanghi (parametri chimico-fisici)
        analisi_section = self.create_analisi_section()
        main_layout.addWidget(analisi_section)
        
        # Layout a 2 colonne per le sezioni rimanenti
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        # Colonna sinistra
        left_column = QVBoxLayout()
        left_column.setSpacing(15)
        
        # Sezione C: Filter Press Status
        filtropressa_section = self.create_filtropressa_section()
        left_column.addWidget(filtropressa_section)
        
        # Sezione D: Sludge Production
        produzione_section = self.create_produzione_section()
        left_column.addWidget(produzione_section)
        
        left_widget = QWidget()
        left_widget.setLayout(left_column)
        content_layout.addWidget(left_widget, 1)
        
        # Colonna destra
        right_column = QVBoxLayout()
        right_column.setSpacing(15)
        
        # Sezione E: Environmental Alarms
        allarmi_section = self.create_allarmi_section()
        right_column.addWidget(allarmi_section)
        
        # Sezione F: Analysis History
        storico_section = self.create_storico_section()
        right_column.addWidget(storico_section)
        
        right_widget = QWidget()
        right_widget.setLayout(right_column)
        content_layout.addWidget(right_widget, 1)
        
        main_layout.addWidget(content_widget, 1)
        
        # Sezione Domanda Operativa (RAG Engine)
        if RAG_AVAILABLE:
            rag_section = self.create_rag_section()
            main_layout.addWidget(rag_section)
        
        # Container per header + scroll area
        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Header fisso
        header = self.create_header()
        container_layout.addWidget(header, 0)
        
        # Scroll area
        container_layout.addWidget(scroll_area, 1)
        
        self.setCentralWidget(container_widget)
        
        # Status bar
        status_bar_widget = self.create_status_bar()
        self.statusBar().addPermanentWidget(status_bar_widget)
        
        self.scroll_area = scroll_area
        self.central_widget = central_widget
    
    def apply_production_stylesheet(self):
        """Applica tema Production HMI (Flat Metal + ISO)."""
        apply_production_theme(self)

    def create_header(self):
        """Crea l'header unificato della finestra"""
        header_widget = QWidget()
        header_widget.setFixedHeight(50)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(15)
        
        # Titolo
        title_label = QLabel("Sludge Treatment")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        dashboard_btn = QPushButton("Dashboard")
        dashboard_btn.clicked.connect(self.go_back_to_dashboard)
        header_layout.addWidget(dashboard_btn)
        
        configure_production_module_header(header_widget, dashboard_btn, title_label)
        return header_widget
    
    def create_impianto_section(self):
        """Sezione A: Sludge Plant Information"""
        group = QGroupBox("Sludge Plant Information")
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        info_text = QLabel("""
        <b>Sludge Treatment Plant</b><br>
        • Tank capacity: 100 m³<br>
        • Filter press type: Automatic plate type<br>
        • Number of plates: 50<br>
        • Max pressure: 15 bar<br>
        • Cycle volume: 2.5 m³<br>
        • Water recycling system: Active
        """)
        info_text.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 12px;")
        layout.addWidget(info_text)
        
        return group
    
    def create_analisi_section(self):
        """Sezione B: Analisi Fanghi (parametri chimico-fisici)"""
        group = QGroupBox("Sludge Analysis — Physico-Chemical Parameters")
        
        layout = QVBoxLayout(group)
        
        # Usa il widget analisi fanghi esistente
        try:
            from ui.analisi_fanghi_widget import AnalisiFanghiWidget
            self.analisi_widget = AnalisiFanghiWidget()
            layout.addWidget(self.analisi_widget)
        except ImportError:
            self.analisi_widget = None
            placeholder = QLabel("Sludge Analysis widget unavailable")
            placeholder.setStyleSheet("color: #888888;")
            layout.addWidget(placeholder)
        
        return group
    
    def create_filtropressa_section(self):
        """Sezione C: Filter Press Status"""
        group = QGroupBox("Filter Press Status")
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # Stato
        self.stato_label = QLabel("Status: --")
        self.stato_label.setStyleSheet(production_label_stylesheet(bold=True) + " font-size: 16px;")
        layout.addWidget(self.stato_label)
        
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)
        
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.on_start_clicked)
        controls_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        controls_layout.addWidget(self.stop_btn)
        
        self.hold_btn = QPushButton("Hold")
        self.hold_btn.clicked.connect(self.on_hold_clicked)
        controls_layout.addWidget(self.hold_btn)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.on_reset_clicked)
        controls_layout.addWidget(self.reset_btn)
        wire_machine_command_buttons(
            self.start_btn, self.stop_btn, hold=self.hold_btn, reset=self.reset_btn
        )
        
        layout.addLayout(controls_layout)
        
        return group
    
    def create_produzione_section(self):
        """Sezione D: Sludge Production"""
        group = QGroupBox("Sludge Production")
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # Parametri produzione
        self.volume_label = QLabel("Volume produced: -- m³/day")
        self.volume_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 12px;")
        layout.addWidget(self.volume_label)
        
        self.cicli_label = QLabel("Cycles completed: --")
        self.cicli_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 12px;")
        layout.addWidget(self.cicli_label)
        
        self.tempo_ciclo_label = QLabel("Average cycle time: -- min")
        self.tempo_ciclo_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 12px;")
        layout.addWidget(self.tempo_ciclo_label)
        
        return group
    
    def create_allarmi_section(self):
        """Sezione E: Environmental Alarms"""
        group = QGroupBox("Environmental Alarms")
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        self.allarme_label = QLabel("No active alarms")
        self.allarme_label.setStyleSheet(state_indicator_style("ok"))
        layout.addWidget(self.allarme_label)
        
        return group
    
    def create_storico_section(self):
        """Sezione F: Analysis History"""
        group = QGroupBox("Analysis History")
        
        layout = QVBoxLayout(group)
        
        # Tabella storico
        self.storico_table = QTableWidget(0, 4)
        self.storico_table.setHorizontalHeaderLabels(["Date/Time", "Moisture %", "pH", "Volume m³"])
        self.storico_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.storico_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.storico_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #4a4a5a;
                color: #FFFFFF;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 5px;
                border: none;
            }
        """)
        layout.addWidget(self.storico_table)
        
        return group
    
    def create_rag_section(self):
        """Sezione Domanda Operativa (RAG Engine) - Struttura a 3 blocchi"""
        group = QGroupBox("💬 Operational Question — Neural Engine")
        
        # Layout orizzontale per i 3 blocchi
        main_layout = QHBoxLayout(group)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # ============================================================
        # BOX SINISTRO — "Values to Analyze"
        # ============================================================
        valori_box = QGroupBox("Values to Analyze")
        valori_layout = QVBoxLayout(valori_box)
        valori_layout.setSpacing(8)
        
        # Umidità residua
        umidita_layout = QHBoxLayout()
        umidita_label = QLabel("Residual moisture (%):")
        umidita_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")
        umidita_layout.addWidget(umidita_label)
        self.rag_umidita = QLineEdit()
        self.rag_umidita.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
        """)
        umidita_layout.addWidget(self.rag_umidita)
        valori_layout.addLayout(umidita_layout)
        
        # Densità fango
        densita_layout = QHBoxLayout()
        densita_label = QLabel("Sludge density (kg/m³):")
        densita_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")
        densita_layout.addWidget(densita_label)
        self.rag_densita = QLineEdit()
        self.rag_densita.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
        """)
        densita_layout.addWidget(self.rag_densita)
        valori_layout.addLayout(densita_layout)
        
        # Granulometria media
        granulometria_layout = QHBoxLayout()
        granulometria_label = QLabel("Average particle size (µm):")
        granulometria_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")
        granulometria_layout.addWidget(granulometria_label)
        self.rag_granulometria = QLineEdit()
        self.rag_granulometria.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
        """)
        granulometria_layout.addWidget(self.rag_granulometria)
        valori_layout.addLayout(granulometria_layout)
        
        # pH
        ph_layout = QHBoxLayout()
        ph_label = QLabel("pH:")
        ph_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")
        ph_layout.addWidget(ph_label)
        self.rag_ph = QLineEdit()
        self.rag_ph.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
        """)
        ph_layout.addWidget(self.rag_ph)
        valori_layout.addLayout(ph_layout)
        
        # Volume fanghi prodotti
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Sludge volume (m³/day):")
        volume_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")
        volume_layout.addWidget(volume_label)
        self.rag_volume = QLineEdit()
        self.rag_volume.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
        """)
        volume_layout.addWidget(self.rag_volume)
        valori_layout.addLayout(volume_layout)
        
        # Tempo ciclo filtropressa
        tempo_ciclo_layout = QHBoxLayout()
        tempo_ciclo_label = QLabel("Filter press cycle time (min):")
        tempo_ciclo_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")
        tempo_ciclo_layout.addWidget(tempo_ciclo_label)
        self.rag_tempo_ciclo = QLineEdit()
        self.rag_tempo_ciclo.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
        """)
        tempo_ciclo_layout.addWidget(self.rag_tempo_ciclo)
        valori_layout.addLayout(tempo_ciclo_layout)
        
        # Stato filtropressa
        stato_layout = QHBoxLayout()
        stato_label = QLabel("Filter press status:")
        stato_label.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 11px; min-width: 150px;")
        stato_layout.addWidget(stato_label)
        self.rag_stato = QComboBox()
        self.rag_stato.addItems(["RUN", "HOLD", "ERROR", "READY", "STOP"])
        self.rag_stato.setStyleSheet("""
            QComboBox {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a3a;
                color: #FFFFFF;
                selection-background-color: #4a4a5a;
            }
        """)
        stato_layout.addWidget(self.rag_stato)
        valori_layout.addLayout(stato_layout)
        
        valori_layout.addStretch()
        main_layout.addWidget(valori_box, 1)
        
        # ============================================================
        # BOX CENTRALE — PULSANTE "Analizza"
        # ============================================================
        analizza_container = QWidget()
        analizza_layout = QVBoxLayout(analizza_container)
        analizza_layout.setAlignment(Qt.AlignCenter)
        
        self.analizza_btn = QPushButton("Analyze")
        self.analizza_btn.setMinimumSize(100, 150)
        self.analizza_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a1a3a;
                color: #FFFFFF;
                border: 2px solid #4a3a5a;
                border-radius: 8px;
                padding: 15px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a2a4a;
                border: 2px solid #5a4a6a;
            }
            QPushButton:pressed {
                background-color: #1a0a2a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border: 2px solid #3a3a3a;
            }
        """)
        self.analizza_btn.clicked.connect(self.on_analizza_clicked)
        self.analizza_btn.setEnabled(False)  # Disabilitato inizialmente
        analizza_layout.addWidget(self.analizza_btn)
        
        main_layout.addWidget(analizza_container, 0)
        
        # ============================================================
        # BOX DESTRO — "Neural Analysis Results"
        # ============================================================
        risultati_box = QGroupBox("Neural Analysis Results")
        risultati_layout = QVBoxLayout(risultati_box)
        
        self.rag_output = QTextEdit()
        self.rag_output.setReadOnly(True)
        self.rag_output.setPlaceholderText(
            "Neural analysis results will appear here after you press 'Analyze'..."
        )
        self.rag_output.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                color: #CCCCCC;
                border: 1px solid #4a4a5a;
                border-radius: 5px;
                padding: 10px;
                font-size: 11px;
                min-height: 300px;
            }
        """)
        risultati_layout.addWidget(self.rag_output)
        
        main_layout.addWidget(risultati_box, 1)
        
        # Collega i campi input per abilitare/disabilitare il pulsante
        self.rag_umidita.textChanged.connect(self.check_analizza_enabled)
        self.rag_densita.textChanged.connect(self.check_analizza_enabled)
        self.rag_granulometria.textChanged.connect(self.check_analizza_enabled)
        self.rag_ph.textChanged.connect(self.check_analizza_enabled)
        self.rag_volume.textChanged.connect(self.check_analizza_enabled)
        self.rag_tempo_ciclo.textChanged.connect(self.check_analizza_enabled)
        
        return group
    
    def create_status_bar(self):
        """Crea la barra di stato"""
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(5, 5, 5, 5)
        status_layout.setSpacing(15)
        
        self.fanghi_status_label = QLabel("Sludge: Disconnected")
        self.fanghi_status_label.setStyleSheet(production_label_stylesheet(variant="muted") + " font-size: 11px;")
        status_layout.addWidget(self.fanghi_status_label)
        
        status_layout.addStretch()
        
        return status_widget
    
    def setup_fanghi_integration(self):
        """Configura integrazione simulatore fanghi"""
        if not FANGHI_AVAILABLE:
            print("⚠ Integrazione Fanghi non disponibile")
            return
        
        try:
            self.fanghi_updater = FanghiSimulatorUpdater(parent=self)
            self.fanghi_updater.status_updated.connect(self.on_fanghi_status_updated)
            self.fanghi_updater.connection_changed.connect(self.on_fanghi_connection_changed)
            self.fanghi_updater.start(interval_ms=100)
        except Exception as e:
            print(f"⚠ Errore setup integrazione fanghi: {e}")
    
    def on_fanghi_status_updated(self, status):
        """Aggiorna UI con nuovo stato fanghi"""
        self._current_fanghi_status = status
        
        # Aggiorna widget analisi
        if hasattr(self, 'analisi_widget') and self.analisi_widget is not None:
            self.analisi_widget.update_analisi(
                umidita_residua=status.get("umidita_residua"),
                densita_fango=status.get("densita_fango"),
                granulometria_media=status.get("granulometria_media"),
                ph=status.get("ph"),
                volume_fanghi_prodotti=status.get("volume_fanghi_prodotti"),
                cicli_filtropressa=status.get("cicli_filtropressa"),
                tempo_ciclo_medio=status.get("tempo_ciclo_medio"),
                stato_filtropressa=status.get("stato_filtropressa"),
                qualita_acqua_riciclata=status.get("qualita_acqua_riciclata")
            )
        
        # Sincronizza valori nel box "Values to Analyze" se non modificati dall'utente
        # Solo se i campi sono vuoti o contengono valori identici (per non sovrascrivere input utente)
        if hasattr(self, 'rag_umidita'):
            if not self.rag_umidita.text().strip() or self.rag_umidita.text().strip() == str(status.get("umidita_residua", 0)):
                self.rag_umidita.setText(f"{status.get('umidita_residua', 0):.1f}")
        
        if hasattr(self, 'rag_densita'):
            if not self.rag_densita.text().strip() or self.rag_densita.text().strip() == str(status.get("densita_fango", 0)):
                self.rag_densita.setText(f"{status.get('densita_fango', 0):.1f}")
        
        if hasattr(self, 'rag_granulometria'):
            if not self.rag_granulometria.text().strip() or self.rag_granulometria.text().strip() == str(status.get("granulometria_media", 0)):
                self.rag_granulometria.setText(f"{status.get('granulometria_media', 0):.1f}")
        
        if hasattr(self, 'rag_ph'):
            if not self.rag_ph.text().strip() or self.rag_ph.text().strip() == str(status.get("ph", 0)):
                self.rag_ph.setText(f"{status.get('ph', 0):.2f}")
        
        if hasattr(self, 'rag_volume'):
            if not self.rag_volume.text().strip() or self.rag_volume.text().strip() == str(status.get("volume_fanghi_prodotti", 0)):
                self.rag_volume.setText(f"{status.get('volume_fanghi_prodotti', 0):.2f}")
        
        if hasattr(self, 'rag_tempo_ciclo'):
            if not self.rag_tempo_ciclo.text().strip() or self.rag_tempo_ciclo.text().strip() == str(status.get("tempo_ciclo_medio", 0)):
                self.rag_tempo_ciclo.setText(f"{status.get('tempo_ciclo_medio', 0)}")
        
        if hasattr(self, 'rag_stato'):
            stato_sim = status.get("stato_filtropressa", "READY")
            if self.rag_stato.currentText() == stato_sim or not self.rag_stato.currentText():
                index = self.rag_stato.findText(stato_sim)
                if index >= 0:
                    self.rag_stato.setCurrentIndex(index)
        
        # Aggiorna stato filtropressa
        stato = status.get("stato_filtropressa", "--")
        if stato == "RUN":
            self.stato_label.setText(f"Status: <span style='color: #00FF00;'>{stato}</span>")
        elif stato == "ERROR":
            self.stato_label.setText(f"Status: <span style='color: #FF0000;'>{stato}</span>")
        else:
            self.stato_label.setText(f"Status: <span style='color: #FFFF00;'>{stato}</span>")
        
        # Aggiorna produzione
        self.volume_label.setText(
            f"Volume produced: {status.get('volume_fanghi_prodotti', 0):.2f} m³/day"
        )
        self.cicli_label.setText(f"Cycles completed: {status.get('cicli_filtropressa', 0)}")
        self.tempo_ciclo_label.setText(
            f"Average cycle time: {status.get('tempo_ciclo_medio', 0)} min"
        )
        
        # Aggiorna allarmi
        alarm_code = status.get("alarm_code", 0)
        alarm_message = status.get("alarm_message", "")
        if alarm_code > 0:
            self.allarme_label.setText(
                f"<span style='color: #FF0000;'>⚠ Alarm {alarm_code}: {alarm_message}</span>"
            )
        else:
            self.allarme_label.setText("<span style='color: #00FF00;'>No active alarms</span>")
        
        # Verifica se pulsante Analizza deve essere disabilitato (stato ERROR)
        if hasattr(self, 'analizza_btn'):
            self.check_analizza_enabled()
    
    def on_fanghi_connection_changed(self, connected):
        """Gestisce cambio stato connessione"""
        if connected:
            self.fanghi_status_label.setText("Sludge: Connected")
            self.fanghi_status_label.setStyleSheet("color: #00FF00; font-size: 11px;")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            self.hold_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
        else:
            self.fanghi_status_label.setText("Sludge: Disconnected")
            self.fanghi_status_label.setStyleSheet(production_label_stylesheet(variant="muted") + " font-size: 11px;")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.hold_btn.setEnabled(False)
            self.reset_btn.setEnabled(False)
    
    def on_start_clicked(self):
        """Comando Start filtropressa"""
        if self.fanghi_updater:
            self.fanghi_updater.send_start()
    
    def on_stop_clicked(self):
        """Comando Stop filtropressa"""
        if self.fanghi_updater:
            self.fanghi_updater.send_stop()
    
    def on_hold_clicked(self):
        """Comando Hold filtropressa"""
        if self.fanghi_updater:
            self.fanghi_updater.send_hold()
    
    def on_reset_clicked(self):
        """Comando Reset filtropressa"""
        if self.fanghi_updater:
            self.fanghi_updater.send_reset()
    
    def check_analizza_enabled(self):
        """Abilita/disabilita pulsante Analizza in base ai valori inseriti"""
        has_values = (
            self.rag_umidita.text().strip() or
            self.rag_densita.text().strip() or
            self.rag_granulometria.text().strip() or
            self.rag_ph.text().strip() or
            self.rag_volume.text().strip() or
            self.rag_tempo_ciclo.text().strip()
        )
        
        # Disabilita anche se stato filtropressa è ERROR
        stato_error = self.rag_stato.currentText() == "ERROR"
        
        self.analizza_btn.setEnabled(has_values and not stato_error)
    
    def on_analizza_clicked(self):
        """Esegue analisi neurale dei valori inseriti"""
        if not RAG_AVAILABLE:
            QMessageBox.warning(self, "RAG Engine", "RAG Engine unavailable")
            return
        
        # Raccogli valori dal box sinistro
        umidita = self.rag_umidita.text().strip()
        densita = self.rag_densita.text().strip()
        granulometria = self.rag_granulometria.text().strip()
        ph = self.rag_ph.text().strip()
        volume = self.rag_volume.text().strip()
        tempo_ciclo = self.rag_tempo_ciclo.text().strip()
        stato = self.rag_stato.currentText()
        
        # Costruisci domanda contestuale
        question = f"""Analizza i seguenti parametri dell'impianto fanghi e fornisci:
1. Diagnosi dello stato attuale
2. Suggerimenti operativi
3. Eventuali allarmi da considerare
4. Consigli di ottimizzazione per il ciclo filtropressa

Parametri:
- Umidità residua: {umidita if umidita else 'N/A'} %
- Densità fango: {densita if densita else 'N/A'} kg/m³
- Granulometria media: {granulometria if granulometria else 'N/A'} µm
- pH: {ph if ph else 'N/A'}
- Volume fanghi prodotti: {volume if volume else 'N/A'} m³/giorno
- Tempo ciclo filtropressa: {tempo_ciclo if tempo_ciclo else 'N/A'} min
- Filter press status: {stato}"""
        
        # Disabilita pulsante durante elaborazione
        self.analizza_btn.setEnabled(False)
        self.rag_output.setPlainText("Processing...")
        
        # Costruisci contesto macchina completo
        machine_context = self.build_machine_context_from_inputs(
            umidita, densita, granulometria, ph, volume, tempo_ciclo, stato
        )
        
        # Crea worker RAG
        rag_engine = self.get_rag_engine()
        self.rag_worker = FanghiRAGWorker(rag_engine, question, machine_context)
        self.rag_worker.result_ready.connect(self.on_rag_finished)
        self.rag_worker.error.connect(self.on_rag_error)
        self.rag_worker.start()
    
    def on_rag_send(self):
        """Invia domanda al RAG Engine (metodo legacy, mantenuto per compatibilità)"""
        if not RAG_AVAILABLE:
            QMessageBox.warning(self, "RAG Engine", "RAG Engine unavailable")
            return
        
        question = self.rag_input.toPlainText().strip()
        if not question:
            return
        
        # Disabilita input durante elaborazione
        self.rag_input.setEnabled(False)
        self.rag_output.setPlainText("Processing...")
        
        # Costruisci contesto macchina
        machine_context = self.build_machine_context()
        
        # Crea worker RAG
        rag_engine = self.get_rag_engine()
        self.rag_worker = FanghiRAGWorker(rag_engine, question, machine_context)
        self.rag_worker.result_ready.connect(self.on_rag_finished)
        self.rag_worker.error.connect(self.on_rag_error)
        self.rag_worker.start()
    
    def build_machine_context(self):
        """Costruisce il contesto impianto fanghi per il RAG Engine (da simulazione)"""
        if self._current_fanghi_status is None:
            return "[IMPIANTO FANGHI]\nNessun dato disponibile."
        
        status = self._current_fanghi_status
        context_parts = ["[IMPIANTO FANGHI - DEPURAZIONE]"]
        context_parts.append("")
        context_parts.append("ANALISI FANGHI:")
        context_parts.append(f"  - Umidità residua: {status.get('umidita_residua', 0):.1f} %")
        context_parts.append(f"  - Densità fango: {status.get('densita_fango', 0):.1f} kg/m³")
        context_parts.append(f"  - Granulometria media: {status.get('granulometria_media', 0):.1f} µm")
        context_parts.append(f"  - pH: {status.get('ph', 0):.2f}")
        context_parts.append(f"  - Qualità acqua riciclata: {status.get('qualita_acqua_riciclata', 0):.1f} %")
        context_parts.append("")
        context_parts.append("PRODUZIONE:")
        context_parts.append(f"  - Volume fanghi prodotti: {status.get('volume_fanghi_prodotti', 0):.2f} m³/giorno")
        context_parts.append(f"  - Cicli filtropressa: {status.get('cicli_filtropressa', 0)}")
        context_parts.append(f"  - Tempo ciclo medio: {status.get('tempo_ciclo_medio', 0)} min")
        context_parts.append("")
        context_parts.append("STATO FILTROPRESSA:")
        context_parts.append(f"  - Status: {status.get('stato_filtropressa', '--')}")
        context_parts.append(f"  - Stato macchina: {status.get('machine_state', '--')}")
        context_parts.append("")
        
        alarm_code = status.get("alarm_code", 0)
        if alarm_code > 0:
            context_parts.append(f"ALLARME: Codice {alarm_code} - {status.get('alarm_message', '')}")
        else:
            context_parts.append("Alarms: None")
        
        return "\n".join(context_parts)
    
    def build_machine_context_from_inputs(self, umidita, densita, granulometria, ph, volume, tempo_ciclo, stato):
        """Costruisce il contesto impianto fanghi dai valori inseriti dall'utente"""
        context_parts = ["[IMPIANTO FANGHI - DEPURAZIONE - VALORI ANALIZZATI]"]
        context_parts.append("")
        context_parts.append("ANALISI FANGHI (Valori inseriti dall'operatore):")
        context_parts.append(f"  - Umidità residua: {umidita if umidita else 'N/A'} %")
        context_parts.append(f"  - Densità fango: {densita if densita else 'N/A'} kg/m³")
        context_parts.append(f"  - Granulometria media: {granulometria if granulometria else 'N/A'} µm")
        context_parts.append(f"  - pH: {ph if ph else 'N/A'}")
        context_parts.append(f"  - Volume fanghi prodotti: {volume if volume else 'N/A'} m³/giorno")
        context_parts.append(f"  - Tempo ciclo filtropressa: {tempo_ciclo if tempo_ciclo else 'N/A'} min")
        context_parts.append("")
        context_parts.append("STATO FILTROPRESSA:")
        context_parts.append(f"  - Status: {stato}")
        context_parts.append("")
        
        # Aggiungi anche dati simulazione se disponibili per contesto completo
        if self._current_fanghi_status:
            status = self._current_fanghi_status
            context_parts.append("CONTESTO AGGIUNTIVO (Simulazione):")
            context_parts.append(f"  - Qualità acqua riciclata: {status.get('qualita_acqua_riciclata', 0):.1f} %")
            context_parts.append(f"  - Cicli filtropressa totali: {status.get('cicli_filtropressa', 0)}")
            alarm_code = status.get("alarm_code", 0)
            if alarm_code > 0:
                context_parts.append(f"  - Allarme attivo: Codice {alarm_code} - {status.get('alarm_message', '')}")
        
        return "\n".join(context_parts)
    
    def on_rag_finished(self, result):
        """Gestisce completamento RAG"""
        self.analizza_btn.setEnabled(True)
        self.check_analizza_enabled()  # Riabilita se necessario
        
        answer = result.get("answer", "Nessuna risposta generata")
        reasoning = result.get("reasoning", "")
        
        output_text = f"{answer}\n\n"
        if reasoning:
            output_text += f"[Ragionamento]\n{reasoning}\n"
        
        self.rag_output.setPlainText(output_text)
    
    def on_rag_error(self, error_msg):
        """Gestisce errore RAG"""
        self.analizza_btn.setEnabled(True)
        self.check_analizza_enabled()  # Riabilita se necessario
        self.rag_output.setPlainText(f"Errore: {error_msg}")
    
    def closeEvent(self, event):
        """Gestisce chiusura finestra"""
        if self.fanghi_updater:
            self.fanghi_updater.stop()
        if self.rag_worker:
            self.rag_worker.terminate()
            self.rag_worker.wait(1000)
        event.accept()

