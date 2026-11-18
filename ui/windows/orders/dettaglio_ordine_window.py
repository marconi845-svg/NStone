"""
Nstone LLM - Finestra Dettaglio Ordine
Visualizza i dettagli completi di un ordine (sola lettura)
"""
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QTextEdit, QScrollArea, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class DettaglioOrdineWindow(SectionDialog):
    """
    Finestra per visualizzare i dettagli completi di un ordine
    Solo lettura, nessuna modifica
    """
    
    def __init__(self, ordine_data, parent=None):
        super().__init__(parent)
        self.ordine_data = ordine_data
        self.setWindowTitle(f"Order Details - {ordine_data.get('order_id', 'N/A')}")
        self.setMinimumSize(700, 600)
        
        self.init_ui()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Header
        header_label = QLabel(f"📋 Dettaglio Ordine: {self.ordine_data.get('order_id', 'N/A')}")
        header_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: bold;
                padding: 10px;
                background-color: #1a0a2a;
                border-radius: 5px;
            }
        """)
        layout.addWidget(header_label)
        
        # Scroll area per contenuto
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #4a4a5a;
                border-radius: 5px;
                background-color: #0a0a1a;
            }
        """)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(15)
        content_layout.setContentsMargins(15, 15, 15, 15)
        
        # Dati completi ordine
        dati_text = f"""
<b style='color: #FFFFFF; font-size: 14px;'>DATI ORDINE</b><br><br>

<b>Codice Ordine:</b> {self.ordine_data.get('order_id', 'N/A')}<br>
<b>ID Database:</b> {self.ordine_data.get('id', 'N/A')}<br>
<b>Cliente:</b> {self.ordine_data.get('client', 'N/A')}<br>
<b>Prodotto/Materiale:</b> {self.ordine_data.get('product', 'N/A')}<br>
<b>Macchina:</b> {self.ordine_data.get('machine', 'N/A')}<br>
<b>Stato:</b> {self.ordine_data.get('status', 'N/A')}<br>
"""
        
        if self.ordine_data.get('scheduled'):
            dati_text += f"<b>Programmato:</b> {self.ordine_data.get('scheduled')}<br>"
        
        dati_label = QLabel(dati_text)
        dati_label.setWordWrap(True)
        dati_label.setStyleSheet("""
            QLabel {
                color: #CCCCCC;
                font-size: 12px;
                padding: 15px;
                background-color: #1a1a2a;
                border: 1px solid #4a4a5a;
                border-radius: 5px;
            }
        """)
        content_layout.addWidget(dati_label)
        
        # Note amministrative (se disponibili)
        note_label = QLabel("<b style='color: #FFFFFF; font-size: 14px;'>NOTE AMMINISTRATIVE</b>")
        note_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        content_layout.addWidget(note_label)
        
        note_text = QTextEdit()
        note_text.setReadOnly(True)
        note_text.setPlaceholderText("Nessuna nota amministrativa disponibile per questo ordine.")
        note_text.setMaximumHeight(150)
        note_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2a;
                color: #CCCCCC;
                border: 1px solid #4a4a5a;
                border-radius: 5px;
                padding: 10px;
                font-size: 11px;
            }
        """)
        content_layout.addWidget(note_text)
        
        # Quantità e misure (se disponibili)
        misure_label = QLabel("<b style='color: #FFFFFF; font-size: 14px;'>QUANTITÀ E MISURE</b>")
        misure_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        content_layout.addWidget(misure_label)
        
        misure_text = QLabel(f"""
<b>Prodotto:</b> {self.ordine_data.get('product', 'N/A')}<br>
<b>Macchina assegnata:</b> {self.ordine_data.get('machine', 'N/A')}<br>
""")
        misure_text.setWordWrap(True)
        misure_text.setStyleSheet("""
            QLabel {
                color: #CCCCCC;
                font-size: 12px;
                padding: 15px;
                background-color: #1a1a2a;
                border: 1px solid #4a4a5a;
                border-radius: 5px;
            }
        """)
        content_layout.addWidget(misure_text)
        
        # Allegati (placeholder)
        allegati_label = QLabel("<b style='color: #FFFFFF; font-size: 14px;'>ALLEGATI</b>")
        allegati_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        content_layout.addWidget(allegati_label)
        
        allegati_text = QLabel("Nessun allegato disponibile per questo ordine.")
        allegati_text.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 11px;
                padding: 10px;
                background-color: #1a1a2a;
                border: 1px solid #4a4a5a;
                border-radius: 5px;
                font-style: italic;
            }
        """)
        content_layout.addWidget(allegati_text)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)
        
        # Pulsante chiusura
        close_btn = QPushButton("Chiudi")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a1a3a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 5px;
                padding: 8px 20px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3a2a4a;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

