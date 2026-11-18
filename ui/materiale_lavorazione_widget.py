"""
Widget tabella per Materiale Attualmente in Lavorazione
Usato sia in Multifilo che in Lucidatrice
"""
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class MaterialeLavorazioneWidget(QGroupBox):
    """Widget tabella per visualizzare il materiale attualmente in lavorazione"""
    
    def __init__(self, parent=None):
        super().__init__("Materiale Attualmente in Lavorazione", parent)
        self.init_ui()
    
    def init_ui(self):
        """Inizializza la tabella - Grande e leggibile"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Crea tabella con 2 colonne (Parametro, Valore) - Stessa dimensione degli altri box
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
        
        # Stile tabella - Grande e leggibile
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
        self.update_materiale(
            materiale="--",
            quantita_lastre=0,
            spessore=0.0,
            finitura="--",
            colore_tipo="--",
            cliente_commessa="--",
            stato_avanzamento=0.0,
            tempo_stimato=0,
            tempo_rimanente=0
        )
    
    def update_materiale(self, materiale=None, quantita_lastre=None, spessore=None,
                       finitura=None, colore_tipo=None, cliente_commessa=None,
                       stato_avanzamento=None, tempo_stimato=None, tempo_rimanente=None):
        """Aggiorna i dati del materiale in lavorazione"""
        # Prepara i dati
        rows = [
            ("Materiale", materiale if materiale is not None else "--"),
            ("Quantità lastre", f"{int(quantita_lastre)}" if quantita_lastre is not None else "0"),
            ("Spessore", f"{spessore:.1f} mm" if spessore is not None else "-- mm"),
            ("Finitura", finitura if finitura is not None else "--"),
            ("Cliente / Commessa", cliente_commessa if cliente_commessa is not None else "--"),
            ("Stato avanzamento", f"{stato_avanzamento:.1f} %" if stato_avanzamento is not None else "0.0 %"),
            ("Tempo stimato", self._format_time(tempo_stimato) if tempo_stimato is not None else "--"),
            ("Tempo rimanente", self._format_time(tempo_rimanente) if tempo_rimanente is not None else "--")
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
            if parametro in ["Stato avanzamento", "Tempo stimato", "Tempo rimanente"]:
                font.setBold(False)
                value_item.setForeground(QColor(100, 255, 255))  # Cyan più brillante
            else:
                font.setBold(False)
                value_item.setForeground(QColor(Qt.white))
            value_item.setFont(font)
            self.table.setItem(row_idx, 1, value_item)
    
    def _format_time(self, seconds):
        """Formatta il tempo in secondi come HH:MM:SS o MM:SS"""
        if seconds is None or seconds <= 0:
            return "--"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

