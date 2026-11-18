"""
Nstone LLM - Finished Goods / Material Yield
Finestra gestione sprechi materiale (calcolo spreco lastra + domande RAG).
Estratta da nstone_main_window.py (pulizia god-file).
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFrame, QDialog, QTableWidget, QTableWidgetItem,
                             QDoubleSpinBox, QTextEdit, QMessageBox, QHeaderView,
                             QGroupBox, QScrollArea)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from ui.common.section_window import SectionDialog

# Import RAG Engine se disponibile
try:
    from llm.rag_engine import RAGEngine
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠ Modulo RAG Engine non disponibile")


class LavoratiRAGWorker(QThread):
    """Worker thread per generare risposte RAG senza bloccare la UI"""
    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(dict)  # Emette il risultato quando finisce
    error = pyqtSignal(str)  # Emette errore se qualcosa va storto
    
    def __init__(self, rag_engine, question, lavorati_context):
        super().__init__()
        self.rag_engine = rag_engine
        self.question = question
        self.lavorati_context = lavorati_context
    
    def run(self):
        """Esegue la generazione della risposta"""
        try:
            # Arricchisci la domanda con contesto lavorati
            enriched_question = f"""{self.question}

[CONTESTO GESTIONE LAVORATI]
{self.lavorati_context}
"""
            
            # Genera risposta con reasoning strutturato
            result = self.rag_engine.generate_answer(
                enriched_question, 
                include_reasoning=True
            )
            
            # Aggiungi contesto lavorati al risultato per riferimento
            result["lavorati_context"] = self.lavorati_context
            
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class WasteManagementWindow(SectionDialog):
    """Finestra per la gestione sprechi materiale"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📦 Finished Goods / Material Yield")
        self.setMinimumSize(1400, 900)
        self.pieces = []  # Lista dei pezzi: [{"width": float, "height": float, "quantity": int}, ...]
        
        # Inizializza RAG Engine se disponibile
        if RAG_AVAILABLE:
            try:
                self.rag_engine = RAGEngine()
            except Exception as e:
                print(f"⚠ Errore inizializzazione RAG Engine: {e}")
                self.rag_engine = None
        else:
            self.rag_engine = None
        
        self.init_ui()
        self.apply_stylesheet()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Titolo
        title_label = QLabel("📦 Finished Goods / Material Yield")
        title_label.setStyleSheet("""
            color: #FFFFFF;
            font-size: 32px;
            font-weight: bold;
            padding: 20px;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Widget contenitore per lo scroll
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(20)
        
        # Layout orizzontale per i tre box
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # BOX SINISTRO - Layout verticale per Dati Lastra e Dati Blocco
        left_column = QVBoxLayout()
        left_column.setSpacing(20)
        left_column.setContentsMargins(0, 0, 0, 0)
        left_box = self.create_slab_data_box()
        left_column.addWidget(left_box)
        block_box = self.create_block_data_box()
        left_column.addWidget(block_box)
        left_column.addStretch()
        
        left_widget = QWidget()
        left_widget.setLayout(left_column)
        left_widget.setMinimumWidth(300)
        content_layout.addWidget(left_widget, 1)
        
        # BOX CENTRO - Tabella Pezzi
        center_box = self.create_pieces_table_box()
        center_box.setMinimumWidth(400)
        content_layout.addWidget(center_box, 2)
        
        # BOX DESTRO - Risultati
        right_box = self.create_results_box()
        right_box.setMinimumWidth(300)
        content_layout.addWidget(right_box, 1)
        
        scroll_layout.addLayout(content_layout, 1)
        
        # Sezione Domanda Operativa - Motore Neurale
        rag_section = self.create_rag_section()
        scroll_layout.addWidget(rag_section)
        
        scroll_layout.addStretch()
        
        # Imposta il widget nello scroll area
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #1a1a2a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a2a6a;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5a3a7a;
            }
        """)
        
        main_layout.addWidget(scroll_area, 1)
    
    def create_slab_data_box(self):
        """Crea il box sinistro con i dati della lastra"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(box)
        layout.setSpacing(15)
        
        # Titolo
        title = QLabel("📐 Slab Data")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Larghezza
        width_label = QLabel("Width (cm):")
        width_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        layout.addWidget(width_label)
        self.slab_width = QDoubleSpinBox()
        self.slab_width.setMinimum(0.1)
        self.slab_width.setMaximum(10000)
        self.slab_width.setDecimals(2)
        self.slab_width.setSuffix(" cm")
        self.slab_width.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.slab_width)
        
        # Altezza
        height_label = QLabel("Height (cm):")
        height_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        layout.addWidget(height_label)
        self.slab_height = QDoubleSpinBox()
        self.slab_height.setMinimum(0.1)
        self.slab_height.setMaximum(10000)
        self.slab_height.setDecimals(2)
        self.slab_height.setSuffix(" cm")
        self.slab_height.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.slab_height)
        
        # Spessore
        thickness_label = QLabel("Thickness (cm):")
        thickness_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        layout.addWidget(thickness_label)
        self.slab_thickness = QDoubleSpinBox()
        self.slab_thickness.setMinimum(0.1)
        self.slab_thickness.setMaximum(1000)
        self.slab_thickness.setDecimals(2)
        self.slab_thickness.setSuffix(" cm")
        self.slab_thickness.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.slab_thickness)
        
        layout.addStretch()
        
        return box
    
    def create_block_data_box(self):
        """Crea il box con i dati del blocco"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(box)
        layout.setSpacing(15)
        
        # Titolo
        title = QLabel("📦 Block Data")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Larghezza blocco
        width_label = QLabel("Block width (cm):")
        width_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        layout.addWidget(width_label)
        self.block_width = QDoubleSpinBox()
        self.block_width.setMinimum(0.1)
        self.block_width.setMaximum(10000)
        self.block_width.setDecimals(2)
        self.block_width.setValue(0.10)
        self.block_width.setSuffix(" cm")
        self.block_width.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.block_width)
        
        # Altezza blocco
        height_label = QLabel("Block height (cm):")
        height_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        layout.addWidget(height_label)
        self.block_height = QDoubleSpinBox()
        self.block_height.setMinimum(0.1)
        self.block_height.setMaximum(10000)
        self.block_height.setDecimals(2)
        self.block_height.setValue(0.10)
        self.block_height.setSuffix(" cm")
        self.block_height.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.block_height)
        
        # Spessore blocco
        thickness_label = QLabel("Block thickness (cm):")
        thickness_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        layout.addWidget(thickness_label)
        self.block_thickness = QDoubleSpinBox()
        self.block_thickness.setMinimum(0.1)
        self.block_thickness.setMaximum(1000)
        self.block_thickness.setDecimals(2)
        self.block_thickness.setValue(0.10)
        self.block_thickness.setSuffix(" cm")
        self.block_thickness.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.block_thickness)
        
        layout.addStretch()
        
        return box
    
    def create_pieces_table_box(self):
        """Crea il box centrale con la tabella dei pezzi"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(box)
        layout.setSpacing(15)
        
        # Titolo e pulsanti
        header_layout = QHBoxLayout()
        title = QLabel("📦 Pieces to Cut")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        # Pulsante Aggiungi
        add_btn = QPushButton("➕ Add piece")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        add_btn.clicked.connect(self.add_piece)
        header_layout.addWidget(add_btn)
        
        # Pulsante Rimuovi
        remove_btn = QPushButton("🗑 Remove piece")
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #6a2a2a;
                color: #FFFFFF;
                border: 1px solid #7a3a3a;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7a3a3a;
            }
            QPushButton:pressed {
                background-color: #5a1a1a;
            }
        """)
        remove_btn.clicked.connect(self.remove_selected_piece)
        header_layout.addWidget(remove_btn)
        
        layout.addLayout(header_layout)
        
        # Tabella pezzi
        self.pieces_table = QTableWidget()
        self.pieces_table.setColumnCount(3)
        self.pieces_table.setHorizontalHeaderLabels(["Larghezza (cm)", "Altezza (cm)", "Quantità"])
        self.pieces_table.setStyleSheet("""
            QTableWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
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
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        self.pieces_table.horizontalHeader().setStretchLastSection(True)
        self.pieces_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pieces_table.setAlternatingRowColors(True)
        self.pieces_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        layout.addWidget(self.pieces_table, 1)
        
        return box
    
    def create_results_box(self):
        """Crea il box destro con i risultati calcolati"""
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(box)
        layout.setSpacing(15)
        
        # Titolo
        title = QLabel("📊 Calculation Results")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Pulsante Calcola
        calc_btn = QPushButton("🔄 Calculate waste")
        calc_btn.setMinimumHeight(45)
        calc_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        calc_btn.clicked.connect(self.calculate_waste_with_gemini)
        layout.addWidget(calc_btn)
        
        # Area risultati
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("Clicca 'Calcola spreco' per ottenere i risultati...")
        self.results_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                padding: 15px;
                font-size: 13px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        layout.addWidget(self.results_text, 1)
        
        return box
    
    def add_piece(self):
        """Aggiunge un nuovo pezzo alla tabella"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Piece")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        
        # Larghezza
        width_label = QLabel("Width (cm):")
        width_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        width_input = QDoubleSpinBox()
        width_input.setMinimum(0.1)
        width_input.setMaximum(10000)
        width_input.setDecimals(2)
        width_input.setSuffix(" cm")
        width_input.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
            }
        """)
        layout.addWidget(width_label)
        layout.addWidget(width_input)
        
        # Altezza
        height_label = QLabel("Height (cm):")
        height_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        height_input = QDoubleSpinBox()
        height_input.setMinimum(0.1)
        height_input.setMaximum(10000)
        height_input.setDecimals(2)
        height_input.setSuffix(" cm")
        height_input.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
            }
        """)
        layout.addWidget(height_label)
        layout.addWidget(height_input)
        
        # Quantità
        qty_label = QLabel("Quantity:")
        qty_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        qty_input = QDoubleSpinBox()
        qty_input.setMinimum(1)
        qty_input.setMaximum(1000)
        qty_input.setDecimals(0)
        qty_input.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
            }
        """)
        layout.addWidget(qty_label)
        layout.addWidget(qty_input)
        
        # Pulsanti
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 6px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
        
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1a2a;
            }
            QLabel {
                color: #FFFFFF;
            }
        """)
        
        if dialog.exec_() == QDialog.Accepted:
            piece = {
                "width": width_input.value(),
                "height": height_input.value(),
                "quantity": int(qty_input.value())
            }
            self.pieces.append(piece)
            self.update_pieces_table()
    
    def remove_selected_piece(self):
        """Rimuove il pezzo selezionato dalla tabella"""
        current_row = self.pieces_table.currentRow()
        if current_row >= 0 and current_row < len(self.pieces):
            del self.pieces[current_row]
            self.update_pieces_table()
        else:
            QMessageBox.warning(self, "Nessuna selezione", "Seleziona un pezzo da rimuovere.")
    
    def update_pieces_table(self):
        """Aggiorna la tabella dei pezzi"""
        self.pieces_table.setRowCount(len(self.pieces))
        for row, piece in enumerate(self.pieces):
            self.pieces_table.setItem(row, 0, QTableWidgetItem(f"{piece['width']:.2f}"))
            self.pieces_table.setItem(row, 1, QTableWidgetItem(f"{piece['height']:.2f}"))
            self.pieces_table.setItem(row, 2, QTableWidgetItem(str(piece['quantity'])))
    
    def calculate_waste_with_gemini(self):
        """Calcola lo spreco materiale usando Gemini"""
        # Verifica dati lastra
        slab_width = self.slab_width.value()
        slab_height = self.slab_height.value()
        slab_thickness = self.slab_thickness.value()
        
        if slab_width <= 0 or slab_height <= 0 or slab_thickness <= 0:
            QMessageBox.warning(self, "Dati mancanti", "Inserisci i dati della lastra (larghezza, altezza, spessore).")
            return
        
        if not self.pieces:
            QMessageBox.warning(self, "Nessun pezzo", "Aggiungi almeno un pezzo da tagliare.")
            return
        
        try:
            # Importa GeminiService
            from llm.gemini_service import GeminiService
            
            gemini_service = GeminiService()
            
            if not gemini_service.is_ready:
                QMessageBox.warning(self, "LLM non disponibile",
                                  "Avvia Ollama (Qwen locale) o configura API Gemini nelle impostazioni.")
                return
            
            # Prepara i dati per Gemini
            pieces_text = "\n".join([
                f"  - Pezzo {i+1}: {p['width']} cm x {p['height']} cm (quantità: {p['quantity']})"
                for i, p in enumerate(self.pieces)
            ])
            
            prompt = f"""Sei un esperto nel calcolo dell'ottimizzazione del taglio di lastre di marmo e pietre naturali per NStone.

DATI LASTRA:
- Larghezza: {slab_width} cm
- Altezza: {slab_height} cm
- Spessore: {slab_thickness} cm

PEZZI DA TAGLIARE:
{pieces_text}

CALCOLA E FORNISCI:
1. Superficie totale della lastra (in cm²)
2. Superficie totale occupata dai pezzi (in cm²)
3. Spreco assoluto (in cm²)
4. Percentuale di spreco
5. Valutazione:
   - 🟢 Ottimo (< 10%)
   - 🟡 Accettabile (10-25%)
   - 🔴 Da ottimizzare (> 25%)
6. Suggerimenti per ottimizzare il taglio (se applicabile)

Rispondi in formato chiaro e strutturato, con numeri precisi e calcoli espliciti."""

            self.results_text.clear()
            self.results_text.append("⏳ Calcolo in corso con Gemini...")
            self.results_text.append("")
            
            # Chiama Gemini
            response = gemini_service.send_message(prompt)
            
            if not response or not response.strip():
                self.results_text.append("❌ ERRORE: Nessuna risposta da Gemini")
                return
            
            self.results_text.clear()
            self.results_text.append("📊 RISULTATI CALCOLO SPRECO\n")
            self.results_text.append("=" * 60)
            self.results_text.append("")
            self.results_text.append(response)
            
        except Exception as e:
            error_msg = f"❌ ERRORE durante il calcolo:\n{str(e)}"
            self.results_text.clear()
            self.results_text.append(error_msg)
            import traceback
            self.results_text.append("\nTraceback completo:")
            self.results_text.append(traceback.format_exc())
            QMessageBox.critical(self, "Errore", f"Errore durante il calcolo:\n{e}")
    
    def create_rag_section(self):
        """Crea la sezione Domanda Operativa con RAG Engine"""
        rag_widget = QGroupBox("🧠 Operational Question — Neural Engine")
        rag_widget.setStyleSheet("""
            QGroupBox {
                background-color: #1a1a2a;
                border: 2px solid #3a3a4a;
                border-radius: 8px;
                padding: 15px;
                margin-top: 10px;
                color: #FFFFFF;
                font-size: 18px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: #1a1a2a;
            }
        """)
        rag_layout = QVBoxLayout(rag_widget)
        rag_layout.setContentsMargins(15, 15, 15, 15)
        rag_layout.setSpacing(10)
        
        # Campo domanda
        question_label = QLabel("Question:")
        question_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        rag_layout.addWidget(question_label)
        
        self.question_text = QTextEdit()
        self.question_text.setPlaceholderText(
            "Esempio: 'Come ottimizzare il taglio per ridurre gli sprechi?'\n"
            "Esempio: 'Qual è la migliore disposizione dei pezzi sulla lastra?'\n"
            "Esempio: 'Spiega come calcolare lo spreco materiale'"
        )
        self.question_text.setMaximumHeight(80)
        self.question_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 12px;
            }
        """)
        rag_layout.addWidget(self.question_text)
        
        # Pulsante
        button_layout = QHBoxLayout()
        self.ask_button = QPushButton("Ask Neural Engine")
        self.ask_button.setStyleSheet("""
            QPushButton {
                background-color: #2a1a3a;
                border: 1px solid #4a3a5a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a2a4a;
                border: 1px solid #5a4a6a;
            }
            QPushButton:pressed {
                background-color: #1a0a2a;
            }
            QPushButton:disabled {
                background-color: #1a1a2a;
                color: #666666;
            }
        """)
        self.ask_button.clicked.connect(self.on_ask_neural_engine)
        button_layout.addWidget(self.ask_button)
        button_layout.addStretch()
        rag_layout.addLayout(button_layout)
        
        # Area risposta
        answer_label = QLabel("Neural Engine response:")
        answer_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        rag_layout.addWidget(answer_label)
        
        self.answer_text = QTextEdit()
        self.answer_text.setReadOnly(True)
        self.answer_text.setPlaceholderText("La risposta del motore neurale apparirà qui...")
        self.answer_text.setMinimumHeight(150)
        self.answer_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        rag_layout.addWidget(self.answer_text)
        
        # Area reasoning strutturato
        reasoning_label = QLabel("Reasoning Strutturato (Livello 2):")
        reasoning_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        rag_layout.addWidget(reasoning_label)
        
        self.reasoning_text = QTextEdit()
        self.reasoning_text.setReadOnly(True)
        self.reasoning_text.setPlaceholderText(
            "1. INTERPRETAZIONE DELLA DOMANDA\n"
            "2. DATI RILEVANTI TROVATI\n"
            "3. DECISIONE LOGICA\n"
            "4. RISPOSTA FINALE"
        )
        self.reasoning_text.setMinimumHeight(200)
        self.reasoning_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        rag_layout.addWidget(self.reasoning_text)
        
        return rag_widget
    
    def on_ask_neural_engine(self):
        """Gestisce la richiesta al motore neurale"""
        if not RAG_AVAILABLE or self.rag_engine is None:
            QMessageBox.warning(
                self,
                "RAG Engine non disponibile",
                "Il motore neurale non è disponibile. Verifica che il modulo RAG Engine sia installato."
            )
            return
        
        question = self.question_text.toPlainText().strip()
        if not question:
            QMessageBox.warning(self, "Domanda vuota", "Inserisci una domanda prima di procedere.")
            return
        
        # Disabilita il pulsante durante l'elaborazione
        self.ask_button.setEnabled(False)
        self.answer_text.clear()
        self.answer_text.append("⏳ Elaborazione in corso...")
        self.reasoning_text.clear()
        
        # Crea e avvia il worker thread
        self.rag_worker = LavoratiRAGWorker(self.rag_engine, question, self.build_lavorati_context())
        self.rag_worker.result_ready.connect(self.on_rag_finished)
        self.rag_worker.error.connect(self.on_rag_error)
        self.rag_worker.start()
    
    def build_lavorati_context(self):
        """Costruisce il contesto per la domanda RAG"""
        context = []
        
        # Dati Lastra
        if hasattr(self, 'slab_width') and hasattr(self, 'slab_height') and hasattr(self, 'slab_thickness'):
            context.append(f"Dati Lastra: Larghezza={self.slab_width.value()} cm, Altezza={self.slab_height.value()} cm, Spessore={self.slab_thickness.value()} cm")
        
        # Dati Blocco
        if hasattr(self, 'block_width') and hasattr(self, 'block_height') and hasattr(self, 'block_thickness'):
            context.append(f"Dati Blocco: Larghezza={self.block_width.value()} cm, Altezza={self.block_height.value()} cm, Spessore={self.block_thickness.value()} cm")
        
        # Pezzi da tagliare
        if self.pieces:
            pieces_info = []
            for i, piece in enumerate(self.pieces, 1):
                pieces_info.append(f"Pezzo {i}: {piece['width']} cm x {piece['height']} cm (quantità: {piece['quantity']})")
            context.append(f"Pezzi da tagliare: {len(self.pieces)} pezzi\n" + "\n".join(pieces_info))
        else:
            context.append("Nessun pezzo da tagliare ancora inserito")
        
        return "\n".join(context)
    
    def on_rag_finished(self, result):
        """Gestisce il completamento della richiesta RAG"""
        self.ask_button.setEnabled(True)
        
        # Mostra la risposta
        if "answer" in result:
            self.answer_text.clear()
            self.answer_text.append(result["answer"])
        else:
            self.answer_text.clear()
            self.answer_text.append("❌ Nessuna risposta generata")
        
        # Mostra il reasoning se disponibile
        if "reasoning" in result and result["reasoning"]:
            self.reasoning_text.clear()
            self.reasoning_text.append(result["reasoning"])
        else:
            self.reasoning_text.clear()
            self.reasoning_text.append("Reasoning non disponibile per questa risposta.")
    
    def on_rag_error(self, error_msg):
        """Gestisce gli errori della richiesta RAG"""
        self.ask_button.setEnabled(True)
        self.answer_text.clear()
        self.answer_text.append(f"❌ ERRORE: {error_msg}")
        self.reasoning_text.clear()
        QMessageBox.critical(self, "Errore RAG", f"Errore durante l'elaborazione:\n{error_msg}")
    
    def apply_stylesheet(self):
        """Applica lo stylesheet con tema scuro"""
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
        """)
