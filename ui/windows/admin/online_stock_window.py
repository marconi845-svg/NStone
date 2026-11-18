"""
Nstone LLM - Finestra Online Stock
Gestione stock prodotti (SQLite / CSV via catalog_db)
"""
import sys
import re
from pathlib import Path
from datetime import datetime
from ui.common.datetime_ui import format_header_datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QTableWidget,
    QTableWidgetItem, QLineEdit, QHeaderView, QMessageBox,
    QFormLayout, QDialogButtonBox, QDoubleSpinBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.catalog_db import (
    PRODUCT_KEYS,
    clear_catalog_cache,
    delete_online_stock_product,
    get_catalog_info,
    insert_online_stock_product,
    is_online_stock_editable,
    load_online_stock_records,
    update_online_stock_product,
)

_BTN_STYLE = """
    QPushButton {
        background-color: #4a2a6a;
        color: #FFFFFF;
        border: 2px solid #5a3a7a;
        border-radius: 8px;
        font-size: 13px;
        font-weight: bold;
        padding: 8px 16px;
    }
    QPushButton:hover { background-color: #5a3a7a; }
    QPushButton:pressed { background-color: #3a1a5a; }
    QPushButton:disabled {
        background-color: #2a2a3a;
        color: #666666;
        border-color: #3a3a4a;
    }
"""


class OnlineStockEditDialog(SectionDialog):
    """Form inserimento / modifica prodotto catalogo."""

    FIELD_LABELS = {
        "Name": "Nome",
        "Type": "Tipo",
        "Color": "Colore",
        "Origin": "Origine",
        "Finish": "Finitura",
        "Thickness": "Spessore (cm)",
        "Dimensions": "Dimensioni (es. 305x152)",
        "Stock": "Stock (mq)",
        "Price": "Prezzo (€/mq)",
    }

    def __init__(self, parent=None, record: dict = None):
        super().__init__(parent)
        self.record = record or {}
        self.is_new = not self.record.get("id")
        self.setWindowTitle("New product" if self.is_new else "Edit product")
        self.setMinimumWidth(480)
        self._inputs = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        for key in PRODUCT_KEYS:
            if key in ("Thickness", "Stock", "Price"):
                widget = QDoubleSpinBox()
                widget.setRange(0, 1_000_000)
                widget.setDecimals(3 if key == "Thickness" else 2)
                widget.setSingleStep(0.5 if key == "Thickness" else 1.0)
                try:
                    widget.setValue(float(str(self.record.get(key) or 0).replace(",", ".")))
                except ValueError:
                    widget.setValue(0.0)
            else:
                widget = QLineEdit(str(self.record.get(key) or ""))
            self._inputs[key] = widget
            form.addRow(self.FIELD_LABELS.get(key, key), widget)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def product_data(self) -> dict:
        data = {}
        for key, widget in self._inputs.items():
            if isinstance(widget, QDoubleSpinBox):
                value = widget.value()
                data[key] = str(int(value)) if key != "Thickness" and value == int(value) else str(value)
            else:
                data[key] = widget.text().strip()
        return data


