"""
Nstone LLM - Finestra Call Center AI
Gestione chiamate VoIP e Asterisk
"""
import os
import sys
from datetime import datetime
from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QListWidget,
                             QGroupBox, QProgressBar)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


class CallCenterWindow(SectionDialog):
    """Finestra Call Center AI per gestione chiamate VoIP e Asterisk"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Call Center AI")
        self.setMinimumSize(1600, 900)
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
        
        # Contenuto principale - Sezione Call Center AI
        call_center_section = self.create_call_center_section()
        main_layout.addWidget(call_center_section, 1)
        
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
        title_label = QLabel("Call Center AI")
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
    
    def create_call_center_section(self):
        """Crea la sezione Call Center AI con tre box orizzontali"""
        section_widget = QWidget()
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(20, 20, 20, 20)
        section_layout.setSpacing(15)
        
        # Titolo e descrizione
        title_label = QLabel("Call Center AI")
        title_label.setStyleSheet("""
            QLabel {
                color: #E8E8E8;
                font-size: 22px;
                font-weight: bold;
                background: transparent;
            }
        """)
        section_layout.addWidget(title_label)
        
        desc_label = QLabel("VoIP calls and Asterisk service management")
        desc_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 13px;
                background: transparent;
            }
        """)
        section_layout.addWidget(desc_label)
        
        # Layout a 3 colonne orizzontali
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(15)
        
        # BOX SINISTRA - Chiamate in Entrata
        left_box = self.create_chiamate_entrata_box()
        columns_layout.addWidget(left_box, 1)
        
        # BOX CENTRO - Stato Servizio
        center_box = self.create_stato_servizio_box()
        columns_layout.addWidget(center_box, 1)
        
        # BOX DESTRA - Chiamate in Uscita
        right_box = self.create_chiamate_uscita_box()
        columns_layout.addWidget(right_box, 1)
        
        section_layout.addLayout(columns_layout, 1)
        
        return section_widget
    
    def create_chiamate_entrata_box(self):
        """Crea il box sinistro: Chiamate in Entrata"""
        self.boxChiamateEntrata = QGroupBox("Chiamate in Entrata")
        self.boxChiamateEntrata.setStyleSheet("""
            QGroupBox {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                padding: 15px;
                font-size: 16px;
                font-weight: bold;
                color: #E8E8E8;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        box_layout = QVBoxLayout(self.boxChiamateEntrata)
        box_layout.setContentsMargins(15, 25, 15, 15)
        box_layout.setSpacing(15)
        
        # Lista chiamate entranti
        calls_list = QListWidget()
        calls_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(20, 20, 30, 150);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                color: #E8E8E8;
                font-size: 12px;
                padding: 8px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(179, 211, 255, 30);
            }
            QListWidget::item:selected {
                background-color: rgba(0, 217, 255, 80);
                color: #E8E8E8;
            }
        """)
        calls_list.addItem("Nessuna chiamata in entrata")
        box_layout.addWidget(calls_list, 1)
        
        # Interfaccia audio player
        audio_frame = QFrame()
        audio_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 10px;
            }
        """)
        audio_layout = QVBoxLayout(audio_frame)
        audio_layout.setSpacing(10)
        
        # Barra di avanzamento (placeholder)
        self.audioPlayerEntrata = QProgressBar()
        self.audioPlayerEntrata.setMinimum(0)
        self.audioPlayerEntrata.setMaximum(100)
        self.audioPlayerEntrata.setValue(0)
        self.audioPlayerEntrata.setStyleSheet("""
            QProgressBar {
                background-color: rgba(15, 15, 25, 150);
                border: 1px solid rgba(179, 211, 255, 50);
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: rgba(0, 217, 255, 200);
                border-radius: 4px;
            }
        """)
        audio_layout.addWidget(self.audioPlayerEntrata)
        
        # Bottoni audio
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        btn_play = QPushButton("▶ Ascolta")
        btn_play.setMinimumHeight(35)
        btn_play.setStyleSheet("""
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
        btn_play.clicked.connect(self.on_ascolta_entrata_clicked)
        buttons_layout.addWidget(btn_play)
        
        btn_stop = QPushButton("⏹ Ferma")
        btn_stop.setMinimumHeight(35)
        btn_stop.setStyleSheet("""
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
        btn_stop.clicked.connect(self.on_ferma_entrata_clicked)
        buttons_layout.addWidget(btn_stop)
        
        audio_layout.addLayout(buttons_layout)
        box_layout.addWidget(audio_frame)
        
        return self.boxChiamateEntrata
    
    def create_stato_servizio_box(self):
        """Crea il box centrale: Stato Servizio Asterisk & VoIP"""
        self.boxStatoServizio = QGroupBox("Stato Servizio Asterisk & VoIP")
        self.boxStatoServizio.setStyleSheet("""
            QGroupBox {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                padding: 15px;
                font-size: 16px;
                font-weight: bold;
                color: #E8E8E8;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        box_layout = QVBoxLayout(self.boxStatoServizio)
        box_layout.setContentsMargins(15, 25, 15, 15)
        box_layout.setSpacing(15)
        
        # Stato Asterisk
        asterisk_frame = QFrame()
        asterisk_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        asterisk_layout = QHBoxLayout(asterisk_frame)
        asterisk_layout.setSpacing(10)
        
        # Indicatore stato (verde/rosso)
        asterisk_indicator = QLabel("●")
        asterisk_indicator.setStyleSheet("color: #00FF00; font-size: 20px; background: transparent;")
        asterisk_layout.addWidget(asterisk_indicator)
        
        asterisk_label = QLabel("Asterisk: Attivo")
        asterisk_label.setStyleSheet("color: #E8E8E8; font-size: 14px; font-weight: bold; background: transparent;")
        asterisk_layout.addWidget(asterisk_label)
        asterisk_layout.addStretch()
        
        box_layout.addWidget(asterisk_frame)
        
        # Stato VoIP
        voip_frame = QFrame()
        voip_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        voip_layout = QHBoxLayout(voip_frame)
        voip_layout.setSpacing(10)
        
        # Indicatore stato (verde/rosso)
        voip_indicator = QLabel("●")
        voip_indicator.setStyleSheet("color: #00FF00; font-size: 20px; background: transparent;")
        voip_layout.addWidget(voip_indicator)
        
        voip_label = QLabel("VoIP: Registrato")
        voip_label.setStyleSheet("color: #E8E8E8; font-size: 14px; font-weight: bold; background: transparent;")
        voip_layout.addWidget(voip_label)
        voip_layout.addStretch()
        
        box_layout.addWidget(voip_frame)
        
        box_layout.addStretch()
        
        # Bottoni azioni
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(10)
        
        btn_riavvia = QPushButton("Riavvia Servizio")
        btn_riavvia.setMinimumHeight(40)
        btn_riavvia.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 217, 255, 150);
                color: #0A0A15;
                border: 1px solid rgba(0, 217, 255, 200);
                border-radius: 8px;
                padding: 10px 20px;
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
        btn_riavvia.clicked.connect(self.on_riavvia_servizio_clicked)
        actions_layout.addWidget(btn_riavvia)
        
        btn_test = QPushButton("Test Chiamata")
        btn_test.setMinimumHeight(40)
        btn_test.setStyleSheet("""
            QPushButton {
                background-color: rgba(23, 147, 209, 120);
                color: #E8E8E8;
                border: 1px solid rgba(0, 217, 255, 100);
                border-radius: 8px;
                padding: 10px 20px;
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
        btn_test.clicked.connect(self.on_test_chiamata_clicked)
        actions_layout.addWidget(btn_test)
        
        box_layout.addLayout(actions_layout)
        
        return self.boxStatoServizio
    
    def create_chiamate_uscita_box(self):
        """Crea il box destro: Chiamate in Uscita"""
        self.boxChiamateUscita = QGroupBox("Chiamate in Uscita")
        self.boxChiamateUscita.setStyleSheet("""
            QGroupBox {
                background-color: rgba(30, 30, 40, 180);
                border: 1px solid rgba(179, 211, 255, 80);
                border-radius: 12px;
                padding: 15px;
                font-size: 16px;
                font-weight: bold;
                color: #E8E8E8;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        box_layout = QVBoxLayout(self.boxChiamateUscita)
        box_layout.setContentsMargins(15, 25, 15, 15)
        box_layout.setSpacing(15)
        
        # Lista chiamate effettuate
        calls_list = QListWidget()
        calls_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(20, 20, 30, 150);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                color: #E8E8E8;
                font-size: 12px;
                padding: 8px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(179, 211, 255, 30);
            }
            QListWidget::item:selected {
                background-color: rgba(0, 217, 255, 80);
                color: #E8E8E8;
            }
        """)
        calls_list.addItem("Nessuna chiamata in uscita")
        box_layout.addWidget(calls_list, 1)
        
        # Interfaccia audio player
        audio_frame = QFrame()
        audio_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 30, 120);
                border: 1px solid rgba(179, 211, 255, 60);
                border-radius: 8px;
                padding: 10px;
            }
        """)
        audio_layout = QVBoxLayout(audio_frame)
        audio_layout.setSpacing(10)
        
        # Barra di avanzamento (placeholder)
        self.audioPlayerUscita = QProgressBar()
        self.audioPlayerUscita.setMinimum(0)
        self.audioPlayerUscita.setMaximum(100)
        self.audioPlayerUscita.setValue(0)
        self.audioPlayerUscita.setStyleSheet("""
            QProgressBar {
                background-color: rgba(15, 15, 25, 150);
                border: 1px solid rgba(179, 211, 255, 50);
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: rgba(0, 217, 255, 200);
                border-radius: 4px;
            }
        """)
        audio_layout.addWidget(self.audioPlayerUscita)
        
        # Bottoni audio
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        btn_play = QPushButton("▶ Ascolta")
        btn_play.setMinimumHeight(35)
        btn_play.setStyleSheet("""
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
        btn_play.clicked.connect(self.on_ascolta_uscita_clicked)
        buttons_layout.addWidget(btn_play)
        
        btn_stop = QPushButton("⏹ Ferma")
        btn_stop.setMinimumHeight(35)
        btn_stop.setStyleSheet("""
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
        btn_stop.clicked.connect(self.on_ferma_uscita_clicked)
        buttons_layout.addWidget(btn_stop)
        
        audio_layout.addLayout(buttons_layout)
        box_layout.addWidget(audio_frame)
        
        return self.boxChiamateUscita
    
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
    
    # Callback functions (solo struttura, non logica)
    def on_ascolta_entrata_clicked(self):
        """Callback per il bottone Ascolta (entrata)"""
        pass
    
    def on_ferma_entrata_clicked(self):
        """Callback per il bottone Ferma (entrata)"""
        pass
    
    def on_riavvia_servizio_clicked(self):
        """Callback per il bottone Riavvia Servizio"""
        pass
    
    def on_test_chiamata_clicked(self):
        """Callback per il bottone Test Chiamata"""
        pass
    
    def on_ascolta_uscita_clicked(self):
        """Callback per il bottone Ascolta (uscita)"""
        pass
    
    def on_ferma_uscita_clicked(self):
        """Callback per il bottone Ferma (uscita)"""
        pass





