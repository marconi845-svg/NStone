"""
Nstone LLM - Finestra Quotations
Gestione preventivi e quotazioni
"""
import os
import sys
from pathlib import Path
from datetime import datetime
from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTextEdit, QLineEdit)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


class QuotationsWindow(SectionDialog):
    """Finestra Quotations per gestire preventivi"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quotations")
        self.setMinimumSize(1400, 800)
        self.setModal(False)
        
        # Tab selezionato
        self.selected_tab = "Slabs"
        
        self.init_ui()
        self.apply_stylesheet()
        
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Navigazione tabs
        tabs = self.create_tabs()
        main_layout.addWidget(tabs)
        
        # Contenuto principale
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(40, 40, 40, 40)
        content_layout.setSpacing(30)
        content_layout.setAlignment(Qt.AlignCenter)
        
        # Messaggio di benvenuto
        welcome_label = QLabel("Welcome at Nstone LLM, submit your enquiry, I will give you my reply.")
        welcome_label.setAlignment(Qt.AlignCenter)
        welcome_label.setWordWrap(True)
        welcome_label.setStyleSheet("""
            color: #FFFFFF;
            font-size: 18px;
            padding: 20px;
        """)
        # Font moderno
        font = QFont()
        font_families = ["Montserrat", "Roboto", "Open Sans", "Segoe UI", "Arial"]
        for font_family in font_families:
            font.setFamily(font_family)
            if font.exactMatch():
                break
        font.setPointSize(18)
        welcome_label.setFont(font)
        content_layout.addWidget(welcome_label)
        
        # Area input
        input_area = self.create_input_area()
        content_layout.addWidget(input_area)
        
        content_layout.addStretch()
        
        main_layout.addWidget(content_widget, 1)
        
        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)
        
    def create_header(self):
        """Crea l'header con info sviluppatore e data/ora"""
        header_frame = QFrame()
        header_frame.setFixedHeight(60)
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 10, 20, 10)
        
        # Pulsante Back
        back_button = QPushButton("← Back")
        back_button.setMinimumHeight(35)
        back_button.setMinimumWidth(100)
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 2px solid #5a3a7a;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 2px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
                border: 2px solid #4a2a6a;
            }
        """)
        back_button.clicked.connect(self.go_back)
        header_layout.addWidget(back_button)
        
        header_layout.addStretch()
        
        # Info sviluppatore
        developer_label = QLabel("NStone")
        developer_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        header_layout.addWidget(developer_label)
        
        # Spacer
        header_layout.addStretch()
        
        # Data e ora a destra
        self.datetime_label = QLabel()
        self.datetime_label.setStyleSheet("color: #FFFFFF; font-size: 11px;")
        self.update_datetime()
        header_layout.addWidget(self.datetime_label)
        
        # Timer per aggiornare data/ora
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_datetime)
        self.timer.start(1000)
        
        return header_frame
    
    def create_tabs(self):
        """Crea la barra di navigazione con tabs"""
        tabs_frame = QFrame()
        tabs_frame.setFixedHeight(50)
        tabs_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border-bottom: 1px solid #2a2a3a;
            }
        """)
        tabs_layout = QHBoxLayout(tabs_frame)
        tabs_layout.setContentsMargins(20, 10, 20, 10)
        tabs_layout.setSpacing(0)
        
        # Tabs
        self.tab_buttons = {}
        tabs = ["Slabs", "Cut to Size", "Blocks"]
        
        for tab_name in tabs:
            tab_button = QPushButton(tab_name)
            tab_button.setMinimumHeight(35)
            tab_button.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #AAAAAA;
                    border: none;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 8px 20px;
                }
                QPushButton:hover {
                    color: #FFFFFF;
                    background-color: #2a2a3a;
                }
            """)
            tab_button.clicked.connect(lambda checked, name=tab_name: self.select_tab(name))
            tabs_layout.addWidget(tab_button)
            self.tab_buttons[tab_name] = tab_button
        
        # Imposta tab iniziale
        self.select_tab("Slabs")
        
        tabs_layout.addStretch()
        
        return tabs_frame
    
    def create_input_area(self):
        """Crea l'area di input per il prompt"""
        input_frame = QFrame()
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(15)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        # Campo di input
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Please insert your prompt")
        self.prompt_input.setMinimumHeight(150)
        self.prompt_input.setMaximumHeight(200)
        self.prompt_input.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 8px;
                padding: 15px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border: 2px solid #5a3a7a;
            }
        """)
        input_layout.addWidget(self.prompt_input)
        
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
        send_button.clicked.connect(self.send_prompt)
        input_layout.addWidget(send_button, 0, Qt.AlignHCenter)
        
        return input_frame
    
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
    
    def select_tab(self, tab_name):
        """Seleziona un tab"""
        self.selected_tab = tab_name
        
        # Aggiorna stile dei pulsanti
        for name, button in self.tab_buttons.items():
            if name == tab_name:
                button.setStyleSheet("""
                    QPushButton {
                        background-color: #4a2a6a;
                        color: #FFFFFF;
                        border: none;
                        font-size: 14px;
                        font-weight: bold;
                        padding: 8px 20px;
                        border-bottom: 3px solid #8B5CF6;
                    }
                    QPushButton:hover {
                        background-color: #5a3a7a;
                    }
                """)
            else:
                button.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #AAAAAA;
                        border: none;
                        font-size: 14px;
                        font-weight: bold;
                        padding: 8px 20px;
                    }
                    QPushButton:hover {
                        color: #FFFFFF;
                        background-color: #2a2a3a;
                    }
                """)
    
    def send_prompt(self):
        """Gestisce l'invio del prompt"""
        prompt = self.prompt_input.toPlainText().strip()
        if prompt:
            # TODO: Implementare logica di invio al motore neurale
            print(f"Prompt inviato ({self.selected_tab}): {prompt}")
            # Per ora mostra un messaggio
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Prompt Inviato", 
                                   f"Prompt inviato per {self.selected_tab}:\n\n{prompt}")
            # Pulisci il campo
            self.prompt_input.clear()
    
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

