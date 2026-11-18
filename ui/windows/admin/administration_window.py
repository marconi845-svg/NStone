"""
Nstone LLM - Finestra Administration
Gestione documenti e fatture
"""
import os
import sys
import csv
import json
import subprocess
import platform
import logging
from pathlib import Path
from datetime import datetime
from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTableWidget, 
                             QTableWidgetItem, QLineEdit, QHeaderView,
                             QDoubleSpinBox, QDateEdit, QTextEdit, QScrollArea,
                             QMessageBox)
from PyQt5.QtCore import Qt, QTimer, QDate, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

logger = logging.getLogger(__name__)


class AdministrationWindow(SectionDialog):
    """Finestra Administration per gestione documenti e fatture"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Administration")
        self.setMinimumSize(1600, 900)
        self.setModal(False)
        
        # Cartella CSV
        self.csv_dir = Path(__file__).parent / "csv_data"
        self.csv_dir.mkdir(exist_ok=True)
        self.csv_file = self.csv_dir / "administration.csv"
        
        # Percorso file JSON ordini (conferme d'ordine)
        self.logs_dir = Path(__file__).parent / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        self.orders_dir = self.logs_dir / "orders"
        self.orders_dir.mkdir(exist_ok=True)
        
        # Percorso cartella fatture elaborate
        self.invoices_ready_dir = self.logs_dir / "invoices_ready"
        self.invoices_ready_dir.mkdir(exist_ok=True)
        
        # Dati ordini confermati caricati
        self.order_confirmations = []
        self.selected_order_data = None
        
        # Dati fatture da inviare
        self.invoices_ready_list = []
        self.selected_invoice_file = None
        self.selected_invoice_order_id = None
        
        # Inizializza CSV se non esiste (legacy, mantenuto per compatibilità)
        self.init_csv_file()
        
        self.init_ui()
        # load_csv_data() rimosso - non più utilizzato (sostituito da load_order_confirmations())
        self.load_order_confirmations()
        self.load_invoices_ready()
        self.apply_stylesheet()
        
    def init_csv_file(self):
        """Inizializza il file CSV con le intestazioni se non esiste"""
        if not self.csv_file.exists() or os.path.getsize(self.csv_file) == 0:
            headers = ["Invoice Number", "Client", "Amount (EUR)", "Date", "Status"]
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                # Aggiungi riga di test
                writer.writerow(["INV-2024-001", "Cliente Test", "15750", "20/12/2025", "Pending"])
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Contenuto principale - Sezione Administration
        administration_section = self.create_administration_section()
        main_layout.addWidget(administration_section, 1)
        
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
        
        # Titolo e sottotitolo
        title_layout = QVBoxLayout()
        title_layout.setSpacing(0)
        
        title_label = QLabel("Administration")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold;")
        title_layout.addWidget(title_label)
        
        subtitle_label = QLabel("Gestione documenti")
        subtitle_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        title_layout.addWidget(subtitle_label)
        
        header_layout.addLayout(title_layout)
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
    
    def create_administration_section(self):
        """Crea la sezione Administration con layout a 3 colonne orizzontali (identico a Orders)"""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(20, 20, 20, 20)
        section_layout.setSpacing(15)
        
        # Titolo e descrizione
        title_label = QLabel("Administration")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        section_layout.addWidget(title_label)
        
        desc_label = QLabel("Gestione documenti e fatture")
        desc_label.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        section_layout.addWidget(desc_label)
        
        # Barra superiore con pulsanti
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        
        fattura_btn = QPushButton("Fattura Manuale")
        fattura_btn.setMinimumHeight(35)
        fattura_btn.setToolTip("Crea una fattura manuale")
        fattura_btn.setStyleSheet("""
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
        top_bar.addWidget(fattura_btn)
        
        # Pulsante Apri cartella ordine
        self.open_order_folder_btn = QPushButton("📂 Apri cartella ordine")
        self.open_order_folder_btn.setMinimumHeight(35)
        self.open_order_folder_btn.setToolTip("Apre la cartella logs/orders/ e seleziona il file JSON dell'ordine selezionato")
        self.open_order_folder_btn.setEnabled(False)  # Disabilitato inizialmente
        self.open_order_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
            QPushButton:disabled {
                background-color: #2a2a3a;
                color: #666666;
                border: 1px solid #3a3a4a;
            }
        """)
        self.open_order_folder_btn.clicked.connect(self.on_open_order_folder_clicked)
        top_bar.addWidget(self.open_order_folder_btn)
        
        top_bar.addStretch()
        
        section_layout.addLayout(top_bar)
        
        # Layout a 3 colonne orizzontali
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(15)
        
        # BOX SINISTRA - Conferme d'ordine ricevute
        left_box = self.create_left_administration_box()
        columns_layout.addWidget(left_box, 1)
        
        # BOX CENTRO - Elaborazione Fattura
        center_box = self.create_invoice_processing_box()
        columns_layout.addWidget(center_box, 1)
        
        # BOX DESTRA - Fatture da inviare
        right_box = self.create_right_administration_box()
        columns_layout.addWidget(right_box, 1)
        
        section_layout.addLayout(columns_layout, 1)
        
        return section_widget
    
    def create_left_administration_box(self):
        """Crea il box sinistro: Conferme d'ordine ricevute"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(15)
        
        # Titolo colonna
        title_label = QLabel("Conferme d'ordine ricevute")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        column_layout.addWidget(title_label)
        
        # Tabella conferme d'ordine
        orders_table = QTableWidget()
        orders_table.setColumnCount(4)
        orders_table.setHorizontalHeaderLabels(["Numero ordine", "Cliente", "Importo", "Stato conferma"])
        orders_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #4a2a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        orders_table.horizontalHeader().setStretchLastSection(True)
        orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        orders_table.setAlternatingRowColors(True)
        orders_table.setEditTriggers(QTableWidget.NoEditTriggers)
        orders_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        # Collega il click alla funzione per abilitare pulsanti
        orders_table.itemClicked.connect(self.on_order_confirmation_clicked)
        orders_table.itemDoubleClicked.connect(self.on_order_confirmation_clicked)
        
        # Pulsante refresh
        refresh_btn = QPushButton("🔄 Aggiorna")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
            }
        """)
        refresh_btn.clicked.connect(self.load_order_confirmations)
        column_layout.addWidget(refresh_btn)
        
        column_layout.addWidget(orders_table, 1)
        
        # Salva riferimento
        self.orders_table = orders_table
        
        return column_widget
    
    def create_invoice_processing_box(self):
        """Crea il box centrale: Elaborazione Fattura"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(15)
        
        # Titolo colonna
        title_label = QLabel("📄 Elaborazione Fattura")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        column_layout.addWidget(title_label)
        
        # Pannello principale
        main_panel = QFrame()
        main_panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        panel_layout = QVBoxLayout(main_panel)
        panel_layout.setContentsMargins(15, 15, 15, 15)
        panel_layout.setSpacing(15)
        
        # Pulsante Elabora con Gemini
        self.process_invoice_btn = QPushButton("⚙️ Elabora con Gemini")
        self.process_invoice_btn.setMinimumHeight(40)
        self.process_invoice_btn.setEnabled(False)  # Disabilitato fino alla selezione di un ordine
        self.process_invoice_btn.setToolTip("Elabora la conferma d'ordine selezionata per generare la fattura")
        self.process_invoice_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
            QPushButton:disabled {
                background-color: #2a2a3a;
                color: #666666;
                border: 1px solid #3a3a4a;
            }
        """)
        self.process_invoice_btn.clicked.connect(self.process_invoice_with_gemini)
        panel_layout.addWidget(self.process_invoice_btn)
        
        # Area di output/log
        output_label = QLabel("Output:")
        output_label.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold;")
        panel_layout.addWidget(output_label)
        
        self.invoice_output_text = QTextEdit()
        self.invoice_output_text.setReadOnly(True)
        self.invoice_output_text.setPlaceholderText("Seleziona un ordine e clicca 'Elabora con Gemini' per generare la fattura...")
        self.invoice_output_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        self.invoice_output_text.setMinimumHeight(300)
        panel_layout.addWidget(self.invoice_output_text, 1)
        
        column_layout.addWidget(main_panel, 1)
        
        return column_widget
    
    def create_unified_service_section(self, title, items):
        """Crea una sezione unificata per un servizio all'interno del pannello centrale"""
        section_frame = QFrame()
        section_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        section_layout = QVBoxLayout(section_frame)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)
        
        # Titolo sezione
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold;")
        section_layout.addWidget(title_label)
        
        # Items della sezione
        for label, value, color in items:
            item_layout = QHBoxLayout()
            
            item_label = QLabel(f"{label}: {value}")
            item_label.setStyleSheet(f"color: {color}; font-size: 11px;")
            item_layout.addWidget(item_label)
            item_layout.addStretch()
            
            section_layout.addLayout(item_layout)
        
        return section_frame
    
    def create_right_administration_box(self):
        """Crea il box destro: Fatture da inviare"""
        column_widget = QWidget()
        column_layout = QVBoxLayout(column_widget)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(15)
        
        # Titolo colonna
        title_label = QLabel("📬 Fatture da inviare")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        column_layout.addWidget(title_label)
        
        # Pulsante Invia fattura
        self.send_invoice_btn = QPushButton("📧 Invia fattura")
        self.send_invoice_btn.setMinimumHeight(35)
        self.send_invoice_btn.setEnabled(False)  # Disabilitato inizialmente
        self.send_invoice_btn.setToolTip("Invia la fattura selezionata al cliente via email")
        self.send_invoice_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
            QPushButton:disabled {
                background-color: #2a2a3a;
                color: #666666;
                border: 1px solid #3a3a4a;
            }
        """)
        self.send_invoice_btn.clicked.connect(self.send_invoice_via_smtp)
        column_layout.addWidget(self.send_invoice_btn)
        
        # Tabella fatture
        invoices_table = QTableWidget()
        invoices_table.setColumnCount(3)
        invoices_table.setHorizontalHeaderLabels(["Nome File", "ID Ordine", "Data Generazione"])
        invoices_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #4a2a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        invoices_table.horizontalHeader().setStretchLastSection(True)
        invoices_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        invoices_table.setAlternatingRowColors(True)
        invoices_table.setEditTriggers(QTableWidget.NoEditTriggers)
        invoices_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        # Collega il click alla selezione
        invoices_table.itemClicked.connect(self.on_invoice_selected)
        invoices_table.itemDoubleClicked.connect(self.on_invoice_selected)
        
        column_layout.addWidget(invoices_table, 1)
        
        # Salva riferimenti
        self.invoices_table = invoices_table
        
        return column_widget
    
    def create_left_panel(self):
        """Crea il pannello sinistro con gestione fatture"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Titolo
        title = QLabel("Lista Fatture")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Form creazione fattura
        form_frame = QFrame()
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(15)
        
        # Cliente
        cliente_label = QLabel("Cliente:")
        cliente_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        form_layout.addWidget(cliente_label)
        
        self.cliente_input = QLineEdit()
        self.cliente_input.setPlaceholderText("Nome Cliente...")
        self.cliente_input.setMinimumHeight(40)
        self.cliente_input.setStyleSheet("""
            QLineEdit {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #5a3a7a;
            }
        """)
        form_layout.addWidget(self.cliente_input)
        
        # Importo
        importo_label = QLabel("Importo (EUR):")
        importo_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        form_layout.addWidget(importo_label)
        
        self.importo_input = QDoubleSpinBox()
        self.importo_input.setMinimum(0.0)
        self.importo_input.setMaximum(999999.99)
        self.importo_input.setDecimals(2)
        self.importo_input.setValue(0.00)
        self.importo_input.setMinimumHeight(40)
        self.importo_input.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QDoubleSpinBox:focus {
                border: 2px solid #5a3a7a;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #2a2a3a;
                border: 1px solid #3a3a4a;
                width: 20px;
            }
        """)
        form_layout.addWidget(self.importo_input)
        
        # Data
        data_label = QLabel("Data:")
        data_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        form_layout.addWidget(data_label)
        
        data_layout = QHBoxLayout()
        self.data_input = QDateEdit()
        self.data_input.setDate(QDate.currentDate())
        self.data_input.setCalendarPopup(True)
        self.data_input.setDisplayFormat("dd/MM/yyyy")
        self.data_input.setMinimumHeight(40)
        self.data_input.setStyleSheet("""
            QDateEdit {
                background-color: #0a0a1a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QDateEdit:focus {
                border: 2px solid #5a3a7a;
            }
            QDateEdit::drop-down {
                background-color: #2a2a3a;
                border: 1px solid #3a3a4a;
                width: 30px;
            }
        """)
        data_layout.addWidget(self.data_input)
        data_layout.addStretch()
        form_layout.addLayout(data_layout)
        
        # Pulsante Crea Fattura
        create_button = QPushButton("Crea Fattura")
        create_button.setMinimumHeight(45)
        create_button.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
            }
            QPushButton:hover {
                background-color: #F0F0F0;
            }
            QPushButton:pressed {
                background-color: #E0E0E0;
            }
        """)
        create_button.clicked.connect(self.create_invoice)
        form_layout.addWidget(create_button)
        
        layout.addWidget(form_frame)
        
        # Tabella fatture legacy - non più utilizzata nella nuova UI
        # Metodo create_left_panel() è legacy e non viene più chiamato
        # La nuova UI usa create_left_administration_box() che legge da JSON
        # Mantenuto per compatibilità ma invoices_table non viene più creato
        # table_label = QLabel("Fatture esistenti:")  # Rimosso
        # self.invoices_table = QTableWidget()  # Rimosso - causa AttributeError
        
        return panel
    
    def create_right_panel(self):
        """Crea il pannello destro con chat interface"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Scroll area per i messaggi
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #1a1a2a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #4a2a6a;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #5a3a7a;
            }
        """)
        
        # Widget per i messaggi
        messages_widget = QWidget()
        messages_layout = QVBoxLayout(messages_widget)
        messages_layout.setAlignment(Qt.AlignTop)
        messages_layout.setSpacing(15)
        
        # Messaggio di benvenuto
        welcome_frame = QFrame()
        welcome_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a3a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        welcome_layout = QHBoxLayout(welcome_frame)
        welcome_layout.setContentsMargins(15, 15, 15, 15)
        
        # Logo N+
        n_logo = QLabel("N+")
        n_logo.setFixedSize(40, 40)
        n_logo.setAlignment(Qt.AlignCenter)
        n_logo.setStyleSheet("""
            QLabel {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 2px solid #5a3a7a;
                border-radius: 20px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        welcome_layout.addWidget(n_logo)
        
        welcome_text = QLabel("Hi I am the administration manager, please submit your question")
        welcome_text.setWordWrap(True)
        welcome_text.setStyleSheet("color: #FFFFFF; font-size: 14px; padding: 10px;")
        welcome_layout.addWidget(welcome_text, 1)
        
        messages_layout.addWidget(welcome_frame)
        messages_layout.addStretch()
        
        scroll_area.setWidget(messages_widget)
        layout.addWidget(scroll_area, 1)
        
        # Area input
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        
        # Icona attachment (simulata con QLabel)
        attach_label = QLabel("📎")
        attach_label.setFixedSize(40, 40)
        attach_label.setAlignment(Qt.AlignCenter)
        attach_label.setStyleSheet("""
            QLabel {
                background-color: #2a2a3a;
                border-radius: 8px;
                font-size: 18px;
            }
        """)
        input_layout.addWidget(attach_label)
        
        # Campo input
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Prompt with data...")
        self.chat_input.setMinimumHeight(45)
        self.chat_input.setStyleSheet("""
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
        input_layout.addWidget(self.chat_input, 1)
        
        # Collega il tasto Invio al campo input
        self.chat_input.returnPressed.connect(self.send_message)
        
        # Pulsante invio
        send_button = QPushButton("✈")
        send_button.setFixedSize(45, 45)
        send_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        send_button.clicked.connect(self.send_message)
        input_layout.addWidget(send_button)
        
        layout.addLayout(input_layout)
        
        return panel
    
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
    
    def create_invoice(self):
        """Crea una nuova fattura e la aggiunge al CSV"""
        cliente = self.cliente_input.text().strip()
        importo = self.importo_input.value()
        data = self.data_input.date().toString("dd/MM/yyyy")
        
        if not cliente:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Inserisci il nome del cliente")
            return
        
        # Genera numero fattura
        invoice_number = self.generate_invoice_number()
        
        # Aggiungi al CSV
        try:
            with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([invoice_number, cliente, str(importo), data, "Pending"])
            
            # Pulisci i campi
            self.cliente_input.clear()
            self.importo_input.setValue(0.00)
            self.data_input.setDate(QDate.currentDate())
            
            # Ricarica la tabella (legacy - metodo neutralizzato)
            # self.load_csv_data()  # Rimosso - non più utilizzato
            
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Errore nel salvataggio: {e}")
    
    def generate_invoice_number(self):
        """Genera un numero di fattura univoco (FATT-YYYY-NNN)"""
        max_num = 0
        
        # Prova a leggere dal database
        try:
            from modules.orders_database import get_database_path
            import sqlite3
            db_path = get_database_path()
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT invoice_number FROM invoices WHERE invoice_number LIKE 'FATT-%'")
                rows = cursor.fetchall()
                conn.close()
                
                for row in rows:
                    inv_num = row[0]
                    if inv_num.startswith('FATT-'):
                        try:
                            parts = inv_num.split('-')
                            if len(parts) >= 3:
                                num = int(parts[2])
                                max_num = max(max_num, num)
                        except:
                            pass
        except:
            pass
        
        # Fallback: leggi da CSV se database non disponibile
        if max_num == 0:
            try:
                with open(self.csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        inv_num = row.get('Invoice Number', '')
                        if inv_num.startswith('FATT-') or inv_num.startswith('INV-'):
                            try:
                                parts = inv_num.split('-')
                                if len(parts) >= 3:
                                    num = int(parts[2])
                                    max_num = max(max_num, num)
                            except:
                                pass
            except:
                pass
        
        year = datetime.now().year
        new_num = max_num + 1
        return f"FATT-{year}-{new_num:03d}"
    
    def load_csv_data(self):
        """
        Metodo legacy - non più utilizzato.
        Mantenuto per compatibilità ma neutralizzato.
        Il sistema ora usa load_order_confirmations() per caricare i dati da JSON.
        """
        # Metodo neutralizzato - non fa più nulla
        # La nuova UI usa load_order_confirmations() che legge da logs/orders/*.json
        pass
    
    def send_message(self):
        """Gestisce l'invio del messaggio nella chat"""
        import traceback
        
        try:
            message = self.chat_input.text().strip()
            if not message:
                return
            
            print(f"\n[ADMINISTRATION WINDOW] Messaggio inviato: {message}")
            
            # TODO: Implementare logica di invio al motore neurale
            print(f"[ADMINISTRATION WINDOW] Funzione send_message chiamata correttamente")
            
            self.chat_input.clear()
            
        except Exception as e:
            print("\n" + "="*80)
            print("ERRORE IN send_message (ADMINISTRATION WINDOW):")
            print("="*80)
            traceback.print_exc()
            print("="*80 + "\n")
            # Non rilanciare l'eccezione per evitare crash
    
    def update_datetime(self):
        """Update header date/time (English)."""
        self.datetime_label.setText(format_header_datetime())
    
    def load_order_confirmations(self):
        """
        Carica le conferme d'ordine (fatture) dai file JSON in logs/orders/
        Mostra solo gli ordini con status='confirmed' e sent_confirmation_email.sent=True
        """
        if not hasattr(self, 'orders_table'):
            return
        
        self.order_confirmations = []
        self.selected_order_data = None
        self.orders_table.setRowCount(0)
        
        # Disabilita i pulsanti quando si ricarica
        if hasattr(self, 'open_order_folder_btn'):
            self.open_order_folder_btn.setEnabled(False)
        if hasattr(self, 'process_invoice_btn'):
            self.process_invoice_btn.setEnabled(False)
        self.selected_order_data = None
        
        try:
            # Verifica che la cartella esista
            if not self.orders_dir.exists():
                self.orders_dir.mkdir(parents=True, exist_ok=True)
                # Nessun file, mostra messaggio
                self.orders_table.setRowCount(1)
                self.orders_table.setItem(0, 0, QTableWidgetItem("Nessuna conferma d'ordine disponibile"))
                self.orders_table.setItem(0, 1, QTableWidgetItem(""))
                self.orders_table.setItem(0, 2, QTableWidgetItem(""))
                self.orders_table.setItem(0, 3, QTableWidgetItem(""))
                return
            
            # Leggi tutti i file JSON nella cartella orders/
            order_files = list(self.orders_dir.glob("order_*.json"))
            
            if not order_files:
                # Nessun file, mostra messaggio
                self.orders_table.setRowCount(1)
                self.orders_table.setItem(0, 0, QTableWidgetItem("Nessuna conferma d'ordine disponibile"))
                self.orders_table.setItem(0, 1, QTableWidgetItem(""))
                self.orders_table.setItem(0, 2, QTableWidgetItem(""))
                self.orders_table.setItem(0, 3, QTableWidgetItem(""))
                return
            
            # Carica e filtra gli ordini confermati
            confirmed_orders = []
            for order_file in order_files:
                try:
                    with open(order_file, 'r', encoding='utf-8') as f:
                        order_data = json.load(f)
                        
                        # Filtra solo ordini confermati con email inviata
                        status = order_data.get("status", "")
                        sent_email = order_data.get("sent_confirmation_email")
                        
                        if status == "confirmed" and sent_email and isinstance(sent_email, dict) and sent_email.get("sent") == True:
                            confirmed_orders.append(order_data)
                            
                except json.JSONDecodeError as e:
                    print(f"Errore nel parsing JSON {order_file.name}: {e}")
                    continue
                except Exception as e:
                    print(f"Errore nella lettura di {order_file.name}: {e}")
                    continue
            
            if not confirmed_orders:
                # Nessun ordine confermato, mostra messaggio
                self.orders_table.setRowCount(1)
                self.orders_table.setItem(0, 0, QTableWidgetItem("Nessuna conferma d'ordine disponibile"))
                self.orders_table.setItem(0, 1, QTableWidgetItem(""))
                self.orders_table.setItem(0, 2, QTableWidgetItem(""))
                self.orders_table.setItem(0, 3, QTableWidgetItem(""))
                return
            
            # Ordina per timestamp decrescente (più recenti prima)
            confirmed_orders.sort(
                key=lambda x: x.get("sent_confirmation_email", {}).get("timestamp", ""),
                reverse=True
            )
            
            # Limita a 100 ordini più recenti
            confirmed_orders = confirmed_orders[:100]
            
            # Salva i dati per accesso rapido
            self.order_confirmations = confirmed_orders
            
            # Popola la tabella
            self.orders_table.setRowCount(len(confirmed_orders))
            
            for row, order in enumerate(confirmed_orders):
                # ID ordine
                order_id = order.get("id", "UNKNOWN")
                self.orders_table.setItem(row, 0, QTableWidgetItem(order_id))
                
                # Cliente (da email)
                from_email = order.get("from", "")
                client_name = from_email.split("@")[0] if "@" in from_email else from_email
                self.orders_table.setItem(row, 1, QTableWidgetItem(client_name))
                
                # Data (timestamp conferma)
                sent_timestamp = order.get("sent_confirmation_email", {}).get("timestamp", "")
                if sent_timestamp:
                    try:
                        # Formatta la data
                        dt = datetime.fromisoformat(sent_timestamp.replace('Z', '+00:00'))
                        date_str = dt.strftime("%d/%m/%Y")
                    except:
                        date_str = sent_timestamp[:10] if len(sent_timestamp) >= 10 else sent_timestamp
                else:
                    date_str = "N/A"
                self.orders_table.setItem(row, 2, QTableWidgetItem(date_str))
                
                # Stato conferma
                status_item = QTableWidgetItem("Confermato")
                status_item.setBackground(QColor("#00FF00"))
                status_item.setForeground(QColor("#000000"))
                self.orders_table.setItem(row, 3, status_item)
            
        except Exception as e:
            print(f"Errore nel caricamento conferme d'ordine: {e}")
            import traceback
            traceback.print_exc()
            # Mostra messaggio di errore
            self.orders_table.setRowCount(1)
            self.orders_table.setItem(0, 0, QTableWidgetItem(f"Errore: {str(e)}"))
            self.orders_table.setItem(0, 1, QTableWidgetItem(""))
            self.orders_table.setItem(0, 2, QTableWidgetItem(""))
            self.orders_table.setItem(0, 3, QTableWidgetItem(""))
    
    def on_order_confirmation_clicked(self, item):
        """
        Gestisce il click su una riga della tabella conferme d'ordine
        Abilita i pulsanti per elaborazione e apertura cartella
        """
        row = item.row()
        
        # Verifica che la riga sia valida
        if row < 0 or row >= len(self.order_confirmations):
            return
        
        # Ottieni i dati dell'ordine
        order_data = self.order_confirmations[row]
        self.selected_order_data = order_data
        
        # Abilita i pulsanti quando viene selezionato un ordine
        if hasattr(self, 'open_order_folder_btn'):
            self.open_order_folder_btn.setEnabled(True)
        if hasattr(self, 'process_invoice_btn'):
            self.process_invoice_btn.setEnabled(True)
    
    def create_order_details_view(self, order_data):
        """
        Crea la vista dettagliata di una conferma d'ordine nel box destro
        """
        # ID Ordine
        order_id_label = QLabel(f"<b>ID Ordine:</b> {order_data.get('id', 'N/A')}")
        order_id_label.setStyleSheet("color: #FFFFFF; font-size: 14px; padding: 5px;")
        order_id_label.setWordWrap(True)
        self.details_layout.addWidget(order_id_label)
        
        # Cliente
        from_email = order_data.get("from", "N/A")
        client_label = QLabel(f"<b>Cliente:</b> {from_email}")
        client_label.setStyleSheet("color: #FFFFFF; font-size: 14px; padding: 5px;")
        client_label.setWordWrap(True)
        self.details_layout.addWidget(client_label)
        
        # Data ordine
        timestamp = order_data.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                date_str = dt.strftime("%d/%m/%Y %H:%M:%S")
            except:
                date_str = timestamp
        else:
            date_str = "N/A"
        date_label = QLabel(f"<b>Data Ordine:</b> {date_str}")
        date_label.setStyleSheet("color: #FFFFFF; font-size: 14px; padding: 5px;")
        self.details_layout.addWidget(date_label)
        
        # Stato
        status = order_data.get("status", "N/A")
        status_label = QLabel(f"<b>Stato:</b> {status}")
        status_label.setStyleSheet("color: #FFFFFF; font-size: 14px; padding: 5px;")
        self.details_layout.addWidget(status_label)
        
        # Separatore
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #2a2a3a; max-height: 1px; margin: 10px 0;")
        self.details_layout.addWidget(separator)
        
        # Email di conferma inviata
        sent_email = order_data.get("sent_confirmation_email", {})
        if sent_email and isinstance(sent_email, dict):
            email_title = QLabel("<b>Email di Conferma Inviata:</b>")
            email_title.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold; padding: 5px;")
            self.details_layout.addWidget(email_title)
            
            # Destinatario
            to_email = sent_email.get("to", "N/A")
            to_label = QLabel(f"<b>Destinatario:</b> {to_email}")
            to_label.setStyleSheet("color: #FFFFFF; font-size: 13px; padding: 5px;")
            to_label.setWordWrap(True)
            self.details_layout.addWidget(to_label)
            
            # Oggetto
            subject = sent_email.get("subject", "N/A")
            subject_label = QLabel(f"<b>Oggetto:</b> {subject}")
            subject_label.setStyleSheet("color: #FFFFFF; font-size: 13px; padding: 5px;")
            subject_label.setWordWrap(True)
            self.details_layout.addWidget(subject_label)
            
            # Timestamp invio
            sent_timestamp = sent_email.get("timestamp", "")
            if sent_timestamp:
                try:
                    dt = datetime.fromisoformat(sent_timestamp.replace('Z', '+00:00'))
                    sent_date_str = dt.strftime("%d/%m/%Y %H:%M:%S")
                except:
                    sent_date_str = sent_timestamp
            else:
                sent_date_str = "N/A"
            sent_date_label = QLabel(f"<b>Data Invio:</b> {sent_date_str}")
            sent_date_label.setStyleSheet("color: #FFFFFF; font-size: 13px; padding: 5px;")
            self.details_layout.addWidget(sent_date_label)
            
            # Corpo email
            body = sent_email.get("body", "N/A")
            body_title = QLabel("<b>Corpo Email:</b>")
            body_title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold; padding: 5px;")
            self.details_layout.addWidget(body_title)
            
            body_text = QTextEdit()
            body_text.setPlainText(body)
            body_text.setReadOnly(True)
            body_text.setStyleSheet("""
                QTextEdit {
                    background-color: #0a0a1a;
                    border: 1px solid #2a2a3a;
                    border-radius: 6px;
                    color: #FFFFFF;
                    padding: 10px;
                    font-size: 12px;
                }
            """)
            body_text.setMinimumHeight(200)
            self.details_layout.addWidget(body_text)
        
        # Separatore
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("background-color: #2a2a3a; max-height: 1px; margin: 10px 0;")
        self.details_layout.addWidget(separator2)
        
        # Oggetto ordine originale
        subject_original = order_data.get("subject", "N/A")
        subject_orig_label = QLabel(f"<b>Oggetto Ordine:</b> {subject_original}")
        subject_orig_label.setStyleSheet("color: #FFFFFF; font-size: 13px; padding: 5px;")
        subject_orig_label.setWordWrap(True)
        self.details_layout.addWidget(subject_orig_label)
        
        # Corpo ordine originale
        body_original = order_data.get("body", "")
        if body_original:
            body_orig_title = QLabel("<b>Corpo Ordine Originale:</b>")
            body_orig_title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold; padding: 5px;")
            self.details_layout.addWidget(body_orig_title)
            
            body_orig_text = QTextEdit()
            body_orig_text.setPlainText(body_original)
            body_orig_text.setReadOnly(True)
            body_orig_text.setStyleSheet("""
                QTextEdit {
                    background-color: #0a0a1a;
                    border: 1px solid #2a2a3a;
                    border-radius: 6px;
                    color: #FFFFFF;
                    padding: 10px;
                    font-size: 12px;
                }
            """)
            body_orig_text.setMinimumHeight(150)
            self.details_layout.addWidget(body_orig_text)
        
        # Note se presenti
        notes = order_data.get("notes", "")
        if notes:
            notes_title = QLabel("<b>Note:</b>")
            notes_title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold; padding: 5px;")
            self.details_layout.addWidget(notes_title)
            
            notes_label = QLabel(notes)
            notes_label.setStyleSheet("color: #AAAAAA; font-size: 12px; padding: 5px;")
            notes_label.setWordWrap(True)
            self.details_layout.addWidget(notes_label)
        
        # Aggiungi stretch alla fine
        self.details_layout.addStretch()
    
    def on_open_order_folder_clicked(self):
        """
        Gestisce il click sul pulsante "Apri cartella ordine"
        Apre la cartella logs/orders/ e seleziona il file JSON dell'ordine selezionato
        """
        if not self.selected_order_data:
            QMessageBox.warning(self, "Nessun ordine selezionato", 
                              "Seleziona una conferma d'ordine dalla tabella per aprire la cartella.")
            return
        
        order_id = self.selected_order_data.get("id", "")
        if not order_id:
            QMessageBox.warning(self, "Error", "ID ordine non valido.")
            return
        
        try:
            # Costruisci il percorso del file JSON
            order_file = self.orders_dir / f"order_{order_id}.json"
            
            # Su Windows, usa explorer per aprire la cartella e selezionare il file
            if platform.system() == 'Windows':
                if order_file.exists():
                    # Apri la cartella e seleziona il file
                    subprocess.run(['explorer', '/select,', str(order_file)], check=False)
                else:
                    # Se il file non esiste, apri comunque la cartella
                    os.startfile(str(self.orders_dir))
                    QMessageBox.information(self, "File non trovato", 
                                           f"Il file order_{order_id}.json non è stato trovato.\n"
                                           f"La cartella {self.orders_dir} è stata aperta.")
            else:
                # Per altri sistemi operativi
                if order_file.exists():
                    # Apri la cartella del file
                    if platform.system() == 'Darwin':  # macOS
                        subprocess.run(['open', '-R', str(order_file)], check=False)
                    else:  # Linux
                        subprocess.run(['xdg-open', str(self.orders_dir)], check=False)
                else:
                    # Apri solo la cartella
                    if platform.system() == 'Darwin':
                        subprocess.run(['open', str(self.orders_dir)], check=False)
                    else:
                        subprocess.run(['xdg-open', str(self.orders_dir)], check=False)
                    QMessageBox.information(self, "File non trovato", 
                                           f"Il file order_{order_id}.json non è stato trovato.\n"
                                           f"La cartella è stata aperta.")
        except Exception as e:
            QMessageBox.critical(self, "Error", 
                               f"Errore nell'apertura della cartella:\n{e}")
    
    def process_invoice_with_gemini(self):
        """
        Elabora la conferma d'ordine selezionata con Gemini per generare la fattura
        """
        if not self.selected_order_data:
            QMessageBox.warning(self, "Nessun ordine selezionato", 
                              "Seleziona una conferma d'ordine dalla tabella prima di elaborare.")
            return
        
        order_id = self.selected_order_data.get("id", "")
        if not order_id:
            QMessageBox.warning(self, "Error", "ID ordine non valido.")
            return
        
        try:
            # Disabilita il pulsante durante l'elaborazione
            self.process_invoice_btn.setEnabled(False)
            self.invoice_output_text.clear()
            self.invoice_output_text.append("⏳ Elaborazione in corso...")
            self.invoice_output_text.append("")
            
            # Importa GeminiService
            try:
                from llm.gemini_service import GeminiService
            except ImportError:
                self.invoice_output_text.append("❌ ERRORE: Impossibile importare GeminiService")
                self.invoice_output_text.append("Assicurati che gemini_service.py sia disponibile.")
                self.process_invoice_btn.setEnabled(True)
                return
            
            # Inizializza il servizio Gemini
            gemini_service = GeminiService()
            
            if not gemini_service.is_ready:
                self.invoice_output_text.append("❌ ERRORE: LLM non disponibile (Ollama o Gemini)")
                self.invoice_output_text.append("Avvia Ollama o configura API Key in Impostazioni")
                self.process_invoice_btn.setEnabled(True)
                return
            
            # Prepara i dati dell'ordine per Gemini
            order_data_text = f"""Dati Ordine:
- ID: {self.selected_order_data.get('id', 'N/A')}
- Cliente: {self.selected_order_data.get('from', 'N/A')}
- Oggetto: {self.selected_order_data.get('subject', 'N/A')}
- Data Ordine: {self.selected_order_data.get('timestamp', 'N/A')}
- Stato: {self.selected_order_data.get('status', 'N/A')}

Corpo Ordine:
{self.selected_order_data.get('body', 'N/A')}

Email di Conferma Inviata:
{self.selected_order_data.get('sent_confirmation_email', {}).get('body', 'N/A')}
"""
            
            # Costruisci il prompt per Gemini
            prompt = f"""Sei un assistente specializzato nella generazione di fatture per NStone, azienda specializzata nella lavorazione e vendita di lastre di marmo e pietre naturali.

Dati dell'ordine confermato:
{order_data_text}

Genera una fattura professionale in formato testo che includa:
1. Intestazione con logo NStone (testuale)
2. Dati cliente (nome, email)
3. Numero fattura (formato: FATT-YYYY-NNN)
4. Data fattura (data corrente)
5. Descrizione prodotti/servizi basata sui dati dell'ordine
6. Quantità e prezzi (stima realistica basata sui dati disponibili)
7. Calcolo IVA al 22%
8. Totale
9. Note e condizioni di pagamento
10. Dati azienda (NStone)

La fattura deve essere professionale, chiara e completa. Usa dati realistici ma coerenti con l'ordine ricevuto.
"""
            
            self.invoice_output_text.append("📡 Invio richiesta a Gemini...")
            
            # Chiama Gemini
            invoice_text = gemini_service.send_message(prompt)
            
            if not invoice_text or not invoice_text.strip():
                self.invoice_output_text.append("❌ ERRORE: Nessuna risposta da Gemini")
                self.process_invoice_btn.setEnabled(True)
                return
            
            self.invoice_output_text.append("✅ Fattura generata con successo!")
            self.invoice_output_text.append("")
            
            # Genera numero fattura
            invoice_number = self.generate_invoice_number()
            
            # Salva il file
            invoice_filename = f"invoice_{invoice_number}.txt"
            invoice_file = self.invoices_ready_dir / invoice_filename
            
            try:
                with open(invoice_file, 'w', encoding='utf-8') as f:
                    f.write(invoice_text)
                
                # Salva fattura nel database
                try:
                    from modules.orders_database import save_invoice
                    client_email = self.selected_order_data.get("from", "")
                    save_invoice(
                        invoice_number=invoice_number,
                        order_id=order_id,
                        file_path=str(invoice_file),
                        client_email=client_email
                    )
                    self.invoice_output_text.append(f"💾 Fattura salvata nel database")
                except Exception as db_error:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Errore salvataggio fattura nel database: {db_error}")
                    self.invoice_output_text.append(f"⚠️ Avviso: Fattura salvata solo su file")
                
                self.invoice_output_text.append(f"💾 File salvato:")
                self.invoice_output_text.append(f"   {invoice_file}")
                self.invoice_output_text.append("")
                
            except Exception as save_error:
                self.invoice_output_text.append(f"⚠️ ATTENZIONE: Errore nel salvataggio del file:")
                self.invoice_output_text.append(f"   {str(save_error)}")
                self.invoice_output_text.append("")
            
            # Mostra anteprima della fattura (prime 50 righe)
            invoice_lines = invoice_text.split('\n')
            preview_lines = invoice_lines[:50]
            preview_text = '\n'.join(preview_lines)
            
            if len(invoice_lines) > 50:
                preview_text += f"\n\n... (altre {len(invoice_lines) - 50} righe) ..."
            
            self.invoice_output_text.append("📄 Anteprima Fattura:")
            self.invoice_output_text.append("=" * 60)
            self.invoice_output_text.append(preview_text)
            self.invoice_output_text.append("=" * 60)
            
            # Abilita di nuovo il pulsante
            self.process_invoice_btn.setEnabled(True)
            
        except Exception as e:
            error_msg = f"❌ ERRORE durante l'elaborazione:\n{str(e)}"
            self.invoice_output_text.append(error_msg)
            import traceback
            self.invoice_output_text.append("\nTraceback completo:")
            self.invoice_output_text.append(traceback.format_exc())
            self.process_invoice_btn.setEnabled(True)
            QMessageBox.critical(self, "Error", 
                               f"Errore durante l'elaborazione della fattura:\n{e}")
    
    def load_invoices_ready(self):
        """
        Carica l'elenco delle fatture generate da Gemini da logs/invoices_ready/
        """
        if not hasattr(self, 'invoices_table'):
            return
        
        self.invoices_ready_list = []
        self.invoices_table.setRowCount(0)
        
        try:
            # Verifica che la cartella esista
            if not self.invoices_ready_dir.exists():
                self.invoices_ready_dir.mkdir(parents=True, exist_ok=True)
                # Nessun file, mostra messaggio
                self.invoices_table.setRowCount(1)
                self.invoices_table.setItem(0, 0, QTableWidgetItem("Nessuna fattura disponibile"))
                self.invoices_table.setItem(0, 1, QTableWidgetItem(""))
                self.invoices_table.setItem(0, 2, QTableWidgetItem(""))
                return
            
            # Leggi tutti i file .txt nella cartella invoices_ready/
            invoice_files = list(self.invoices_ready_dir.glob("invoice_*.txt"))
            
            if not invoice_files:
                # Nessun file, mostra messaggio
                self.invoices_table.setRowCount(1)
                self.invoices_table.setItem(0, 0, QTableWidgetItem("Nessuna fattura disponibile"))
                self.invoices_table.setItem(0, 1, QTableWidgetItem(""))
                self.invoices_table.setItem(0, 2, QTableWidgetItem(""))
                return
            
            # Ordina per data di modifica decrescente (più recenti prima)
            invoice_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Salva i file nella lista
            self.invoices_ready_list = invoice_files
            
            # Popola la tabella
            self.invoices_table.setRowCount(len(invoice_files))
            
            for row, invoice_file in enumerate(invoice_files):
                # Nome file
                filename = invoice_file.name
                self.invoices_table.setItem(row, 0, QTableWidgetItem(filename))
                
                # ID ordine (estratto dal nome file: invoice_<id>.txt)
                order_id = "N/A"
                if filename.startswith("invoice_") and filename.endswith(".txt"):
                    order_id = filename[8:-4]  # Rimuove "invoice_" e ".txt"
                self.invoices_table.setItem(row, 1, QTableWidgetItem(order_id))
                
                # Data generazione
                try:
                    mtime = invoice_file.stat().st_mtime
                    dt = datetime.fromtimestamp(mtime)
                    date_str = dt.strftime("%d/%m/%Y %H:%M")
                except:
                    date_str = "N/A"
                self.invoices_table.setItem(row, 2, QTableWidgetItem(date_str))
            
            # Disabilita il pulsante se nessuna selezione
            if hasattr(self, 'send_invoice_btn'):
                self.send_invoice_btn.setEnabled(False)
            self.selected_invoice_file = None
            self.selected_invoice_order_id = None
            
        except Exception as e:
            print(f"Errore nel caricamento fatture: {e}")
            import traceback
            traceback.print_exc()
            # Mostra messaggio di errore
            self.invoices_table.setRowCount(1)
            self.invoices_table.setItem(0, 0, QTableWidgetItem(f"Errore: {str(e)}"))
            self.invoices_table.setItem(0, 1, QTableWidgetItem(""))
            self.invoices_table.setItem(0, 2, QTableWidgetItem(""))
    
    def on_invoice_selected(self, item):
        """
        Gestisce la selezione di una fattura dalla tabella
        Abilita il pulsante di invio
        """
        if not hasattr(self, 'invoices_table'):
            return
        
        row = item.row()
        
        # Verifica che la riga sia valida
        if row < 0 or row >= len(self.invoices_ready_list):
            return
        
        # Ottieni il file della fattura
        invoice_file = self.invoices_ready_list[row]
        self.selected_invoice_file = invoice_file
        
        # Estrai ID ordine dal nome file
        filename = invoice_file.name
        if filename.startswith("invoice_") and filename.endswith(".txt"):
            self.selected_invoice_order_id = filename[8:-4]  # Rimuove "invoice_" e ".txt"
        else:
            self.selected_invoice_order_id = None
        
        # Abilita il pulsante
        if hasattr(self, 'send_invoice_btn'):
            self.send_invoice_btn.setEnabled(True)
    
    def send_invoice_via_smtp(self):
        """
        Invia la fattura selezionata via SMTP Gmail al cliente dell'ordine originale
        """
        if not self.selected_invoice_file or not self.selected_invoice_file.exists():
            QMessageBox.warning(self, "Nessuna fattura selezionata", 
                              "Seleziona una fattura dalla tabella prima di inviare.")
            return
        
        if not self.selected_invoice_order_id:
            QMessageBox.warning(self, "Error", "ID ordine non valido.")
            return
        
        try:
            # Disabilita il pulsante durante l'invio
            self.send_invoice_btn.setEnabled(False)
            
            # Importa modulo email
            try:
                from modules.email_service import _load_gmail_credentials
            except ImportError:
                QMessageBox.critical(self, "Error", "Impossibile importare modulo email")
                self.send_invoice_btn.setEnabled(True)
                return
            
            # Carica credenziali Gmail
            email, app_password = _load_gmail_credentials()
            
            if not email or not app_password:
                QMessageBox.warning(self, "Credenziali mancanti", 
                                  "Credenziali Gmail non configurate.\nConfigura email e app_password in config.json")
                self.send_invoice_btn.setEnabled(True)
                return
            
            # Recupera email cliente da logs/orders/order_<id>.json
            order_file = self.orders_dir / f"order_{self.selected_invoice_order_id}.json"
            
            if not order_file.exists():
                QMessageBox.warning(self, "File non trovato", 
                                  f"File ordine non trovato:\n{order_file}")
                self.send_invoice_btn.setEnabled(True)
                return
            
            # Leggi dati ordine
            with open(order_file, 'r', encoding='utf-8') as f:
                order_data = json.load(f)
            
            client_email = order_data.get("from", "")
            
            if not client_email:
                QMessageBox.warning(self, "Email mancante", 
                                  "Email cliente non trovata nell'ordine")
                self.send_invoice_btn.setEnabled(True)
                return
            
            # Leggi contenuto fattura
            with open(self.selected_invoice_file, 'r', encoding='utf-8') as f:
                invoice_content = f.read()
            
            # Costruisci email
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = email
            msg['To'] = client_email
            msg['Subject'] = f"Fattura ordine {self.selected_invoice_order_id}"
            
            # Corpo email
            email_body = f"""Gentile Cliente,

in allegato trovi la fattura relativa al tuo ordine {self.selected_invoice_order_id}.

Cordiali saluti,
NStone"""
            
            msg.attach(MIMEText(email_body, 'plain', 'utf-8'))
            
            # Aggiungi la fattura come allegato (nel corpo dell'email per semplicità)
            # In alternativa si potrebbe usare MIMEBase per un vero allegato
            msg.attach(MIMEText("\n\n" + "="*60 + "\nFATTURA\n" + "="*60 + "\n\n" + invoice_content, 'plain', 'utf-8'))
            
            # Invia email via SMTP
            server = None
            try:
                logger.info(f"Connessione a smtp.gmail.com:587...")
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.set_debuglevel(1)  # Debug SMTP
                logger.info("Avvio TLS...")
                server.starttls()
                logger.info("Login SMTP in corso...")
                server.login(email, app_password)
                logger.info("Login completato, invio email...")
                server.send_message(msg)
                logger.info("Email inviata con successo")
            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"Errore autenticazione SMTP: {e}")
                QMessageBox.critical(self, "Errore autenticazione", 
                                  f"Errore durante l'autenticazione Gmail:\n{e}\n\nVerifica le credenziali in config.json")
                self.send_invoice_btn.setEnabled(True)
                return
            except smtplib.SMTPServerDisconnected as e:
                logger.error(f"Server SMTP disconnesso: {e}")
                QMessageBox.critical(self, "Errore connessione", 
                                  f"Errore di connessione al server SMTP:\n{e}")
                self.send_invoice_btn.setEnabled(True)
                return
            except smtplib.SMTPException as e:
                logger.error(f"Errore SMTP: {e}")
                QMessageBox.critical(self, "Errore SMTP", 
                                  f"Errore durante l'invio email:\n{e}")
                self.send_invoice_btn.setEnabled(True)
                return
            except Exception as e:
                logger.error(f"Errore generico invio email: {e}")
                import traceback
                logger.error(traceback.format_exc())
                QMessageBox.critical(self, "Error", 
                                  f"Errore inaspettato durante l'invio email:\n{e}")
                self.send_invoice_btn.setEnabled(True)
                return
            finally:
                if server is not None:
                    try:
                        server.quit()
                        logger.info("Connessione SMTP chiusa")
                    except Exception as e:
                        logger.warning(f"Errore chiusura connessione SMTP: {e}")
            
            # Aggiorna stato fattura nel database
            try:
                from modules.orders_database import update_invoice_status
                # Estrai numero fattura dal nome file
                invoice_number = self.selected_invoice_file.stem.replace("invoice_", "")
                data_invio = datetime.now().isoformat()
                update_invoice_status(invoice_number, "INVIATA", data_invio)
            except Exception as db_error:
                logger.error(f"Errore aggiornamento stato fattura: {db_error}")
            
            # Abilita di nuovo il pulsante
            self.send_invoice_btn.setEnabled(True)
            
            QMessageBox.information(self, "Fattura inviata", 
                                  f"Fattura inviata con successo a {client_email}")
            
        except Exception as e:
            self.send_invoice_btn.setEnabled(True)
            QMessageBox.critical(self, "Error", 
                               f"Errore durante l'invio della fattura:\n{e}")
            import traceback
            traceback.print_exc()
    
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

