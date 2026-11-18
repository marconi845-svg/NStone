"""
Nstone LLM - Finestra Centro Ordini Produzione
Interfaccia per ricerca e invio ordini alla produzione
Layout semplice e funzionale
"""
import sys
from pathlib import Path
from ui.common.section_window import SectionDialog, SectionMainWindow
from ui.common.window_helpers import show_auxiliary_window
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QTextEdit, QLineEdit, QSpinBox,
                             QMessageBox, QGroupBox, QScrollArea, QApplication, QSizePolicy,
                             QTableWidget, QTableWidgetItem, QHeaderView, QComboBox)
from PyQt5.QtGui import QColor
from ui.windows.orders.dettaglio_ordine_window import DettaglioOrdineWindow
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class CentroOrdiniProduzioneWindow(SectionMainWindow):
    """
    Finestra per gestione invio ordini alla produzione
    Layout semplice e funzionale
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.ordine_inviato = False
        self.ordine_trovato = None  # Dati ordine trovato
        self.tutti_ordini = []  # Lista ordini caricati
        
        # Flag interni per destinazione invio (non salvati nel DB)
        self.invio_multifilo = False
        self.invio_lucidatrice = False
        self.invio_cnc = False
        
        # Code macchina (sincronizzate da DB orders)
        self.ordini_multifilo = []
        self.ordini_lucidatrice = []
        self.ordini_cnc = []
        self._filtro_vista = "da_inviare"

        self.setWindowTitle("📋 Production Order Center")
        self.setMinimumSize(1000, 700)
        
        self.init_ui()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        # Scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background-color: #1a1a2a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a3a5a;
                min-height: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5a4a6a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Widget centrale
        central_widget = QWidget()
        central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        scroll_area.setWidget(central_widget)
        
        # Layout principale
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Layout orizzontale per i 3 blocchi
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        
        # ============================================================
        # BOX SINISTRO — "Ordini da Inviare" (Lista Ordini)
        # ============================================================
        ordine_box = QGroupBox("Production orders")
        ordine_box.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #FFFFFF;
                border: 2px solid #4a4a5a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        ordine_layout = QVBoxLayout(ordine_box)
        ordine_layout.setSpacing(10)
        
        vista_layout = QHBoxLayout()
        vista_label = QLabel("Vista:")
        vista_label.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        vista_layout.addWidget(vista_label)
        self.vista_combo = QComboBox()
        self.vista_combo.addItems([
            "Da inviare (CONFIRMED)",
            "Già inviati (INVIATO+)",
            "Tutti (confermati e inviati)",
        ])
        self.vista_combo.setStyleSheet("""
            QComboBox {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
        """)
        self.vista_combo.currentIndexChanged.connect(self._on_vista_changed)
        vista_layout.addWidget(self.vista_combo, 1)
        ordine_layout.addLayout(vista_layout)

        ricerca_layout = QHBoxLayout()
        codice_label = QLabel("Cerca:")
        codice_label.setStyleSheet("color: #CCCCCC; font-size: 12px; min-width: 50px;")
        ricerca_layout.addWidget(codice_label)
        self.codice_input = QLineEdit()
        self.codice_input.setPlaceholderText("Cerca per codice, cliente, materiale...")
        self.codice_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
            }
        """)
        self.codice_input.textChanged.connect(self.filtra_ordini)
        ricerca_layout.addWidget(self.codice_input, 1)
        ordine_layout.addLayout(ricerca_layout)
        
        # Tabella ordini
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.ordini_table = QTableWidget()
        self.ordini_table.setColumnCount(5)
        self.ordini_table.setHorizontalHeaderLabels(["Codice", "Cliente", "Materiale", "Macchina", "Stato"])
        self.ordini_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ordini_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ordini_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ordini_table.setAlternatingRowColors(True)
        self.ordini_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #4a4a5a;
                border-radius: 5px;
                color: #FFFFFF;
                font-size: 11px;
                gridline-color: #3a3a4a;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #4a4a6a;
            }
            QTableWidget::item:alternate {
                background-color: #0f0f1f;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 5px;
                border: none;
                border-bottom: 2px solid #5a5a6a;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        self.ordini_table.itemClicked.connect(self.on_ordine_selected)
        self.ordini_table.itemDoubleClicked.connect(self.on_ordine_double_clicked)
        ordine_layout.addWidget(self.ordini_table, 1)
        
        # Pulsanti azione
        azioni_layout = QHBoxLayout()
        azioni_layout.setSpacing(10)
        
        self.esamina_btn = QPushButton("📄 Esamina Ordine")
        self.esamina_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a5a;
                color: #FFFFFF;
                border: 1px solid #3a3a6a;
                border-radius: 5px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3a3a6a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
            }
        """)
        self.esamina_btn.setEnabled(False)
        self.esamina_btn.clicked.connect(self.on_esamina_clicked)
        azioni_layout.addWidget(self.esamina_btn)
        
        self.refresh_btn = QPushButton("🔄 Aggiorna")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a1a3a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 5px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3a2a4a;
            }
        """)
        self.refresh_btn.clicked.connect(self.carica_ordini)
        azioni_layout.addWidget(self.refresh_btn)
        
        ordine_layout.addLayout(azioni_layout)
        
        content_layout.addWidget(ordine_box, 1)
        
        # ============================================================
        # BOX CENTRALE — TRE PULSANTI INVIO
        # ============================================================
        invio_container = QWidget()
        invio_layout = QVBoxLayout(invio_container)
        invio_layout.setAlignment(Qt.AlignCenter)
        invio_layout.setSpacing(10)
        
        # Pulsante "Invia a Multifilo"
        self.invia_multifilo_btn = QPushButton("Invia a\nMultifilo")
        self.invia_multifilo_btn.setMinimumSize(120, 80)
        self.invia_multifilo_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a5a2a;
                color: #FFFFFF;
                border: 2px solid #3a6a3a;
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a6a3a;
                border: 2px solid #4a7a4a;
            }
            QPushButton:pressed {
                background-color: #1a4a1a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border: 2px solid #3a3a3a;
            }
        """)
        self.invia_multifilo_btn.setEnabled(False)
        self.invia_multifilo_btn.clicked.connect(self.on_invia_multifilo)
        invio_layout.addWidget(self.invia_multifilo_btn)
        
        # Pulsante "Invia a Lucidatrice"
        self.invia_lucidatrice_btn = QPushButton("Invia a\nLucidatrice")
        self.invia_lucidatrice_btn.setMinimumSize(120, 80)
        self.invia_lucidatrice_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a5a2a;
                color: #FFFFFF;
                border: 2px solid #3a6a3a;
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a6a3a;
                border: 2px solid #4a7a4a;
            }
            QPushButton:pressed {
                background-color: #1a4a1a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border: 2px solid #3a3a3a;
            }
        """)
        self.invia_lucidatrice_btn.setEnabled(False)
        self.invia_lucidatrice_btn.clicked.connect(self.on_invia_lucidatrice)
        invio_layout.addWidget(self.invia_lucidatrice_btn)
        
        # Pulsante "Invia a CNC"
        self.invia_cnc_btn = QPushButton("Invia a\nCNC")
        self.invia_cnc_btn.setMinimumSize(120, 80)
        self.invia_cnc_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a5a2a;
                color: #FFFFFF;
                border: 2px solid #3a6a3a;
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a6a3a;
                border: 2px solid #4a7a4a;
            }
            QPushButton:pressed {
                background-color: #1a4a1a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
                border: 2px solid #3a3a3a;
            }
        """)
        self.invia_cnc_btn.setEnabled(False)
        self.invia_cnc_btn.clicked.connect(self.on_invia_cnc)
        invio_layout.addWidget(self.invia_cnc_btn)
        
        content_layout.addWidget(invio_container, 0)
        
        # ============================================================
        # BOX DESTRO — "Ordini Inviati alle Macchine"
        # ============================================================
        conferma_box = QGroupBox("Orders sent to machines")
        conferma_box.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #FFFFFF;
                border: 2px solid #4a4a5a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        conferma_layout = QVBoxLayout(conferma_box)
        
        # Scroll area per contenere le tre sezioni
        scroll_area_ordini = QScrollArea()
        scroll_area_ordini.setWidgetResizable(True)
        scroll_area_ordini.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(12)
        scroll_layout.setContentsMargins(5, 5, 5, 5)
        
        # Sezione Multifilo (25-30% altezza)
        multifilo_section, self.multifilo_list_label = self._create_machine_section("Multifilo", "#2a5a2a")
        scroll_layout.addWidget(multifilo_section, 3)  # Proporzione 3
        
        # Sezione Lucidatrice (25-30% altezza)
        lucidatrice_section, self.lucidatrice_list_label = self._create_machine_section("Lucidatrice", "#2a5a2a")
        scroll_layout.addWidget(lucidatrice_section, 3)  # Proporzione 3
        
        # Sezione CNC (25-30% altezza)
        cnc_section, self.cnc_list_label = self._create_machine_section("CNC", "#2a5a2a")
        scroll_layout.addWidget(cnc_section, 3)  # Proporzione 3
        
        # Spazio vuoto in fondo (10-20% altezza)
        scroll_layout.addStretch(1)  # Proporzione 1 per spazio respiro
        
        scroll_area_ordini.setWidget(scroll_widget)
        conferma_layout.addWidget(scroll_area_ordini)
        
        content_layout.addWidget(conferma_box, 1)
        
        # Inizializza visualizzazione ordini inviati
        self.aggiorna_visualizzazione_ordini_inviati()
        
        main_layout.addLayout(content_layout, 1)
        
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
        
        self.carica_code_macchine()
        self.carica_ordini()
    
    def create_header(self):
        """Crea l'header unificato della finestra"""
        header_widget = QWidget()
        header_widget.setFixedHeight(50)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(15)
        
        # Titolo
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_label = QLabel("📋 Production Order Center")
        title_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 20px;
                font-weight: bold;
            }
        """)
        title_col.addWidget(title_label)
        subtitle = QLabel(
            "Tabella: filtro vista · Destra: code per macchina (persistite su DB)"
        )
        subtitle.setStyleSheet("color: #888888; font-size: 11px;")
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)
        
        header_layout.addStretch()
        
        # Bottone Dashboard
        dashboard_btn = QPushButton("🏠 Dashboard")
        dashboard_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a1a3a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 5px;
                padding: 5px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3a2a4a;
            }
        """)
        dashboard_btn.clicked.connect(self.go_back_to_dashboard)
        header_layout.addWidget(dashboard_btn)
        
        header_widget.setStyleSheet("background-color: #1a0a2a; border-bottom: 1px solid #3a2a4a;")
        return header_widget
    
    def create_status_bar(self):
        """Crea la barra di stato"""
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(5, 5, 5, 5)
        status_layout.setSpacing(15)
        
        self.ordine_status_label = QLabel("Ordine Produzione: Nessun ordine")
        self.ordine_status_label.setStyleSheet("color: #888888; font-size: 11px;")
        status_layout.addWidget(self.ordine_status_label)
        
        status_layout.addStretch()
        
        return status_widget
    
    def carica_code_macchine(self):
        """Ricarica le code inviate alle tre macchine dal database."""
        try:
            from modules.orders_database import get_orders_for_machine

            self.ordini_multifilo = get_orders_for_machine("Multifilo")
            self.ordini_lucidatrice = get_orders_for_machine("Lucidatrice")
            self.ordini_cnc = get_orders_for_machine("CNC")
            self.aggiorna_visualizzazione_ordini_inviati()
        except Exception as e:
            print(f"Errore caricamento code macchine: {e}")

    def _on_vista_changed(self, _index: int = 0):
        labels = ("da_inviare", "inviati", "tutti")
        idx = self.vista_combo.currentIndex() if hasattr(self, "vista_combo") else 0
        self._filtro_vista = labels[idx] if 0 <= idx < len(labels) else "da_inviare"
        self.carica_ordini()

    def carica_ordini(self):
        """Carica ordini in base alla vista selezionata."""
        try:
            from modules.orders_database import (
                get_database_path,
                get_orders_pending_production,
                get_orders_sent_production,
                get_orders_production_overview,
            )

            if not get_database_path().exists():
                self.ordini_table.setRowCount(1)
                self.ordini_table.setItem(0, 0, QTableWidgetItem("Database non trovato"))
                return

            vista = getattr(self, "_filtro_vista", "da_inviare")
            if vista == "inviati":
                self.tutti_ordini = get_orders_sent_production(limit=100)
                hint = f"Inviati / in produzione: {len(self.tutti_ordini)}"
            elif vista == "tutti":
                self.tutti_ordini = get_orders_production_overview(limit=100)
                hint = f"Totale pipeline produzione: {len(self.tutti_ordini)}"
            else:
                self.tutti_ordini = get_orders_pending_production(limit=100)
                hint = f"Da inviare (CONFIRMED): {len(self.tutti_ordini)}"

            filtro_testo = self.codice_input.text().strip().lower() if hasattr(self, "codice_input") else ""
            if filtro_testo:
                self.filtra_ordini()
            else:
                self.mostra_ordini_tabella(self.tutti_ordini)
            self.carica_code_macchine()

            self.ordine_trovato = None
            self.esamina_btn.setEnabled(False)
            self.disabilita_tutti_pulsanti_invia()
            self.ordine_status_label.setText(hint)
            self.ordine_status_label.setStyleSheet("color: #CCCCCC; font-size: 11px;")

        except Exception as e:
            QMessageBox.critical(
                self, "Errore Database", f"Errore durante il caricamento: {e}"
            )
            self.ordini_table.setRowCount(1)
            self.ordini_table.setItem(0, 0, QTableWidgetItem(f"Errore: {e}"))
    
    def mostra_ordini_tabella(self, ordini):
        """Mostra ordini nella tabella.

        Vista "Da inviare": la macchina non è ancora decisa (si sceglie qui),
        quindi la colonna mostra la quantità. Nelle altre viste mostra la macchina.
        """
        vista = getattr(self, "_filtro_vista", "da_inviare")
        show_machine = vista != "da_inviare"
        self.ordini_table.setHorizontalHeaderLabels(
            ["Codice", "Cliente", "Materiale",
             "Macchina" if show_machine else "Quantità (mq)", "Stato"]
        )
        self.ordini_table.setRowCount(len(ordini))
        
        for row_idx, ordine in enumerate(ordini):
            # Codice
            codice_item = QTableWidgetItem(ordine['order_id'])
            self.ordini_table.setItem(row_idx, 0, codice_item)
            
            # Cliente
            cliente_item = QTableWidgetItem(ordine['client'])
            self.ordini_table.setItem(row_idx, 1, cliente_item)
            
            materiale = ordine.get("materiale") or ordine.get("product") or ""
            materiale_item = QTableWidgetItem(materiale)
            self.ordini_table.setItem(row_idx, 2, materiale_item)

            qty = ordine.get("quantita_mq")
            if qty is not None:
                materiale_item.setToolTip(f"Quantità: {qty:g} mq")

            if show_machine:
                machine = ordine.get("machine") or ""
                from modules.orders_database import MACHINE_DB_TO_UI
                macchina_label = MACHINE_DB_TO_UI.get(
                    (machine or "").strip().lower(), machine or "—"
                )
                col3_item = QTableWidgetItem(macchina_label)
            else:
                col3_item = QTableWidgetItem(f"{qty:g}" if qty is not None else "—")
            self.ordini_table.setItem(row_idx, 3, col3_item)
            
            # Stato con colore
            stato = ordine['status'].upper()
            stato_item = QTableWidgetItem(stato)
            if stato == "INVIATO" or stato == "IN PRODUZIONE":
                stato_item.setForeground(QColor(0, 255, 0))  # Verde
            elif stato == "COMPLETATO":
                stato_item.setForeground(QColor(0, 170, 255))  # Blu
            else:
                stato_item.setForeground(QColor(255, 255, 0))  # Giallo
            self.ordini_table.setItem(row_idx, 4, stato_item)
    
    def filtra_ordini(self):
        """Filtra ordini in base al testo di ricerca"""
        if not hasattr(self, 'tutti_ordini'):
            return
        
        filtro = self.codice_input.text().strip().lower()
        
        if not filtro:
            # Mostra tutti gli ordini
            self.mostra_ordini_tabella(self.tutti_ordini)
            return
        
        # Filtra ordini
        ordini_filtrati = []
        for ordine in self.tutti_ordini:
            materiale = (ordine.get("materiale") or ordine.get("product") or "").lower()
            if (filtro in ordine["order_id"].lower()
                or filtro in ordine["client"].lower()
                or filtro in materiale
                or filtro in (ordine.get("machine") or "").lower()
                or filtro in ordine["status"].lower()):
                ordini_filtrati.append(ordine)
        
        self.mostra_ordini_tabella(ordini_filtrati)
    
    def on_ordine_selected(self, item):
        """Gestisce selezione ordine nella tabella"""
        if not hasattr(self, 'tutti_ordini'):
            return
        
        row = item.row()
        if row >= self.ordini_table.rowCount():
            return
        
        # Trova l'ordine selezionato dalla tabella corrente (potrebbe essere filtrata)
        codice = self.ordini_table.item(row, 0)
        if not codice:
            return
        
        codice_text = codice.text()
        ordine = self.cerca_ordine_db(codice_text)
        if ordine:
            self.ordine_trovato = ordine
            self.esamina_btn.setEnabled(True)
            # Aggiorna box destro con dettagli
            self.aggiorna_box_destro(ordine)
    
    def on_ordine_double_clicked(self, item):
        """Apre dettaglio ordine al doppio click"""
        self.on_ordine_selected(item)
        if self.ordine_trovato:
            self.on_esamina_clicked()
    
    def aggiorna_box_destro(self, ordine):
        """Aggiorna il box destro con i dettagli dell'ordine selezionato"""
        stato = ordine['status'].upper()
        
        # Colore stato
        if stato == "INVIATO" or stato == "IN PRODUZIONE":
            stato_html = f"<span style='color: #00FF00;'>IN PRODUZIONE</span>"
        elif stato == "COMPLETATO":
            stato_html = f"<span style='color: #00AAFF;'>COMPLETATO</span>"
        else:
            stato_html = f"<span style='color: #FFFF00;'>APERTO</span>"
        
        # Aggiorna pulsanti Invia (il box destro ora mostra solo ordini inviati)
        self.aggiorna_pulsanti_invia(ordine)
    
    def aggiorna_pulsanti_invia(self, ordine):
        """Abilita invio solo per ordini confermati non ancora in coda."""
        from modules.orders_database import PRODUCTION_READY_STATUSES

        stato = (ordine.get("status") or "").upper()
        if stato in PRODUCTION_READY_STATUSES and getattr(self, "_filtro_vista", "") == "da_inviare":
            self.invia_multifilo_btn.setEnabled(True)
            self.invia_lucidatrice_btn.setEnabled(True)
            self.invia_cnc_btn.setEnabled(True)
        else:
            self.disabilita_tutti_pulsanti_invia()
    
    def disabilita_tutti_pulsanti_invia(self):
        """Disabilita tutti i pulsanti di invio"""
        self.invia_multifilo_btn.setEnabled(False)
        self.invia_lucidatrice_btn.setEnabled(False)
        self.invia_cnc_btn.setEnabled(False)
    
    def cerca_ordine_db(self, codice_ordine):
        """Cerca ordine nel database orders."""
        try:
            from modules.orders_database import get_order_for_production

            return get_order_for_production(codice_ordine)
        except Exception as e:
            QMessageBox.critical(self, "Errore Database", f"Errore ricerca: {e}")
            return None
    
    
    def on_esamina_clicked(self):
        """Apre finestra dettaglio ordine"""
        if not self.ordine_trovato:
            return
        
        dettaglio_window = DettaglioOrdineWindow(self.ordine_trovato, self)
        show_auxiliary_window(dettaglio_window)
    
    def on_invia_multifilo(self):
        """Gestisce invio ordine a Multifilo"""
        self._invia_ordine_destinazione("Multifilo")
    
    def on_invia_lucidatrice(self):
        """Gestisce invio ordine a Lucidatrice"""
        self._invia_ordine_destinazione("Lucidatrice")
    
    def on_invia_cnc(self):
        """Gestisce invio ordine a CNC"""
        self._invia_ordine_destinazione("CNC")
    
    def _invia_ordine_destinazione(self, destinazione):
        """Persiste invio su DB e aggiorna code macchine."""
        if not self.ordine_trovato:
            QMessageBox.warning(self, "Error", "Selezionare prima un ordine dalla tabella")
            return

        codice = self.ordine_trovato["order_id"]
        try:
            from modules.orders_database import assign_order_to_machine

            ok, msg = assign_order_to_machine(codice, destinazione)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        if not ok:
            QMessageBox.warning(self, "Invio non riuscito", msg)
            return

        self.ordine_status_label.setText(
            f"Ordine Produzione: Inviato a {destinazione} ({codice})"
        )
        self.ordine_status_label.setStyleSheet("color: #00FF00; font-size: 11px;")
        self.disabilita_tutti_pulsanti_invia()
        self.ordine_trovato = None
        self.esamina_btn.setEnabled(False)

        if hasattr(self, "vista_combo"):
            self.vista_combo.setCurrentIndex(1)
        self.carica_ordini()
        QMessageBox.information(self, "Ordine Inviato", msg)
    
    def _create_machine_section(self, nome_macchina, colore_bordo):
        """Crea una sezione per visualizzare ordini inviati a una macchina"""
        section_box = QGroupBox(f"Orders sent to {nome_macchina}")
        section_box.setStyleSheet(f"""
            QGroupBox {{
                font-size: 13px;
                font-weight: bold;
                color: #FFFFFF;
                border: 2px solid {colore_bordo};
                border-radius: 6px;
                margin-top: 5px;
                padding-top: 8px;
                background-color: #0f0f1a;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                border-bottom: 1px solid {colore_bordo};
                padding-bottom: 3px;
            }}
        """)
        section_layout = QVBoxLayout(section_box)
        section_layout.setContentsMargins(8, 8, 8, 8)
        section_layout.setSpacing(5)
        
        # Scroll area interna per ogni sezione
        inner_scroll = QScrollArea()
        inner_scroll.setWidgetResizable(True)
        inner_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #1a1a2a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #3a3a4a;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4a4a5a;
            }
        """)
        
        list_label = QLabel("Nessun ordine inviato")
        list_label.setWordWrap(True)
        list_label.setAlignment(Qt.AlignTop)
        list_label.setStyleSheet("""
            QLabel {
                color: #CCCCCC;
                font-size: 11px;
                padding: 8px;
                background-color: transparent;
                border: none;
                min-height: 60px;
            }
        """)
        
        inner_scroll.setWidget(list_label)
        section_layout.addWidget(inner_scroll)
        
        # Imposta altezza massima proporzionata (circa 25-30% del box)
        section_box.setMaximumHeight(250)
        section_box.setMinimumHeight(80)
        
        return section_box, list_label
    
    def aggiorna_visualizzazione_ordini_inviati(self):
        """Aggiorna la visualizzazione di tutti gli ordini inviati"""
        # Aggiorna sezione Multifilo
        if hasattr(self, 'multifilo_list_label'):
            self._aggiorna_sezione_ordini(self.multifilo_list_label, self.ordini_multifilo, "Multifilo")
        
        # Aggiorna sezione Lucidatrice
        if hasattr(self, 'lucidatrice_list_label'):
            self._aggiorna_sezione_ordini(self.lucidatrice_list_label, self.ordini_lucidatrice, "Lucidatrice")
        
        # Aggiorna sezione CNC
        if hasattr(self, 'cnc_list_label'):
            self._aggiorna_sezione_ordini(self.cnc_list_label, self.ordini_cnc, "CNC")
    
    def _aggiorna_sezione_ordini(self, label, lista_ordini, nome_macchina):
        """Aggiorna una singola sezione con gli ordini inviati"""
        if not lista_ordini:
            label.setText(f"<div style='padding: 15px; text-align: center;'><i style='color: #666666; font-size: 11px;'>Nessun ordine inviato al {nome_macchina}</i></div>")
            return
        
        html_content = "<div style='padding: 2px;'>"
        for idx, ordine in enumerate(lista_ordini):
            # Righe alternate per leggibilità
            bg_color = "#1a1a2a" if idx % 2 == 0 else "#151520"
            
            html_content += f"""
            <div style='margin-bottom: 6px; padding: 8px; background-color: {bg_color}; border-left: 3px solid #00FF00; border-radius: 3px;'>
                <b style='color: #00FF00; font-size: 12px;'>• {ordine['codice']}</b><br>
                <span style='color: #CCCCCC; font-size: 10px; line-height: 1.4;'>
                    <span style='color: #AAAAAA;'>Cliente:</span> {ordine['cliente']}<br>
                    <span style='color: #AAAAAA;'>Materiale:</span> {ordine['materiale']}<br>
                    <span style='color: #AAAAAA;'>Quantità:</span> {ordine['quantita']}<br>
                    <i style='color: #888888; font-size: 9px;'>Inviato: {ordine['timestamp']}</i>
                </span>
            </div>
            """
        
        html_content += "</div>"
        label.setText(html_content)
    
    def on_section_shown(self) -> None:
        self.carica_ordini()

    def closeEvent(self, event):
        """Gestisce chiusura finestra"""
        event.accept()