class OnlineStockWindow(SectionDialog):
    """Finestra Online Stock per visualizzare e gestire lo stock"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Online Stock")
        self.setMinimumSize(1400, 800)
        self.setModal(False)  # Non modale per permettere interazione con altre finestre
        
        # Dati
        self.all_data = []
        self.filtered_data = []
        self._catalog_source = ""
        self._editable = False
        
        self.init_ui()
        self.load_catalog_data()
        self.apply_stylesheet()

    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Breadcrumb
        breadcrumb = self.create_breadcrumb()
        main_layout.addWidget(breadcrumb)
        
        # Contenuto principale
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)
        
        # Barra di ricerca e azioni
        search_bar = self.create_search_bar()
        content_layout.addWidget(search_bar)

        toolbar = self.create_toolbar()
        content_layout.addWidget(toolbar)
        
        # Tabella
        table_widget = self.create_table()
        content_layout.addWidget(table_widget, 1)
        
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
        
        # Info sviluppatore a sinistra
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
    
    def create_breadcrumb(self):
        """Crea il breadcrumb sopra la tabella"""
        breadcrumb_frame = QFrame()
        breadcrumb_frame.setFixedHeight(50)
        breadcrumb_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border-bottom: 1px solid #2a2a3a;
            }
        """)
        breadcrumb_layout = QHBoxLayout(breadcrumb_frame)
        breadcrumb_layout.setContentsMargins(20, 10, 20, 10)
        breadcrumb_layout.setSpacing(15)
        
        # Pulsante Back - più visibile e grande
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
        breadcrumb_layout.addWidget(back_button)
        
        breadcrumb_label = QLabel("/ products")
        breadcrumb_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        breadcrumb_layout.addWidget(breadcrumb_label)

        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        breadcrumb_layout.addWidget(self.source_label)
        breadcrumb_layout.addStretch()
        
        return breadcrumb_frame
    
    def create_search_bar(self):
        """Crea la barra di ricerca"""
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(10)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search products...")
        self.search_input.setMinimumHeight(40)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 8px;
                padding: 10px 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #5a3a7a;
            }
            QLineEdit:hover {
                border: 1px solid #4a3a5a;
            }
        """)
        self.search_input.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.search_input)

        return search_frame

    def create_toolbar(self):
        """Pulsanti modifica catalogo (solo SQLite)."""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.add_btn = QPushButton("+ New")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.refresh_btn = QPushButton("Refresh")

        for btn in (self.add_btn, self.edit_btn, self.delete_btn, self.refresh_btn):
            btn.setStyleSheet(_BTN_STYLE)
            btn.setMinimumHeight(38)

        self.add_btn.clicked.connect(self.add_product)
        self.edit_btn.clicked.connect(self.edit_selected_product)
        self.delete_btn.clicked.connect(self.delete_selected_product)
        self.refresh_btn.clicked.connect(self.refresh_data)

        layout.addWidget(self.add_btn)
        layout.addWidget(self.edit_btn)
        layout.addWidget(self.delete_btn)
        layout.addStretch()
        layout.addWidget(self.refresh_btn)
        return frame

    def _set_editing_enabled(self, enabled: bool):
        self._editable = enabled
        self.add_btn.setEnabled(enabled)
        self.edit_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        if enabled:
            self.source_label.setText(f"SQLite — modifica abilitata · {self._catalog_source}")
            self.source_label.setStyleSheet("color: #7dcea0; font-size: 12px;")
        else:
            hint = "Solo lettura (CSV o DB non disponibile)"
            if self._catalog_source:
                hint = f"{self._catalog_source} · {hint}"
            self.source_label.setText(hint)
            self.source_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
    
    def create_table(self):
        """Crea la tabella dei prodotti"""
        table_frame = QFrame()
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)
        
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "Type", "Color", "Origin",
            "Finish", "Thickness", "Dimensions", "Stock", "Price",
        ])
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #2a2a3a;
            }
            QTableWidget::item {
                padding: 10px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #4a2a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #FFFFFF;
                padding: 12px;
                border: none;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        
        # Configura header
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        
        # Font moderno
        font = QFont()
        font_families = ["Montserrat", "Roboto", "Open Sans", "Segoe UI", "Arial"]
        for font_family in font_families:
            font.setFamily(font_family)
            if font.exactMatch():
                break
        font.setPointSize(11)
        self.table.setFont(font)
        
        table_layout.addWidget(self.table)
        
        return table_frame
    
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
        
        footer_label = QLabel("NStone — all rights reserved.")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setStyleSheet("color: #AAAAAA; font-size: 10px;")
        footer_layout.addWidget(footer_label)
        
        return footer_frame
    
    def load_catalog_data(self):
        """Carica prodotti da SQLite (fallback CSV, solo lettura)."""
        self.all_data = []
        try:
            source, records = load_online_stock_records(use_cache=False)
            info = get_catalog_info()
            self._catalog_source = f"{info.get('source', source)} ({info.get('count', len(records))} prodotti)"
            for row in records:
                self.all_data.append({
                    "id": row.get("id"),
                    "Name": row.get("Name", ""),
                    "Type": row.get("Type", ""),
                    "Color": row.get("Color", ""),
                    "Origin": row.get("Origin", ""),
                    "Finish": row.get("Finish", ""),
                    "Thickness": row.get("Thickness", ""),
                    "Dimensions": row.get("Dimensions", ""),
                    "Stock": row.get("Stock", ""),
                    "Price": row.get("Price", ""),
                })
            self.filtered_data = self.all_data.copy()
            self._set_editing_enabled(is_online_stock_editable())
            self.populate_table()
        except (FileNotFoundError, ValueError) as exc:
            self._set_editing_enabled(False)
            print(f"Errore caricamento catalogo: {exc}")
        except Exception as exc:
            self._set_editing_enabled(False)
            print(f"Errore nel caricamento catalogo: {exc}")
    
    def convert_to_cm(self, value):
        """Converte un valore in centimetri se necessario"""
        if not value:
            return value
        
        value = str(value).strip()
        
        # Se già in cm, restituisci così com'è
        if 'cm' in value.lower():
            return value
        
        # Prova a convertire da mm
        if 'mm' in value.lower():
            try:
                num = float(re.findall(r'\d+\.?\d*', value)[0])
                return f"{num / 10:.1f} cm"
            except:
                pass
        
        # Prova a convertire da metri
        if 'm' in value.lower() and 'cm' not in value.lower() and 'mm' not in value.lower():
            try:
                num = float(re.findall(r'\d+\.?\d*', value)[0])
                return f"{num * 100:.1f} cm"
            except:
                pass
        
        # Se c'è solo un numero (senza unità), assumi che sia in cm
        try:
            # Prova a estrarre solo il numero
            num_str = re.findall(r'^\d+\.?\d*$', value)
            if num_str:
                num = float(num_str[0])
                # Se è un numero intero, mostra senza decimali
                if num == int(num):
                    return f"{int(num)} cm"
                else:
                    return f"{num} cm"
        except:
            pass
        
        return value
    
    def convert_dimensions_to_cm(self, value):
        """Converte le dimensioni in centimetri se necessario"""
        if not value:
            return value
        
        value = str(value).strip()
        
        # Se già in cm, restituisci così com'è
        if 'cm' in value.lower():
            return value
        
        # Pattern per dimensioni tipo "300x200 cm" o "300x200mm" o "300x200" (senza unità)
        pattern = r'(\d+\.?\d*)\s*[xX]\s*(\d+\.?\d*)\s*(mm|cm|m)?'
        match = re.search(pattern, value)
        
        if match:
            width = float(match.group(1))
            height = float(match.group(2))
            unit = match.group(3) if match.group(3) else 'cm'  # Default a cm se non specificato
            
            if unit.lower() == 'mm':
                width = width / 10
                height = height / 10
            elif unit.lower() == 'm':
                width = width * 100
                height = height * 100
            # Se unit è 'cm' o None, mantieni i valori così come sono
            
            return f"{int(width)}x{int(height)} cm"
        
        return value
    
    def filter_table(self, text):
        """Filtra la tabella in base al testo di ricerca"""
        search_text = text.lower().strip()
        
        if not search_text:
            self.filtered_data = self.all_data.copy()
        else:
            self.filtered_data = [
                row for row in self.all_data
                if any(search_text in str(value).lower() for value in row.values())
            ]
        
        self.populate_table()
    
    def populate_table(self):
        """Popola la tabella con i dati filtrati."""
        self.table.setRowCount(len(self.filtered_data))
        columns = [
            ("id", lambda d: "" if d.get("id") is None else str(d["id"])),
            ("Name", lambda d: d["Name"]),
            ("Type", lambda d: d["Type"]),
            ("Color", lambda d: d["Color"]),
            ("Origin", lambda d: d["Origin"]),
            ("Finish", lambda d: d["Finish"]),
            ("Thickness", lambda d: self.convert_to_cm(d["Thickness"])),
            ("Dimensions", lambda d: self.convert_dimensions_to_cm(d["Dimensions"])),
            ("Stock", lambda d: d["Stock"]),
            ("Price", lambda d: d["Price"]),
        ]
        for row_idx, data in enumerate(self.filtered_data):
            for col_idx, (_, getter) in enumerate(columns):
                item = QTableWidgetItem(getter(data))
                if col_idx == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)

    def _selected_record(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered_data):
            return None
        return self.filtered_data[row]

    def _on_row_double_clicked(self):
        if self._editable:
            self.edit_selected_product()

    def add_product(self):
        if not self._editable:
            return
        dialog = OnlineStockEditDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        result = insert_online_stock_product(dialog.product_data())
        if result.get("ok"):
            self.refresh_data()
            QMessageBox.information(self, "Saved", "Prodotto aggiunto al catalogo.")
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Salvataggio fallito."))

    def edit_selected_product(self):
        if not self._editable:
            QMessageBox.information(
                self,
                "Read only",
                "Per modificare il catalogo serve SQLite (data/nstonellm.db).\n"
                "Esegui: python database/init_db.py",
            )
            return
        record = self._selected_record()
        if not record or record.get("id") is None:
            QMessageBox.warning(self, "Selection", "Seleziona un prodotto dalla tabella.")
            return
        dialog = OnlineStockEditDialog(self, record=record)
        if dialog.exec_() != QDialog.Accepted:
            return
        result = update_online_stock_product(record["id"], dialog.product_data())
        if result.get("ok"):
            self.refresh_data()
            QMessageBox.information(self, "Saved", "Prodotto aggiornato.")
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Aggiornamento fallito."))

    def delete_selected_product(self):
        if not self._editable:
            return
        record = self._selected_record()
        if not record or record.get("id") is None:
            QMessageBox.warning(self, "Selection", "Seleziona un prodotto da eliminare.")
            return
        name = record.get("Name", "")
        answer = QMessageBox.question(
            self,
            "Confirm deletion",
            f"Eliminare «{name}» dal catalogo?\nL'operazione non è reversibile.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        result = delete_online_stock_product(record["id"])
        if result.get("ok"):
            self.refresh_data()
            QMessageBox.information(self, "Deleted", "Prodotto rimosso dal catalogo.")
        else:
            QMessageBox.warning(self, "Error", result.get("error", "Eliminazione fallita."))
    
    def update_datetime(self):
        """Update header date/time (English)."""
        self.datetime_label.setText(format_header_datetime())
    
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
    
    def refresh_data(self):
        """Ricarica il catalogo prodotti dal database."""
        clear_catalog_cache()
        self.load_catalog_data()
    
    def go_back(self):
        """Porta il focus alla dashboard (sezione resta aperta o in icona)."""
        self.go_back_to_dashboard()

