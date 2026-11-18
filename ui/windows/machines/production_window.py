"""
Nstone LLM - Finestra Production
Gestione produzione e macchine
"""
import os
import sys
import csv
from pathlib import Path
from datetime import datetime
from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from ui.common.window_helpers import show_auxiliary_window
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTableWidget, 
                             QTableWidgetItem, QLineEdit, QHeaderView, QTextEdit,
                             QListWidget, QRadioButton, QButtonGroup, QGridLayout,
                             QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
from pathlib import Path
import shutil
from core.session_manager import create_simple_session
from llm.gemini_service import GeminiService


class ExportAnalysisDialog(SectionDialog):
    """Dialog per esportare e copiare l'analisi"""
    
    def __init__(self, parent=None, analysis_text=""):
        super().__init__(parent)
        self.setWindowTitle("Export Analysis")
        self.setMinimumSize(800, 600)
        self.analysis_text = analysis_text
        self.init_ui()
        self.apply_stylesheet()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Titolo
        title_label = QLabel("Esporta Analisi")
        title_label.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            }
        """)
        main_layout.addWidget(title_label)
        
        # Descrizione
        desc_label = QLabel("Copia il testo dell'analisi utilizzando Ctrl+C o il menu contestuale")
        desc_label.setStyleSheet("color: #B0B0B0; font-size: 12px; background: transparent;")
        main_layout.addWidget(desc_label)
        
        # Area testo copiabile
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)  # Solo lettura, ma permette selezione e copia
        self.text_edit.setPlainText(self.analysis_text)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(20, 20, 30, 200);
                border: 1px solid rgba(179, 211, 255, 100);
                border-radius: 8px;
                color: #E8E8E8;
                font-size: 12px;
                font-family: 'Courier New', monospace;
                padding: 15px;
            }
            QTextEdit::selection {
                background-color: rgba(0, 217, 255, 150);
                color: #0A0A15;
            }
        """)
        main_layout.addWidget(self.text_edit, 1)
        
        # Barra bottoni
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        # Bottone Copia Tutto
        copy_all_btn = QPushButton("Copia Tutto")
        copy_all_btn.setMinimumHeight(40)
        copy_all_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 217, 255, 150);
                color: #0A0A15;
                border: 1px solid rgba(0, 217, 255, 200);
                border-radius: 8px;
                padding: 10px 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 217, 255, 200);
                border: 1px solid rgba(0, 217, 255, 255);
            }
            QPushButton:pressed {
                background-color: rgba(0, 180, 220, 200);
            }
        """)
        copy_all_btn.clicked.connect(self.copy_all_text)
        buttons_layout.addWidget(copy_all_btn)
        
        # Bottone Chiudi
        close_btn = QPushButton("Chiudi")
        close_btn.setMinimumHeight(40)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(23, 147, 209, 120);
                color: #E8E8E8;
                border: 1px solid rgba(0, 217, 255, 100);
                border-radius: 8px;
                padding: 10px 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(23, 147, 209, 180);
                border: 1px solid rgba(0, 217, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(15, 76, 117, 180);
            }
        """)
        close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(close_btn)
        
        main_layout.addLayout(buttons_layout)
    
    def copy_all_text(self):
        """Copia tutto il testo nella clipboard"""
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
    
    def apply_stylesheet(self):
        """Applica lo stylesheet con tema scuro"""
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
            QWidget {
                background: transparent;
            }
        """)


class ProductionWindow(SectionDialog):
    """Finestra Production per gestione produzione e macchine"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Production")
        self.setMinimumSize(1600, 900)
        self.setModal(False)
        
        # Cartella CSV
        self.csv_dir = Path(__file__).parent / "csv_data"
        self.csv_dir.mkdir(exist_ok=True)
        self.csv_file = self.csv_dir / "production.csv"
        
        # Gestione foto caricate (path per ogni slot)
        self.loaded_photo_paths = [None] * 4
        
        # Sessione corrente
        self.current_session_dir = None
        
        # Servizio Gemini
        self.gemini_service = GeminiService()
        
        # Inizializza CSV se non esiste
        self.init_csv_file()
        
        # Inizializza UI prima di caricare i dati
        self.init_ui()
        # Carica i dati CSV dopo che la UI è stata creata
        self.load_csv_data()
        self.apply_stylesheet()
        
    def init_csv_file(self):
        """Inizializza il file CSV con le intestazioni se non esiste"""
        if not self.csv_file.exists() or os.path.getsize(self.csv_file) == 0:
            headers = ["Machine", "Status", "Current Work", "Completion", "Efficiency", "Consumption"]
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                # Aggiungi riga di test
                writer.writerow(["Linea Taglio 01", "Attivo", "Blocco Calacatta #2847", "68", "93.9", "45.2"])
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        # Crea machines_table prima di qualsiasi altra cosa per evitare AttributeError
        self.machines_table = QTableWidget()
        self.machines_table.setColumnCount(6)
        self.machines_table.setHorizontalHeaderLabels([
            "Machine", "Status", "Current Work", "Completion (%)", "Efficiency (%)", "Consumption (kWh)"
        ])
        self.machines_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
            }
            QTableWidget::item {
                padding: 12px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #4a2a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 12px;
                border: none;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        self.machines_table.horizontalHeader().setStretchLastSection(True)
        self.machines_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.machines_table.setAlternatingRowColors(True)
        self.machines_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Font moderno
        font = QFont()
        font_families = ["Montserrat", "Roboto", "Open Sans", "Segoe UI", "Arial"]
        for font_family in font_families:
            font.setFamily(font_family)
            if font.exactMatch():
                break
        font.setPointSize(11)
        self.machines_table.setFont(font)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Contenuto principale - Sezione Inspection
        inspection_section = self.create_inspection_section()
        main_layout.addWidget(inspection_section, 1)
        
        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)
        
    def create_header(self):
        """Crea l'header con back button, logo e titolo"""
        header_frame = QFrame()
        header_frame.setFixedHeight(80)
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 15, 20, 15)
        header_layout.setSpacing(15)
        
        # Pulsante Back
        back_button = QPushButton("←")
        back_button.setFixedSize(40, 40)
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 20px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
                border: 1px solid #4a4a5a;
            }
            QPushButton:pressed {
                background-color: #1a1a2a;
            }
        """)
        back_button.clicked.connect(self.go_back)
        header_layout.addWidget(back_button)
        
        # Logo circolare (simulato con QLabel)
        logo_label = QLabel("N+")
        logo_label.setFixedSize(50, 50)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("""
            QLabel {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 2px solid #5a3a7a;
                border-radius: 25px;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(logo_label)
        
        # Titolo
        title_label = QLabel("Production")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Info sviluppatore e data/ora
        info_layout = QVBoxLayout()
        info_layout.setAlignment(Qt.AlignRight)
        
        developer_label = QLabel("NStone")
        developer_label.setStyleSheet("color: #FFFFFF; font-size: 10px;")
        info_layout.addWidget(developer_label)
        
        self.datetime_label = QLabel()
        self.datetime_label.setStyleSheet("color: #FFFFFF; font-size: 10px;")
        self.update_datetime()
        info_layout.addWidget(self.datetime_label)
        
        header_layout.addLayout(info_layout)
        
        # Timer per aggiornare data/ora
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_datetime)
        self.timer.start(1000)
        
        return header_frame
    
    def create_left_box(self):
        """Crea il box sinistro con AI Assistant"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)
        
        # Titolo
        title = QLabel("Produzione AI")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # Sottotitolo
        subtitle = QLabel("Assistente Produzione AI")
        subtitle.setStyleSheet("color: #AAAAAA; font-size: 16px;")
        layout.addWidget(subtitle)
        
        layout.addSpacing(30)
        
        # Messaggio
        message = QLabel("Submit your question")
        message.setStyleSheet("color: #FFFFFF; font-size: 18px;")
        layout.addWidget(message)
        
        layout.addSpacing(20)
        
        # Campo input
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Inserisci la tua domanda")
        self.question_input.setMinimumHeight(50)
        self.question_input.setStyleSheet("""
            QLineEdit {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 8px;
                padding: 12px 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #5a3a7a;
            }
        """)
        layout.addWidget(self.question_input)
        
        # Collega il tasto Invio al campo input
        self.question_input.returnPressed.connect(self.send_question)
        
        # Pulsante invio
        send_button = QPushButton("Send")
        send_button.setMinimumHeight(45)
        send_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                padding: 12px 40px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        send_button.clicked.connect(self.send_question)
        layout.addWidget(send_button, 0, Qt.AlignHCenter)
        
        layout.addStretch()
        
        return box
    
    def create_right_box(self):
        """Crea il box destro con tabella macchine"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Titolo tabella
        title = QLabel("Stato Macchine")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Tabella
        self.machines_table = QTableWidget()
        self.machines_table.setColumnCount(6)
        self.machines_table.setHorizontalHeaderLabels([
            "Machine", "Status", "Current Work", "Completion (%)", "Efficiency (%)", "Consumption (kWh)"
        ])
        self.machines_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
            }
            QTableWidget::item {
                padding: 12px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #4a2a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 12px;
                border: none;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        self.machines_table.horizontalHeader().setStretchLastSection(True)
        self.machines_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.machines_table.setAlternatingRowColors(True)
        self.machines_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Font moderno
        font = QFont()
        font_families = ["Montserrat", "Roboto", "Open Sans", "Segoe UI", "Arial"]
        for font_family in font_families:
            font.setFamily(font_family)
            if font.exactMatch():
                break
        font.setPointSize(11)
        self.machines_table.setFont(font)
        
        layout.addWidget(self.machines_table, 1)
        
        return box
    
    def create_footer(self):
        """Crea il footer con copyright"""
        footer_frame = QFrame()
        footer_frame.setFixedHeight(50)
        footer_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
        """)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        
        footer_label = QLabel("NStone")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setStyleSheet("color: #AAAAAA; font-size: 10px;")
        footer_layout.addWidget(footer_label)
        
        return footer_frame
    
    def load_csv_data(self):
        """Carica i dati dal CSV e popola la tabella"""
        self.machines_table.setRowCount(0)
        
        if not self.csv_file.exists():
            return
        
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_pos = self.machines_table.rowCount()
                    self.machines_table.insertRow(row_pos)
                    
                    # Machine
                    self.machines_table.setItem(row_pos, 0, QTableWidgetItem(row.get('Machine', '')))
                    
                    # Status
                    self.machines_table.setItem(row_pos, 1, QTableWidgetItem(row.get('Status', '')))
                    
                    # Current Work
                    self.machines_table.setItem(row_pos, 2, QTableWidgetItem(row.get('Current Work', '')))
                    
                    # Completion (%)
                    completion = row.get('Completion', '0')
                    try:
                        completion_float = float(completion)
                        completion_str = f"{completion_float:.1f}%"
                    except:
                        completion_str = f"{completion}%"
                    self.machines_table.setItem(row_pos, 3, QTableWidgetItem(completion_str))
                    
                    # Efficiency (%)
                    efficiency = row.get('Efficiency', '0')
                    try:
                        efficiency_float = float(efficiency)
                        efficiency_str = f"{efficiency_float:.1f}%"
                    except:
                        efficiency_str = f"{efficiency}%"
                    self.machines_table.setItem(row_pos, 4, QTableWidgetItem(efficiency_str))
                    
                    # Consumption (kWh)
                    consumption = row.get('Consumption', '0')
                    try:
                        consumption_float = float(consumption)
                        consumption_str = f"{consumption_float:.1f} kWh"
                    except:
                        consumption_str = f"{consumption} kWh"
                    self.machines_table.setItem(row_pos, 5, QTableWidgetItem(consumption_str))
                    
        except Exception as e:
            print(f"Errore nel caricamento CSV: {e}")
    
    def send_question(self):
        """Gestisce l'invio della domanda"""
        import traceback
        
        try:
            question = self.question_input.text().strip()
            if not question:
                return
            
            print(f"\n[PRODUCTION WINDOW] Domanda inviata: {question}")
            
            # TODO: Implementare logica di invio al motore neurale
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Domanda Inviata", 
                                   f"Domanda inviata:\n\n{question}")
            
            print(f"[PRODUCTION WINDOW] Funzione send_question chiamata correttamente")
            
            self.question_input.clear()
            
        except Exception as e:
            print("\n" + "="*80)
            print("ERRORE IN send_question (PRODUCTION WINDOW):")
            print("="*80)
            traceback.print_exc()
            print("="*80 + "\n")
            # Non rilanciare l'eccezione per evitare crash
    
    def update_datetime(self):
        """Update header date/time (English)."""
        self.datetime_label.setText(format_header_datetime())
    
    def go_back(self):
        """Porta il focus alla dashboard (sezione resta aperta o in icona)."""
        self.go_back_to_dashboard()
    
    def apply_stylesheet(self):
        """Applica lo stylesheet con tema scuro"""
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
            QWidget {
                background: transparent;
            }
        """)
    
    def create_inspection_section(self):
        """Crea la sezione Inspection con stile liquid glass e palette Arch Linux"""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(20, 10, 20, 20)  # Ridotto margine superiore da 20 a 10
        section_layout.setSpacing(8)  # Ridotto spacing da 15 a 8
        
        # Titolo e descrizione (sulla stessa riga per risparmiare spazio)
        title_row = QHBoxLayout()
        title_label = QLabel("Inspection")
        title_label.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 22px;
                font-weight: bold;
                background: transparent;
            }
        """)
        title_row.addWidget(title_label)
        
        desc_label = QLabel("Analisi qualità lastre di marmo")
        desc_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 13px;
                background: transparent;
            }
        """)
        title_row.addWidget(desc_label)
        title_row.addStretch()
        section_layout.addLayout(title_row)
        
        # Barra superiore con due pulsanti piccoli
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)  # Ridotto spacing da 10 a 8
        
        # Pulsante Manual Inspection
        manual_inspection_btn = QPushButton("Manual Inspection")
        manual_inspection_btn.setMinimumHeight(35)
        manual_inspection_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 217, 255, 150);
                color: #0A0A15;
                border: 1px solid rgba(0, 217, 255, 200);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 217, 255, 200);
                border: 1px solid rgba(0, 217, 255, 255);
            }
            QPushButton:pressed {
                background-color: rgba(0, 180, 220, 200);
            }
        """)
        top_bar.addWidget(manual_inspection_btn)
        
        # Pulsante AI Assistant
        ai_assistant_btn = QPushButton("AI Assistant")
        ai_assistant_btn.setMinimumHeight(35)
        ai_assistant_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(23, 147, 209, 120);
                color: #E8E8E8;
                border: 1px solid rgba(0, 217, 255, 100);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(23, 147, 209, 180);
                border: 1px solid rgba(0, 217, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(15, 76, 117, 180);
            }
        """)
        top_bar.addWidget(ai_assistant_btn)
        
        # Pulsante Apri Cartella Foto
        self.btnApriCartellaFoto = QPushButton("Apri Cartella Foto")
        self.btnApriCartellaFoto.setMinimumHeight(35)
        self.btnApriCartellaFoto.setStyleSheet("""
            QPushButton {
                background-color: rgba(23, 147, 209, 120);
                color: #E8E8E8;
                border: 1px solid rgba(0, 217, 255, 100);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(23, 147, 209, 180);
                border: 1px solid rgba(0, 217, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(15, 76, 117, 180);
            }
        """)
        self.btnApriCartellaFoto.clicked.connect(self.on_apri_cartella_foto_clicked)
        top_bar.addWidget(self.btnApriCartellaFoto)
        
        top_bar.addStretch()
        
        section_layout.addLayout(top_bar)
        
        # Barra bottoni azioni (in alto a destra) - 2 colonne verticali
        actions_bar = QHBoxLayout()
        actions_bar.setSpacing(8)  # Ridotto spacing da 10 a 8
        actions_bar.addStretch()
        
        # Colonna sinistra: Esporta Analisi e Salva Analisi
        left_actions_column = QVBoxLayout()
        left_actions_column.setSpacing(5)  # Ridotto spacing da 8 a 5
        
        # Bottone Esporta Analisi
        self.btnEsportaAnalisi = QPushButton("Esporta Analisi")
        self.btnEsportaAnalisi.setMinimumHeight(40)
        self.btnEsportaAnalisi.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 217, 255, 150);
                color: #0A0A15;
                border: 1px solid rgba(0, 217, 255, 200);
                border-radius: 8px;
                padding: 10px 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 217, 255, 200);
                border: 1px solid rgba(0, 217, 255, 255);
            }
            QPushButton:pressed {
                background-color: rgba(0, 180, 220, 200);
            }
        """)
        self.btnEsportaAnalisi.clicked.connect(self.on_esporta_analisi_clicked)
        left_actions_column.addWidget(self.btnEsportaAnalisi)
        
        # Bottone Salva Analisi
        self.btnSalvaAnalisi = QPushButton("Salva Analisi")
        self.btnSalvaAnalisi.setMinimumHeight(40)
        self.btnSalvaAnalisi.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 217, 255, 150);
                color: #0A0A15;
                border: 1px solid rgba(0, 217, 255, 200);
                border-radius: 8px;
                padding: 10px 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 217, 255, 200);
                border: 1px solid rgba(0, 217, 255, 255);
            }
            QPushButton:pressed {
                background-color: rgba(0, 180, 220, 200);
            }
        """)
        self.btnSalvaAnalisi.clicked.connect(self.on_salva_analisi_clicked)
        left_actions_column.addWidget(self.btnSalvaAnalisi)
        
        # Colonna destra: Reset Sessione e Storico Analisi
        right_actions_column = QVBoxLayout()
        right_actions_column.setSpacing(5)  # Ridotto spacing da 8 a 5
        
        # Bottone Reset Sessione
        self.btnResetSessione = QPushButton("Reset Sessione")
        self.btnResetSessione.setMinimumHeight(40)
        self.btnResetSessione.setStyleSheet("""
            QPushButton {
                background-color: rgba(23, 147, 209, 120);
                color: #E8E8E8;
                border: 1px solid rgba(0, 217, 255, 100);
                border-radius: 8px;
                padding: 10px 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(23, 147, 209, 180);
                border: 1px solid rgba(0, 217, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(15, 76, 117, 180);
            }
        """)
        self.btnResetSessione.clicked.connect(self.on_reset_sessione_clicked)
        right_actions_column.addWidget(self.btnResetSessione)
        
        # Bottone Storico Analisi
        self.btnStoricoAnalisi = QPushButton("Storico Analisi")
        self.btnStoricoAnalisi.setMinimumHeight(40)
        self.btnStoricoAnalisi.setStyleSheet("""
            QPushButton {
                background-color: rgba(23, 147, 209, 120);
                color: #E8E8E8;
                border: 1px solid rgba(0, 217, 255, 100);
                border-radius: 8px;
                padding: 10px 25px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(23, 147, 209, 180);
                border: 1px solid rgba(0, 217, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(15, 76, 117, 180);
            }
        """)
        self.btnStoricoAnalisi.clicked.connect(self.on_storico_analisi_clicked)
        right_actions_column.addWidget(self.btnStoricoAnalisi)
        
        # Aggiungi le due colonne alla barra azioni
        actions_bar.addLayout(left_actions_column)
        actions_bar.addLayout(right_actions_column)
        
        section_layout.addLayout(actions_bar)
        
        # Layout a 3 colonne orizzontali
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(10)  # Ridotto spacing da 15 a 10
        
        # BOX SINISTRA - Input Materiale
        left_box = self.create_inspection_input_box()
        columns_layout.addWidget(left_box, 1)
        
        # BOX CENTRO - Risultati Analisi
        center_box = self.create_inspection_results_box()
        columns_layout.addWidget(center_box, 1)
        
        # BOX DESTRA - Analisi Difetti e Telemetria
        right_box = self.create_inspection_analysis_box()
        columns_layout.addWidget(right_box, 1)
        
        section_layout.addLayout(columns_layout, 1)
        
        return section_widget
    
    def create_inspection_input_box(self):
        """Crea il box sinistro: Input Materiale con 4 slot immagine"""
        box_widget = QFrame()
        box_widget.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                padding: 10px;
            }
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(40, 40, 55, 200),
                    stop:1 rgba(30, 30, 40, 180));
            }
        """)
        box_layout = QVBoxLayout(box_widget)
        box_layout.setContentsMargins(10, 10, 10, 10)  # Ridotto da 15 a 10
        box_layout.setSpacing(10)  # Ridotto da 15 a 10
        
        # Titolo
        title_label = QLabel("Foto Materiale da Ispezionare")
        title_label.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 16px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(title_label)
        
        # Grid per 4 slot immagine (2x2)
        image_grid = QGridLayout()
        image_grid.setSpacing(8)  # Ridotto da 10 a 8
        
        self.image_slots = []
        self.image_labels = []  # Per memorizzare i label delle immagini
        button_names = ['btnCaricaFoto1', 'btnCaricaFoto2', 'btnCaricaFoto3', 'btnCaricaFoto4']
        callback_names = [self.on_carica_foto_1_clicked, self.on_carica_foto_2_clicked, 
                         self.on_carica_foto_3_clicked, self.on_carica_foto_4_clicked]
        
        for i in range(4):
            row = i // 2
            col = i % 2
            
            # Frame per slot immagine
            slot_frame = QFrame()
            slot_frame.setMinimumHeight(120)
            slot_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(20, 20, 30, 150);
                    border: 2px dashed rgba(179, 211, 255, 100);
                    border-radius: 8px;
                }
            """)
            slot_layout = QVBoxLayout(slot_frame)
            slot_layout.setAlignment(Qt.AlignCenter)
            slot_layout.setSpacing(8)
            
            # Placeholder immagine (salvato per poter aggiornare)
            image_label = QLabel("📷")
            image_label.setAlignment(Qt.AlignCenter)
            image_label.setStyleSheet("""
                QLabel {
                    color: #B0B0B0;
                    font-size: 32px;
                    background: transparent;
                }
            """)
            image_label.setScaledContents(True)
            image_label.setMaximumSize(100, 80)
            slot_layout.addWidget(image_label)
            self.image_labels.append(image_label)
            
            # Pulsante Carica Foto
            load_btn = QPushButton("Carica Foto")
            load_btn.setMinimumHeight(30)
            load_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(23, 147, 209, 120);
                    color: #E8E8E8;
                    border: 1px solid rgba(0, 217, 255, 100);
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: rgba(23, 147, 209, 180);
                    border: 1px solid rgba(0, 217, 255, 150);
                }
                QPushButton:pressed {
                    background-color: rgba(15, 76, 117, 180);
                }
            """)
            setattr(self, button_names[i], load_btn)
            load_btn.clicked.connect(callback_names[i])
            slot_layout.addWidget(load_btn)
            
            image_grid.addWidget(slot_frame, row, col)
            self.image_slots.append(slot_frame)
        
        box_layout.addLayout(image_grid)
        
        # Pulsante Avvia Analisi
        self.analyze_btn = QPushButton("Avvia Analisi")
        self.analyze_btn.setMinimumHeight(45)
        self.analyze_btn.setToolTip("Inserisci 4 immagini della lastra per avviare l'ispezione automatica")
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 217, 255, 150);
                color: #0A0A15;
                border: 1px solid rgba(0, 217, 255, 200);
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 217, 255, 200);
                border: 1px solid rgba(0, 217, 255, 255);
            }
            QPushButton:pressed {
                background-color: rgba(0, 180, 220, 200);
            }
        """)
        self.analyze_btn.clicked.connect(self.on_avvia_analisi_clicked)
        box_layout.addWidget(self.analyze_btn)
        box_layout.addStretch()
        
        return box_widget
    
    def create_inspection_results_box(self):
        """Crea il box centrale: Risultati Analisi"""
        box_widget = QFrame()
        box_widget.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                padding: 10px;
            }
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(40, 40, 55, 200),
                    stop:1 rgba(30, 30, 40, 180));
            }
        """)
        box_layout = QVBoxLayout(box_widget)
        box_layout.setContentsMargins(10, 10, 10, 10)  # Ridotto da 15 a 10
        box_layout.setSpacing(10)  # Ridotto da 15 a 10
        
        # Titolo
        title_label = QLabel("Informazioni Materiale")
        title_label.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 16px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(title_label)
        
        # Campi informativi
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(10)
        
        # Identità materiale
        self.identity_label = QLabel("Identità materiale: -")
        self.identity_label.setStyleSheet("color: #B0B0B0; font-size: 12px; background: transparent;")
        info_layout.addWidget(self.identity_label)
        
        # Grado
        self.grade_label = QLabel("Grado: -")
        self.grade_label.setStyleSheet("color: #B0B0B0; font-size: 12px; background: transparent;")
        info_layout.addWidget(self.grade_label)
        
        # Confidence
        self.confidence_label = QLabel("Confidence: -")
        self.confidence_label.setStyleSheet("color: #B0B0B0; font-size: 12px; background: transparent;")
        info_layout.addWidget(self.confidence_label)
        
        # Diagnostica estetica
        self.diagnostic_text = QTextEdit()
        self.diagnostic_text.setReadOnly(True)
        self.diagnostic_text.setMaximumHeight(80)
        self.diagnostic_text.setPlaceholderText("Diagnostica estetica...")
        self.diagnostic_text.setStyleSheet("""
            QTextEdit {
                background-color: rgba(15, 15, 25, 150);
                border: 1px solid rgba(179, 211, 255, 50);
                border-radius: 6px;
                color: #B0B0B0;
                font-size: 11px;
                padding: 8px;
            }
        """)
        info_layout.addWidget(self.diagnostic_text)
        
        box_layout.addWidget(info_frame)
        
        # Separatore visivo
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: rgba(179, 211, 255, 60); max-height: 1px;")
        box_layout.addWidget(separator)
        
        # Box Classificazione
        classification_frame = QFrame()
        classification_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        classification_layout = QVBoxLayout(classification_frame)
        classification_layout.setSpacing(10)
        
        classification_title = QLabel("Classificazione")
        classification_title.setStyleSheet("color: #E8E8E8; font-size: 13px; font-weight: bold; background: transparent;")
        classification_layout.addWidget(classification_title)
        
        # Radio buttons per classificazione
        self.classification_group = QButtonGroup()
        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(15)
        
        for label in ["1ST", "2ND", "COMMERCIAL"]:
            radio = QRadioButton(label)
            radio.setToolTip("Classificazione automatica secondo standard NSTONE")
            radio.setStyleSheet("""
                QRadioButton {
                    color: #B0B0B0;
                    font-size: 12px;
                    background: transparent;
                }
                QRadioButton::indicator {
                    width: 16px;
                    height: 16px;
                    border: 2px solid rgba(179, 211, 255, 150);
                    border-radius: 8px;
                    background-color: rgba(20, 20, 30, 150);
                }
                QRadioButton::indicator:checked {
                    background-color: rgba(0, 217, 255, 200);
                    border: 2px solid rgba(0, 217, 255, 255);
                }
            """)
            self.classification_group.addButton(radio)
            radio_layout.addWidget(radio)
        
        classification_layout.addLayout(radio_layout)
        box_layout.addWidget(classification_frame)
        box_layout.addStretch()
        
        return box_widget
    
    def create_inspection_analysis_box(self):
        """Crea il box destro: Analisi Difetti e Telemetria"""
        box_widget = QFrame()
        box_widget.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                padding: 10px;
            }
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(40, 40, 55, 200),
                    stop:1 rgba(30, 30, 40, 180));
            }
        """)
        box_layout = QVBoxLayout(box_widget)
        box_layout.setContentsMargins(10, 10, 10, 10)  # Ridotto da 15 a 10
        box_layout.setSpacing(10)  # Ridotto da 15 a 10
        
        # Box superiore: Difetti Rilevati
        defects_frame = QFrame()
        defects_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        defects_layout = QVBoxLayout(defects_frame)
        defects_layout.setSpacing(10)
        
        defects_title = QLabel("Difetti Rilevati")
        defects_title.setStyleSheet("color: #E8E8E8; font-size: 14px; font-weight: bold; background: transparent;")
        defects_layout.addWidget(defects_title)
        
        defects_list = QListWidget()
        defects_list.setToolTip("Scheggiature, venature disomogenee, anomalie strutturali")
        defects_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(15, 15, 25, 150);
                border: 1px solid rgba(179, 211, 255, 50);
                border-radius: 6px;
                color: #B0B0B0;
                font-size: 11px;
                padding: 8px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid rgba(179, 211, 255, 30);
            }
            QListWidget::item:selected {
                background-color: rgba(0, 217, 255, 80);
                color: #E8E8E8;
            }
        """)
        self.defects_list = defects_list
        self.defects_list.addItem("Nessun difetto rilevato")
        defects_layout.addWidget(self.defects_list)
        
        box_layout.addWidget(defects_frame)
        
        # Box inferiore: Telemetria Visiva
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        telemetry_layout = QVBoxLayout(telemetry_frame)
        telemetry_layout.setSpacing(10)
        
        telemetry_title = QLabel("Telemetria Visiva")
        telemetry_title.setStyleSheet("color: #E8E8E8; font-size: 14px; font-weight: bold; background: transparent;")
        telemetry_layout.addWidget(telemetry_title)
        
        # Granulometria
        granulometry_label = QLabel("Granulometria:")
        granulometry_label.setStyleSheet("color: #E8E8E8; font-size: 12px; font-weight: bold; background: transparent;")
        telemetry_layout.addWidget(granulometry_label)
        
        self.granulometry_text = QTextEdit()
        self.granulometry_text.setReadOnly(True)
        self.granulometry_text.setMaximumHeight(60)
        self.granulometry_text.setPlaceholderText("Descrizione granulometrica...")
        self.granulometry_text.setToolTip("Analisi granulometrica e cromatica rilevata dal sistema neurale")
        self.granulometry_text.setStyleSheet("""
            QTextEdit {
                background-color: rgba(15, 15, 25, 150);
                border: 1px solid rgba(179, 211, 255, 50);
                border-radius: 6px;
                color: #B0B0B0;
                font-size: 11px;
                padding: 8px;
            }
        """)
        telemetry_layout.addWidget(self.granulometry_text)
        
        # Colore
        color_label = QLabel("Colore:")
        color_label.setStyleSheet("color: #E8E8E8; font-size: 12px; font-weight: bold; background: transparent;")
        telemetry_layout.addWidget(color_label)
        
        self.color_text = QTextEdit()
        self.color_text.setReadOnly(True)
        self.color_text.setMaximumHeight(60)
        self.color_text.setPlaceholderText("Descrizione cromatica...")
        self.color_text.setToolTip("Analisi granulometrica e cromatica rilevata dal sistema neurale")
        self.color_text.setStyleSheet("""
            QTextEdit {
                background-color: rgba(15, 15, 25, 150);
                border: 1px solid rgba(179, 211, 255, 50);
                border-radius: 6px;
                color: #B0B0B0;
                font-size: 11px;
                padding: 8px;
            }
        """)
        telemetry_layout.addWidget(self.color_text)
        
        box_layout.addWidget(telemetry_frame)
        box_layout.addStretch()
        
        return box_widget
    
    def on_carica_foto_1_clicked(self):
        """Callback per il bottone Carica Foto 1"""
        self._load_photo(0)
    
    def on_carica_foto_2_clicked(self):
        """Callback per il bottone Carica Foto 2"""
        self._load_photo(1)
    
    def on_carica_foto_3_clicked(self):
        """Callback per il bottone Carica Foto 3"""
        self._load_photo(2)
    
    def on_carica_foto_4_clicked(self):
        """Callback per il bottone Carica Foto 4"""
        self._load_photo(3)
    
    def _load_photo(self, index: int):
        """Carica una foto nello slot specificato"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Seleziona Foto {index + 1}",
            "",
            "Immagini (*.png *.jpg *.jpeg *.bmp *.gif);;Tutti i file (*.*)"
        )
        
        if file_path:
            self.loaded_photo_paths[index] = file_path
            # Aggiorna l'anteprima immagine
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    100, 80, 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                self.image_labels[index].setPixmap(scaled_pixmap)
                self.image_labels[index].setText("")  # Rimuove l'emoji
    
    def on_apri_cartella_foto_clicked(self):
        """Callback per il bottone Apri Cartella Foto"""
        pass
    
    def on_salva_analisi_clicked(self):
        """Callback per il bottone Salva Analisi"""
        pass
    
    def on_storico_analisi_clicked(self):
        """Callback per il bottone Storico Analisi"""
        pass
    
    def on_esporta_analisi_clicked(self):
        """Callback per il bottone Esporta Analisi - apre dialog con testo copiabile"""
        # TODO: Recuperare i dati dell'analisi corrente dai widget della UI
        # Per ora mostriamo un esempio di testo
        analysis_text = self.get_analysis_text()
        
        dialog = ExportAnalysisDialog(self, analysis_text)
        show_auxiliary_window(dialog)
    
    def on_reset_sessione_clicked(self):
        """Callback per il bottone Reset Sessione"""
        self.reset_session()
    
    def reset_session(self):
        """Reset completo della UI e dello stato interno"""
        # A) Svuotare le foto caricate
        for image_label in self.image_labels:
            image_label.setPixmap(QPixmap())
            image_label.setText("📷")
        
        # Resettare variabili foto
        self.loaded_photo_paths = [None] * 4
        
        # B) Azzerare i campi UI
        self.identity_label.setText("-")
        self.grade_label.setText("-")
        self.confidence_label.setText("-")
        self.diagnostic_text.clear()
        self.defects_list.clear()
        self.granulometry_text.clear()
        self.color_text.clear()
        
        # C) Resettare classificazione
        for button in self.classification_group.buttons():
            button.setChecked(False)
        
        # D) Resettare stato interno
        # E) Eliminare la cartella temporanea della sessione, se esiste
        if self.current_session_dir is not None:
            try:
                shutil.rmtree(self.current_session_dir, ignore_errors=True)
            except Exception as e:
                print(f"Errore nell'eliminazione della sessione: {e}")
            finally:
                self.current_session_dir = None
    
    def get_loaded_photo_paths(self):
        """Restituisce la lista dei path delle foto caricate (escludendo None)"""
        return [path for path in self.loaded_photo_paths if path is not None]
    
    def on_avvia_analisi_clicked(self):
        """Callback per il bottone Avvia Analisi"""
        # Raccogli i path delle foto
        photo_paths = self.get_loaded_photo_paths()
        
        if not photo_paths:
            QMessageBox.warning(
                self,
                "Nessuna Foto",
                "Carica almeno una foto prima di avviare l'analisi."
            )
            return
        
        try:
            # Disabilita il bottone durante l'elaborazione
            self.analyze_btn.setEnabled(False)
            self.analyze_btn.setText("Analisi in corso...")
            
            # Crea la sessione
            session_dir = create_simple_session(photo_paths)
            if not session_dir:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Impossibile creare la sessione di analisi."
                )
                return
            
            # Salva la sessione corrente
            self.current_session_dir = session_dir
            
            # Invia a Gemini
            result = self.gemini_service.analyze_session(session_dir)
            if result and "analysis" in result:
                # Aggiorna la UI con i risultati dell'analisi
                self.update_ui_with_result(result)
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    "Impossibile ricevere la risposta dal servizio di analisi."
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Errore durante l'analisi: {str(e)}"
            )
        finally:
            # Riabilita il bottone
            self.analyze_btn.setEnabled(True)
            self.analyze_btn.setText("Avvia Analisi")
    
    def update_ui_with_result(self, result: dict):
        """
        Aggiorna l'interfaccia utente con i risultati dell'analisi.
        
        Args:
            result: Dizionario contenente session_id e analysis
        """
        try:
            analysis = result["analysis"]
            
            # Aggiorna informazioni materiale
            self.identity_label.setText(analysis["material_identity"])
            self.grade_label.setText(analysis["grade"])
            self.confidence_label.setText(str(analysis["confidence"]))
            self.diagnostic_text.setPlainText(analysis["description"])
            
            # Aggiorna classificazione
            classification = str(analysis["classification"]).upper()
            for button in self.classification_group.buttons():
                if button.text() == classification:
                    button.setChecked(True)
                    break
            
            # Aggiorna difetti
            self.defects_list.clear()
            defects = analysis["defects"]
            if isinstance(defects, list):
                for defect in defects:
                    self.defects_list.addItem(str(defect))
            else:
                self.defects_list.addItem("Nessun difetto rilevato")
            
            # Aggiorna telemetria
            self.granulometry_text.setPlainText(analysis["granulometry"])
            self.color_text.setPlainText(analysis["color"])
                
        except Exception as e:
            print(f"Errore nell'aggiornamento UI: {e}")
    
    def get_analysis_text(self):
        """Recupera il testo completo dell'analisi da esportare"""
        # TODO: Recuperare i dati reali dai widget dell'interfaccia
        # Questo è un placeholder - dovrebbe essere implementato recuperando:
        # - Informazioni Materiale (identità, grado, confidence, diagnostica)
        # - Classificazione
        # - Difetti rilevati
        # - Telemetria visiva (granulometria, colore)
        
        text = "=== ANALISI MATERIALE ===\n\n"
        text += f"{self.identity_label.text()}\n"
        text += f"{self.grade_label.text()}\n"
        text += f"{self.confidence_label.text()}\n\n"
        text += f"Diagnostica estetica: {self.diagnostic_text.toPlainText()}\n\n"
        
        # Classificazione
        checked_button = self.classification_group.checkedButton()
        classification = checked_button.text() if checked_button else "-"
        text += f"Classificazione: {classification}\n\n"
        
        text += "=== DIFETTI RILEVATI ===\n\n"
        defects_text = "\n".join([
            self.defects_list.item(i).text() 
            for i in range(self.defects_list.count())
        ])
        text += defects_text + "\n\n"
        
        text += "=== TELEMETRIA VISIVA ===\n\n"
        text += f"Granulometria: {self.granulometry_text.toPlainText()}\n"
        text += f"Colore: {self.color_text.toPlainText()}\n"
        
        return text

