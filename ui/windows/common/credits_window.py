"""
Nstone LLM - Finestra Credits
Informazioni su sviluppatore, versione e crediti
"""
import os
import sys
from datetime import datetime
from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QGroupBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


class CreditsWindow(SectionDialog):
    """Finestra Credits per informazioni su sviluppatore e versione"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Credits")
        self.setMinimumSize(800, 600)
        self.setModal(False)
        
        # Inizializza UI
        self.init_ui()
        self.apply_stylesheet()
        self.setup_timer()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Contenuto principale - Sezione Credits
        self.creditsPage = self.create_credits_section()
        main_layout.addWidget(self.creditsPage, 1)
        
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
        title_label = QLabel("Credits")
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
        
        return header_frame
    
    def create_credits_section(self):
        """Crea la sezione Credits con informazioni"""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(20, 20, 20, 20)
        section_layout.setSpacing(20)
        
        # Titolo grande centrato
        title_label = QLabel("Credits")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 36px;
                font-weight: bold;
                background: transparent;
                padding: 20px;
            }
        """)
        section_layout.addWidget(title_label)
        
        # Spacer per centratura verticale
        section_layout.addStretch()
        
        # QGroupBox centrale con informazioni
        self.boxCreditsInfo = QGroupBox()
        self.boxCreditsInfo.setStyleSheet("""
            QGroupBox {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                padding: 30px;
                margin: 0px;
            }
        """)
        self.boxCreditsInfo.setAlignment(Qt.AlignCenter)
        
        box_layout = QVBoxLayout(self.boxCreditsInfo)
        box_layout.setContentsMargins(40, 40, 40, 40)
        box_layout.setSpacing(25)
        box_layout.setAlignment(Qt.AlignCenter)
        
        # Sviluppatore
        dev_label = QLabel("Sviluppatore")
        dev_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(dev_label)
        
        dev_value = QLabel("Nicolò Marconi")
        dev_value.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(dev_value)
        
        box_layout.addSpacing(10)
        
        # Ruolo
        role_label = QLabel("Ruolo")
        role_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(role_label)
        
        role_value = QLabel("Sviluppatore Software & AI Engineer")
        role_value.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 16px;
                background: transparent;
            }
        """)
        box_layout.addWidget(role_value)
        
        box_layout.addSpacing(10)
        
        # Versione software
        version_label = QLabel("Versione Software")
        version_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(version_label)
        
        version_value = QLabel("NStone LLM 0.0.12")
        version_value.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 16px;
                background: transparent;
            }
        """)
        box_layout.addWidget(version_value)
        
        box_layout.addSpacing(10)
        
        # Anno
        year_label = QLabel("Anno")
        year_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(year_label)
        
        year_value = QLabel("2025")
        year_value.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 16px;
                background: transparent;
            }
        """)
        box_layout.addWidget(year_value)
        
        box_layout.addSpacing(20)
        
        # Ringraziamenti
        thanks_label = QLabel("Ringraziamenti")
        thanks_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }
        """)
        box_layout.addWidget(thanks_label)
        
        thanks_value = QLabel("Grazie per aver scelto NStone LLM.\nAgentic OS for natural stone.")
        thanks_value.setAlignment(Qt.AlignCenter)
        thanks_value.setWordWrap(True)
        thanks_value.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 14px;
                background: transparent;
                padding: 10px;
            }
        """)
        box_layout.addWidget(thanks_value)
        
        # Centra orizzontalmente il box
        section_layout.addWidget(self.boxCreditsInfo, 0, Qt.AlignHCenter | Qt.AlignVCenter)
        
        # Spacer per centratura verticale
        section_layout.addStretch()
        
        return section_widget
    
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
    
    def setup_timer(self):
        """Configura il timer per aggiornare data e ora"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_datetime)
        self.timer.start(1000)
    
    def update_datetime(self):
        """Update header date/time (English)."""
        self.datetime_label.setText(format_header_datetime())
    
    def go_back(self):
        """Porta il focus alla dashboard (sezione resta aperta o in icona)."""
        self.go_back_to_dashboard()





