"""
Widget casellario per Pezzi Attualmente in Lavorazione
Usato nella sezione Gestione CNC Universale
"""
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class PezziLavorazioneWidget(QGroupBox):
    """Widget tabella per visualizzare i pezzi attualmente in lavorazione"""
    
    def __init__(self, parent=None):
        super().__init__("Pezzi Attualmente in Lavorazione", parent)
        self.init_ui()
    
    def init_ui(self):
        """Inizializza la tabella - Stessa dimensione degli altri box"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Crea tabella con 2 colonne (Parametro, Valore)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Parametro", "Valore"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        # Altezza fissa - sviluppata in verticale per mostrare tutte le righe
        self.table.setFixedHeight(300)
        # Abilita scroll orizzontale e verticale
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Stile tabella - Stessa dimensione degli altri box
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 2px solid #4a4a5a;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-weight: normal;
                gridline-color: #3a3a4a;
            }
            QTableWidget::item {
                padding: 8px 10px;
                border: none;
                min-height: 28px;
            }
            QTableWidget::item:alternate {
                background-color: #0f0f1f;
            }
            QTableWidget::item:selected {
                background-color: #4a4a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 8px 10px;
                border: none;
                border-bottom: 2px solid #5a5a6a;
                font-weight: bold;
                font-size: 12px;
                min-height: 30px;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: #1a1a2a;
                width: 12px;
                height: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background-color: #4a4a5a;
                min-height: 30px;
                min-width: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background-color: #5a5a6a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                height: 0px;
                width: 0px;
            }
        """)
        
        layout.addWidget(self.table)
        
        # Inizializza con valori di default
        self.update_pezzi(
            materiale="--",
            spessore=0.0,
            dimensioni_l=0.0,
            dimensioni_h=0.0,
            dimensioni_p=0.0,
            pezzi_totali=0,
            pezzi_completati=0,
            pezzi_in_lavorazione=0,
            avanzamento_pezzo=0.0,
            avanzamento_lotto=0.0
        )
    
    def update_pezzi(self, materiale=None, spessore=None,
                   dimensioni_l=None, dimensioni_h=None, dimensioni_p=None,
                   pezzi_totali=None, pezzi_completati=None,
                   pezzi_in_lavorazione=None, avanzamento_pezzo=None,
                   avanzamento_lotto=None):
        """Aggiorna i dati dei pezzi in lavorazione"""
        # Prepara i dati
        dimensioni_text = f"{dimensioni_l:.1f} x {dimensioni_h:.1f} x {dimensioni_p:.1f} mm" if (
            dimensioni_l is not None and dimensioni_h is not None and dimensioni_p is not None
        ) else "--"
        
        pezzi_rimanenti = 0
        if pezzi_totali is not None and pezzi_completati is not None:
            pezzi_rimanenti = max(0, pezzi_totali - pezzi_completati)
        
        rows = [
            ("Materiale", materiale if materiale is not None else "--"),
            ("Spessore", f"{spessore:.1f} mm" if spessore is not None else "-- mm"),
            ("Dimensioni pezzo", dimensioni_text),
            ("Pezzi totali", f"{int(pezzi_totali)}" if pezzi_totali is not None else "0"),
            ("Pezzi completati", f"{int(pezzi_completati)}" if pezzi_completati is not None else "0"),
            ("Pezzi in lavorazione", f"{int(pezzi_in_lavorazione)}" if pezzi_in_lavorazione is not None else "0"),
            ("Pezzi rimanenti", f"{int(pezzi_rimanenti)}"),
            ("Avanzamento pezzo", f"{avanzamento_pezzo:.1f} %" if avanzamento_pezzo is not None else "0.0 %"),
            ("Avanzamento lotto", f"{avanzamento_lotto:.1f} %" if avanzamento_lotto is not None else "0.0 %")
        ]
        
        # Aggiorna tabella
        self.table.setRowCount(len(rows))
        for row_idx, (parametro, valore) in enumerate(rows):
            # Colonna parametro - Font come altri box, senza grassetto
            param_item = QTableWidgetItem(parametro)
            param_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            param_item.setForeground(QColor(Qt.white))
            font = param_item.font()
            font.setPointSize(10)
            font.setBold(False)  # Nessun grassetto
            param_item.setFont(font)
            self.table.setItem(row_idx, 0, param_item)
            
            # Colonna valore - Font come altri box
            value_item = QTableWidgetItem(str(valore))
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            font = value_item.font()
            font.setPointSize(10)
            if parametro in ["Avanzamento pezzo", "Avanzamento lotto"]:
                font.setBold(False)
                value_item.setForeground(QColor(100, 255, 255))  # Cyan più brillante
            else:
                font.setBold(False)
                value_item.setForeground(QColor(Qt.white))
            value_item.setFont(font)
            self.table.setItem(row_idx, 1, value_item)

