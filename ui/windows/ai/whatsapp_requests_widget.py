"""
Nstone LLM - Widget per gestione richieste WhatsApp
Gestisce richieste ricevute via WhatsApp e preparazione offerte
"""
import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QTableWidget, QTableWidgetItem,
                             QTextEdit, QLineEdit, QHeaderView, QProgressBar,
                             QScrollArea, QMessageBox, QSplitter)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor


class WhatsAppRequest:
    """Modello dati per una richiesta WhatsApp"""
    
    def __init__(self, data: Dict[str, Any]):
        self.timestamp = data.get("timestamp", datetime.now().isoformat())
        self.from_number = data.get("from", "")
        self.message = data.get("message", "")
        self.status = data.get("status", "Nuovo")  # Nuovo, In lavorazione, Offerta inviata
        self.notes = data.get("notes", "")
        self.request_id = data.get("id", f"req_{datetime.now().timestamp()}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte la richiesta in dizionario"""
        return {
            "id": self.request_id,
            "timestamp": self.timestamp,
            "from": self.from_number,
            "message": self.message,
            "status": self.status,
            "notes": self.notes
        }


class WhatsAppRequestsWidget(QWidget):
    """
    Widget per gestire richieste WhatsApp ricevute e preparazione offerte.
    
    PUNTI DI INTEGRAZIONE:
    1. Backend che riceve dati dalla Cloud Function:
       - Metodo: add_request_from_backend(data: Dict)
       - Chiamato quando il backend Windows riceve un messaggio dalla Cloud Function
       
    2. Modulo generazione offerte (futuro):
       - Metodo: prepara_offerta_per_email(richiesta: WhatsAppRequest)
       - Questo metodo preparerà i dati per l'invio email
       
    3. Modulo invio email Outlook (futuro):
       - Metodo: invia_offerta_via_outlook(offerta_data: Dict)
       - Chiamato dopo la preparazione dell'offerta
    """
    
    # Segnale emesso quando una richiesta viene selezionata
    request_selected = pyqtSignal(WhatsAppRequest)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Percorso per salvare le richieste localmente
        self.data_dir = Path(__file__).parent / "csv_data"
        self.data_dir.mkdir(exist_ok=True)
        self.requests_file = self.data_dir / "whatsapp_requests.json"
        
        # Lista richieste
        self.requests: List[WhatsAppRequest] = []
        
        # Lista offerte in bozza
        self.draft_offers: List[Dict[str, Any]] = []
        
        # Richiesta selezionata
        self.selected_request: Optional[WhatsAppRequest] = None
        
        self.init_ui()
        self.load_requests()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Titolo e descrizione
        title_label = QLabel("Centro Richieste")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        main_layout.addWidget(title_label)
        
        desc_label = QLabel("Gestisci il flusso di preventivazione neurale")
        desc_label.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        main_layout.addWidget(desc_label)
        
        # Splitter per due pannelli
        splitter = QSplitter(Qt.Horizontal)
        
        # Pannello sinistro - Richieste Ricevute
        left_panel = self.create_received_requests_panel()
        splitter.addWidget(left_panel)
        
        # Pannello destro - Richieste da Inviare
        right_panel = self.create_pending_offers_panel()
        splitter.addWidget(right_panel)
        
        # Imposta proporzioni (50-50)
        splitter.setSizes([500, 500])
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2a2a3a;
                width: 2px;
            }
        """)
        
        main_layout.addWidget(splitter, 1)
        
        self.apply_stylesheet()
    
    def create_received_requests_panel(self):
        """Crea il pannello delle richieste ricevute"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border-radius: 8px;
                border: 1px solid #2a2a3a;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header con badge
        header_layout = QHBoxLayout()
        
        header_label = QLabel("📧 Richieste Ricevute")
        header_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        # Badge nuove richieste
        self.new_requests_badge = QLabel("0 NUOVE")
        self.new_requests_badge.setStyleSheet("""
            QLabel {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self.new_requests_badge)
        
        layout.addLayout(header_layout)
        
        # Tabella richieste
        self.requests_table = QTableWidget()
        self.requests_table.setColumnCount(4)
        self.requests_table.setHorizontalHeaderLabels(["Data/Ora", "Numero", "Messaggio", "Stato"])
        self.requests_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
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
                padding: 8px;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        self.requests_table.horizontalHeader().setStretchLastSection(True)
        self.requests_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.requests_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.requests_table.itemSelectionChanged.connect(self.on_request_selected)
        
        layout.addWidget(self.requests_table, 1)
        
        # Pulsante WhatsApp Sync
        whatsapp_button = QPushButton("💬 WHATSAPP CHANNEL SYNC")
        whatsapp_button.setMinimumHeight(40)
        whatsapp_button.setStyleSheet("""
            QPushButton {
                background-color: #25D366;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #20BA5A;
            }
        """)
        whatsapp_button.clicked.connect(self.sync_whatsapp_channel)
        layout.addWidget(whatsapp_button)
        
        return panel
    
    def create_pending_offers_panel(self):
        """Crea il pannello delle offerte da inviare"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border-radius: 8px;
                border: 1px solid #2a2a3a;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header con badge
        header_layout = QHBoxLayout()
        
        header_label = QLabel("✈ Richieste da Inviare")
        header_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        # Badge bozze
        self.drafts_badge = QLabel("0 BOZZE")
        self.drafts_badge.setStyleSheet("""
            QLabel {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self.drafts_badge)
        
        layout.addLayout(header_layout)
        
        # Scroll area per lista offerte
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
        
        self.offers_container = QWidget()
        self.offers_layout = QVBoxLayout(self.offers_container)
        self.offers_layout.setContentsMargins(0, 0, 0, 0)
        self.offers_layout.setSpacing(10)
        self.offers_layout.addStretch()
        
        scroll_area.setWidget(self.offers_container)
        layout.addWidget(scroll_area, 1)
        
        # Aggiorna lista offerte
        self.update_offers_list()
        
        # Pulsante Outlook Integration
        outlook_button = QPushButton("📧 OUTLOOK INTEGRATION")
        outlook_button.setMinimumHeight(40)
        outlook_button.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #0063B1;
            }
        """)
        outlook_button.clicked.connect(self.open_outlook_integration)
        layout.addWidget(outlook_button)
        
        return panel
    
    def create_offer_card(self, offer_data: Dict[str, Any]) -> QFrame:
        """Crea una card per un'offerta in bozza"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)
        
        # Header con nome cliente e pulsante INVIA
        header_layout = QHBoxLayout()
        
        cliente_label = QLabel(offer_data.get("cliente", "N/A"))
        cliente_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        header_layout.addWidget(cliente_label)
        
        header_layout.addStretch()
        
        invia_button = QPushButton("INVIA")
        invia_button.setFixedSize(70, 30)
        invia_button.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9B6CF6;
            }
        """)
        invia_button.clicked.connect(lambda: self.send_offer(offer_data))
        header_layout.addWidget(invia_button)
        
        card_layout.addLayout(header_layout)
        
        # Totale stimato
        totale = offer_data.get("totale_stimato", 0.0)
        totale_label = QLabel(f"TOTALE STIMATO: {totale:,.2f} €")
        totale_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        card_layout.addWidget(totale_label)
        
        # Progress bar
        progress = offer_data.get("progress", 0)
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(100)
        progress_bar.setValue(progress)
        progress_bar.setFormat(f"{progress}%")
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a2a4a;
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
                background-color: #1a1a2a;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8B5CF6, stop:1 #6B4CD6);
                border-radius: 3px;
            }
        """)
        card_layout.addWidget(progress_bar)
        
        # Last edit
        last_edit = offer_data.get("last_edit", "N/A")
        last_edit_label = QLabel(f"LAST EDIT: {last_edit}")
        last_edit_label.setStyleSheet("color: #666666; font-size: 10px;")
        card_layout.addWidget(last_edit_label)
        
        return card
    
    def update_offers_list(self):
        """Aggiorna la lista delle offerte in bozza"""
        # Rimuovi tutte le card esistenti
        while self.offers_layout.count() > 1:  # Mantieni lo stretch
            item = self.offers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Aggiungi card per ogni offerta
        for offer in self.draft_offers:
            card = self.create_offer_card(offer)
            self.offers_layout.insertWidget(self.offers_layout.count() - 1, card)
        
        # Aggiorna badge
        self.drafts_badge.setText(f"{len(self.draft_offers)} BOZZE")
    
    def send_offer(self, offer_data: Dict[str, Any]):
        """Invia un'offerta"""
        # Prepara l'offerta
        offerta_preparata = self.prepara_offerta_per_email_from_dict(offer_data)
        
        # Invia via Outlook
        if self.invia_offerta_via_outlook(offerta_preparata):
            QMessageBox.information(self, "Offerta Inviata", 
                                  f"Offerta inviata con successo a {offer_data.get('cliente')}")
            # Rimuovi dalla lista bozze
            if offer_data in self.draft_offers:
                self.draft_offers.remove(offer_data)
                self.update_offers_list()
        else:
            QMessageBox.warning(self, "Error", 
                              "Errore durante l'invio dell'offerta")
    
    def prepara_offerta_per_email_from_dict(self, offer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepara offerta da dizionario (per offerte in bozza)"""
        return {
            "richiesta_id": offer_data.get("richiesta_id", ""),
            "cliente": offer_data.get("cliente", ""),
            "totale_stimato": offer_data.get("totale_stimato", 0.0),
            "dettagli_offerta": offer_data.get("dettagli_offerta", []),
            "timestamp": datetime.now().isoformat()
        }
    
    def add_request_from_backend(self, data: Dict[str, Any]):
        """
        Aggiunge una nuova richiesta ricevuta dal backend.
        
        PUNTO DI INTEGRAZIONE BACKEND:
        Questo metodo deve essere chiamato quando il backend Windows riceve
        un messaggio inoltrato dalla Cloud Function.
        
        Esempio di chiamata:
            widget.add_request_from_backend({
                "from": "393471234567",
                "message": "Ciao, vorrei un preventivo",
                "timestamp": "2025-01-15T10:30:00"
            })
        """
        # Crea nuova richiesta
        request = WhatsAppRequest({
            "timestamp": data.get("timestamp", datetime.now().isoformat()),
            "from": data.get("from", ""),
            "message": data.get("message", ""),
            "status": "Nuovo"
        })
        
        # Aggiungi alla lista
        self.requests.insert(0, request)  # Aggiungi in cima
        
        # Aggiorna UI
        self.update_requests_table()
        self.save_requests()
        
        # Mostra notifica (opzionale)
        self.show_notification(f"Nuova richiesta da {request.from_number}")
    
    def update_requests_table(self):
        """Aggiorna la tabella delle richieste"""
        self.requests_table.setRowCount(len(self.requests))
        
        for row, request in enumerate(self.requests):
            # Data/Ora
            try:
                dt = datetime.fromisoformat(request.timestamp)
                date_str = dt.strftime("%d/%m/%Y %H:%M")
            except:
                date_str = request.timestamp
            
            self.requests_table.setItem(row, 0, QTableWidgetItem(date_str))
            
            # Numero
            self.requests_table.setItem(row, 1, QTableWidgetItem(request.from_number))
            
            # Messaggio (troncato)
            message_preview = request.message[:50] + "..." if len(request.message) > 50 else request.message
            self.requests_table.setItem(row, 2, QTableWidgetItem(message_preview))
            
            # Stato
            status_item = QTableWidgetItem(request.status)
            if request.status == "Nuovo":
                status_item.setForeground(QColor("#FF6B6B"))
            elif request.status == "In lavorazione":
                status_item.setForeground(QColor("#FFD93D"))
            else:
                status_item.setForeground(QColor("#6BCF7F"))
            self.requests_table.setItem(row, 3, status_item)
        
        # Aggiorna badge
        new_count = sum(1 for r in self.requests if r.status == "Nuovo")
        self.new_requests_badge.setText(f"{new_count} NUOVE")
    
    def on_request_selected(self):
        """Gestisce la selezione di una richiesta"""
        selected_rows = self.requests_table.selectedItems()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        if row < len(self.requests):
            self.selected_request = self.requests[row]
            self.request_selected.emit(self.selected_request)
            
            # Mostra opzione per creare offerta
            self.show_offer_creation_options()
    
    def show_offer_creation_options(self):
        """Mostra opzioni per creare offerta dalla richiesta selezionata"""
        if not self.selected_request:
            return
        
        # TODO: Mostrare dialog o pannello per creare offerta
        # Per ora, crea una bozza automatica
        self.create_draft_offer_from_request(self.selected_request)
    
    def create_draft_offer_from_request(self, request: WhatsAppRequest):
        """Crea una bozza di offerta da una richiesta"""
        draft = {
            "richiesta_id": request.request_id,
            "cliente": request.from_number,
            "messaggio_originale": request.message,
            "totale_stimato": 0.0,  # TODO: Calcolare da logica di generazione offerte
            "progress": 0,  # TODO: Calcolare progresso
            "last_edit": "Adesso",
            "dettagli_offerta": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Aggiungi alla lista bozze se non esiste già
        if not any(d.get("richiesta_id") == request.request_id for d in self.draft_offers):
            self.draft_offers.append(draft)
            self.update_offers_list()
    
    def prepara_offerta_per_email(self, richiesta: WhatsAppRequest) -> Dict[str, Any]:
        """
        Prepara i dati per l'invio email di un'offerta.
        
        PUNTO DI INTEGRAZIONE MODULO GENERAZIONE OFFERTE:
        Questo metodo prepara i dati necessari per generare e inviare un'offerta.
        In futuro, qui verrà integrata la logica di generazione offerta.
        
        Returns:
            Dict con dati dell'offerta pronta per l'invio email
        """
        # TODO: Integrare logica di generazione offerta
        # Per ora restituisce dati base
        
        offerta_data = {
            "richiesta_id": richiesta.request_id,
            "cliente": richiesta.from_number,
            "messaggio_originale": richiesta.message,
            "note_interne": richiesta.notes,
            "timestamp": datetime.now().isoformat(),
            # Campi da popolare con logica di generazione offerta:
            "totale_stimato": 0.0,
            "dettagli_offerta": [],
            "allegati": []
        }
        
        # TODO: Chiamare qui il modulo di generazione offerte
        # offerta_data = modulo_generazione_offerte.genera(richiesta)
        
        return offerta_data
    
    def invia_offerta_via_outlook(self, offerta_data: Dict[str, Any]) -> bool:
        """
        Invia un'offerta via email usando Outlook.
        
        PUNTO DI INTEGRAZIONE MODULO OUTLOOK:
        Questo metodo deve essere collegato al modulo di invio email Outlook.
        Attualmente è un placeholder che logga l'azione.
        
        Args:
            offerta_data: Dati dell'offerta preparati da prepara_offerta_per_email()
        
        Returns:
            True se l'invio è riuscito, False altrimenti
        """
        # TODO: Integrare chiamata reale a Outlook API
        # Esempio futuro:
        # return outlook_module.invia_email(
        #     destinatario=offerta_data["cliente"],
        #     oggetto="Preventivo NStone",
        #     corpo=offerta_data["corpo_email"],
        #     allegati=offerta_data["allegati"]
        # )
        
        print(f"[OUTLOOK] Invio offerta a {offerta_data.get('cliente')}")
        print(f"[OUTLOOK] Totale: {offerta_data.get('totale_stimato')} €")
        
        # Simulazione: per ora restituisce True
        return True
    
    def sync_whatsapp_channel(self):
        """Sincronizza il canale WhatsApp"""
        # TODO: Implementare sincronizzazione con WhatsApp
        QMessageBox.information(self, "WhatsApp Sync", 
                               "Sincronizzazione canale WhatsApp in corso...")
    
    def open_outlook_integration(self):
        """Apre la configurazione integrazione Outlook"""
        # TODO: Implementare configurazione Outlook
        QMessageBox.information(self, "Outlook Integration", 
                               "Configurazione integrazione Outlook...")
    
    def show_notification(self, message: str):
        """Mostra una notifica (placeholder)"""
        # TODO: Implementare sistema di notifiche
        print(f"[NOTIFICA] {message}")
    
    def load_requests(self):
        """Carica le richieste salvate"""
        if not self.requests_file.exists():
            return
        
        try:
            with open(self.requests_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.requests = [WhatsAppRequest(item) for item in data]
            self.update_requests_table()
        except Exception as e:
            print(f"Errore caricamento richieste: {e}")
    
    def save_requests(self):
        """Salva le richieste su file"""
        try:
            data = [req.to_dict() for req in self.requests]
            with open(self.requests_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Errore salvataggio richieste: {e}")
    
    def apply_stylesheet(self):
        """Applica lo stylesheet"""
        self.setStyleSheet("""
            QWidget {
                background: transparent;
            }
        """)

