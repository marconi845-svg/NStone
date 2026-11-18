"""
Widget per Analisi Fanghi - Depurazione
Usato nella sezione Gestione CNC Universale
"""
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class AnalisiFanghiWidget(QGroupBox):
    """Widget tabella per visualizzare l'analisi fanghi e depurazione"""
    
    def __init__(self, parent=None):
        super().__init__("Analisi Fanghi — Depurazione", parent)
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
        self.update_analisi(
            umidita_residua=0.0,
            densita_fango=0.0,
            granulometria_media=0.0,
            ph=7.0,
            volume_fanghi_prodotti=0.0,
            cicli_filtropressa=0,
            tempo_ciclo_medio=0,
            stato_filtropressa="--",
            qualita_acqua_riciclata=0.0
        )
    
    def update_analisi(self, umidita_residua=None, densita_fango=None,
                      granulometria_media=None, ph=None,
                      volume_fanghi_prodotti=None, cicli_filtropressa=None,
                      tempo_ciclo_medio=None, stato_filtropressa=None,
                      qualita_acqua_riciclata=None):
        """Aggiorna i dati dell'analisi fanghi"""
        # Prepara i dati
        rows = [
            ("Umidità residua", f"{umidita_residua:.1f} %" if umidita_residua is not None else "-- %"),
            ("Densità fango", f"{densita_fango:.1f} kg/m³" if densita_fango is not None else "-- kg/m³"),
            ("Granulometria media", f"{granulometria_media:.1f} µm" if granulometria_media is not None else "-- µm"),
            ("pH", f"{ph:.2f}" if ph is not None else "--"),
            ("Volume fanghi prodotti", f"{volume_fanghi_prodotti:.2f} m³/giorno" if volume_fanghi_prodotti is not None else "-- m³/giorno"),
            ("Cicli filtropressa", f"{int(cicli_filtropressa)}" if cicli_filtropressa is not None else "0"),
            ("Tempo ciclo medio", f"{int(tempo_ciclo_medio)} min" if tempo_ciclo_medio is not None else "-- min"),
            ("Stato filtropressa", stato_filtropressa if stato_filtropressa is not None else "--"),
            ("Qualità acqua riciclata", f"{qualita_acqua_riciclata:.1f} %" if qualita_acqua_riciclata is not None else "-- %")
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
            
            # Colore in base al parametro e valore
            if parametro == "Umidità residua":
                if umidita_residua is not None and umidita_residua > 80.0:
                    value_item.setForeground(QColor(255, 100, 100))  # Rosso se troppo alta
                else:
                    value_item.setForeground(QColor(100, 255, 255))  # Cyan
            elif parametro == "pH":
                if ph is not None and (ph < 6.0 or ph > 8.5):
                    value_item.setForeground(QColor(255, 100, 100))  # Rosso se fuori range
                else:
                    value_item.setForeground(QColor(100, 255, 255))  # Cyan
            elif parametro in ["Volume fanghi prodotti", "Cicli filtropressa", "Tempo ciclo medio"]:
                value_item.setForeground(QColor(100, 255, 255))  # Cyan per valori dinamici
            elif parametro == "Stato filtropressa":
                if stato_filtropressa == "RUN":
                    value_item.setForeground(QColor(100, 255, 100))  # Verde
                elif stato_filtropressa == "ERROR":
                    value_item.setForeground(QColor(255, 100, 100))  # Rosso
                else:
                    value_item.setForeground(QColor(Qt.white))
            else:
                font.setBold(False)
                value_item.setForeground(QColor(Qt.white))
            
            value_item.setFont(font)
            self.table.setItem(row_idx, 1, value_item)

