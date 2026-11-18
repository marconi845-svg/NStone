"""
RAG Engine Window - Finestra dedicata per RAG Engine
Interfaccia PyQt5 per domande, retrieval contesto e risposte
"""
import os
import sys
from pathlib import Path
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTextEdit, QMessageBox,
                             QApplication)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from llm.rag_engine import RAGEngine


class RAGWorker(QThread):
    """Worker thread per generare risposte senza bloccare la UI"""
    result_ready = pyqtSignal(dict)  # Emette il risultato quando finisce
    error = pyqtSignal(str)  # Emette errore se qualcosa va storto
    
    def __init__(self, rag_engine: RAGEngine, question: str, include_reasoning: bool = False):
        super().__init__()
        self.rag_engine = rag_engine
        self.question = question
        self.include_reasoning = include_reasoning
    
    def run(self):
        """Esegue la generazione della risposta"""
        try:
            result = self.rag_engine.generate_answer(self.question, self.include_reasoning)
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class RAGEngineWindow(SectionDialog):
    """Finestra RAG Engine per domande e risposte con retrieval contesto"""
    
    # Istanza unica del RAG Engine (singleton pattern)
    _rag_engine_instance = None
    
    @classmethod
    def get_rag_engine(cls):
        """Ottiene o crea l'istanza unica del RAG Engine"""
        if cls._rag_engine_instance is None:
            cls._rag_engine_instance = RAGEngine()
        return cls._rag_engine_instance
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RAG Engine")
        # Ottieni istanza RAG Engine
        self.rag_engine = self.get_rag_engine()
        
        # Worker thread
        self.worker = None
        
        # Storage per reasoning
        self._last_reasoning = ""
        self._last_reasoning_available = False
        
        # Setup dimensione finestra
        self.setup_window_size()
        
        self.init_ui()
        self.apply_stylesheet()
    
    def setup_window_size(self):
        from ui.common.window_helpers import default_window_geometry, ensure_resizable_window

        self._available_width = 1400
        self._available_height = 900
        ensure_resizable_window(self, min_width=1024, min_height=700)
        default_window_geometry(self)
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Contenuto principale (due colonne)
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(30)
        
        # Pannello sinistro - Input
        left_panel = self.create_left_panel()
        content_layout.addWidget(left_panel, 40)
        
        # Pannello destro - Output
        right_panel = self.create_right_panel()
        content_layout.addWidget(right_panel, 60)
        
        main_layout.addLayout(content_layout, 1)
        
        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)
    
    def create_header(self):
        """Crea l'header"""
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
        header_layout.setContentsMargins(30, 15, 30, 15)
        
        title_label = QLabel("RAG Engine")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        return header_frame
    
    def create_left_panel(self):
        """Crea il pannello sinistro con input"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Titolo
        title = QLabel("Domanda utente")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # QTextEdit per la domanda
        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText("Inserisci la tua domanda qui...")
        self.question_input.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 14px;
                padding: 10px;
            }
        """)
        self.question_input.setMinimumHeight(300)
        layout.addWidget(self.question_input, 1)
        
        # Pulsanti
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        # Pulsante Genera Risposta
        self.generate_button = QPushButton("Genera Risposta")
        self.generate_button.setMinimumHeight(50)
        self.generate_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                padding: 12px 25px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
            QPushButton:disabled {
                background-color: #2a2a3a;
                color: #666666;
            }
        """)
        self.generate_button.clicked.connect(self.on_generate_clicked)
        buttons_layout.addWidget(self.generate_button)
        
        # Pulsante Mostra Reasoning (nascosto di default)
        self.reasoning_button = QPushButton("Mostra Reasoning")
        self.reasoning_button.setMinimumHeight(50)
        self.reasoning_button.setVisible(False)  # Nascosto di default
        self.reasoning_button.setStyleSheet("""
            QPushButton {
                background-color: #2a5a4a;
                color: #FFFFFF;
                border: 1px solid #3a6a5a;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                padding: 12px 25px;
            }
            QPushButton:hover {
                background-color: #3a6a5a;
                border: 1px solid #4a7a6a;
            }
            QPushButton:pressed {
                background-color: #1a4a3a;
            }
        """)
        self.reasoning_button.clicked.connect(self.on_show_reasoning)
        buttons_layout.addWidget(self.reasoning_button)
        
        layout.addLayout(buttons_layout)
        
        # Barra di stato locale
        self.local_status_label = QLabel("Pronto. Inserisci una domanda e clicca 'Genera Risposta'.")
        self.local_status_label.setStyleSheet("""
            color: #AAAAAA; 
            font-size: 12px; 
            padding: 10px;
            background-color: #0a0a1a;
            border-radius: 5px;
            border: 1px solid #2a2a3a;
        """)
        self.local_status_label.setWordWrap(True)
        layout.addWidget(self.local_status_label)
        
        return panel
    
    def create_right_panel(self):
        """Crea il pannello destro con output"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Sezione A: Contesto Recuperato
        context_title = QLabel("Contesto Recuperato")
        context_title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(context_title)
        
        self.context_output = QTextEdit()
        self.context_output.setReadOnly(True)
        self.context_output.setPlaceholderText("Il contesto recuperato dal database apparirà qui...")
        self.context_output.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #CCCCCC;
                font-size: 13px;
                padding: 10px;
            }
        """)
        self.context_output.setMinimumHeight(250)
        layout.addWidget(self.context_output)
        
        # Sezione B: Risposta del Modello
        answer_title = QLabel("Risposta del Modello")
        answer_title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(answer_title)
        
        self.answer_output = QTextEdit()
        self.answer_output.setReadOnly(True)
        self.answer_output.setPlaceholderText("La risposta generata apparirà qui...")
        self.answer_output.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 14px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.answer_output, 1)
        
        return panel
    
    def create_footer(self):
        """Crea il footer"""
        footer_frame = QFrame()
        footer_frame.setFixedHeight(80)
        footer_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
        """)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(30, 15, 30, 15)
        footer_layout.setSpacing(20)
        
        # Barra di stato
        self.status_label = QLabel("RAG Engine pronto.")
        self.status_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        footer_layout.addWidget(self.status_label)
        
        footer_layout.addStretch()
        
        # Badge RAG ACTIVE
        rag_layout = QHBoxLayout()
        rag_layout.setSpacing(10)
        
        rag_indicator = QLabel("●")
        rag_indicator.setStyleSheet("color: #8B5CF6; font-size: 16px;")
        rag_layout.addWidget(rag_indicator)
        
        rag_label = QLabel("RAG ACTIVE")
        rag_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        rag_layout.addWidget(rag_label)
        
        footer_layout.addLayout(rag_layout)
        
        footer_layout.addStretch()
        
        # Pulsante Apri Memoria RAG
        memory_button = QPushButton("Apri Memoria RAG")
        memory_button.setMinimumHeight(50)
        memory_button.setMinimumWidth(180)
        memory_button.setStyleSheet("""
            QPushButton {
                background-color: #6a2a4a;
                color: #FFFFFF;
                border: 1px solid #7a3a5a;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                padding: 12px 25px;
            }
            QPushButton:hover {
                background-color: #7a3a5a;
                border: 1px solid #8a4a6a;
            }
            QPushButton:pressed {
                background-color: #5a1a3a;
            }
        """)
        memory_button.clicked.connect(self.open_memory_viewer)
        footer_layout.addWidget(memory_button)
        
        return footer_frame
    
    def on_generate_clicked(self):
        """
        Gestisce il click su Genera Risposta.
        Collega UI → Backend RAG Engine → Database → Gemini
        """
        question = self.question_input.toPlainText().strip()
        
        if not question:
            QMessageBox.warning(self, "Domanda vuota", "Inserisci una domanda prima di generare la risposta.")
            return
        
        # Verifica se il database è locked
        if self.rag_engine.is_database_locked():
            reply = QMessageBox.question(
                self, 
                "Database Bloccato",
                "Database bloccato. Il RAG Engine utilizzerà solo il contesto statico.\n\nVuoi continuare?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.No:
                return
            self.local_status_label.setText("Database bloccato. Generazione risposta senza contesto database...")
            self.status_label.setText("Database bloccato. Generazione risposta senza contesto database...")
        else:
            self.local_status_label.setText("Recupero contesto dal database...")
            self.status_label.setText("Recupero contesto dal database e generazione risposta...")
        
        # Disabilita pulsante durante la generazione
        self.generate_button.setEnabled(False)
        
        # Pulisci output precedente
        self.context_output.clear()
        self.answer_output.clear()
        self.reasoning_button.setVisible(False)
        
        # Crea e avvia worker thread
        self.worker = RAGWorker(self.rag_engine, question, include_reasoning=False)
        self.worker.result_ready.connect(self.on_generation_finished)
        self.worker.error.connect(self.on_generation_error)
        self.worker.start()
    
    def on_generation_finished(self, result: dict):
        """
        Gestisce il completamento della generazione.
        Aggiorna UI con contesto, risposta e stato.
        """
        # Mostra contesto
        context = result.get("context", "")
        if context:
            self.context_output.setPlainText(context)
        else:
            self.context_output.setPlainText("Nessun contesto disponibile.")
        
        # Mostra risposta
        answer = result.get("answer", "")
        if answer:
            self.answer_output.setPlainText(answer)
        else:
            self.answer_output.setPlainText("Nessuna risposta generata.")
        
        # Salva reasoning per uso futuro (non mostrato automaticamente)
        # Il reasoning può essere generato on-demand quando l'utente clicca "Mostra Reasoning"
        self._last_reasoning_available = True
        
        # Mostra sempre il pulsante reasoning (può essere generato on-demand)
        self.reasoning_button.setVisible(True)
        
        # Aggiorna stato
        self.generate_button.setEnabled(True)
        
        # Messaggio di stato appropriato
        if context and not context.startswith("⚠️"):
            self.local_status_label.setText("Risposta generata con successo. Contesto recuperato dal database.")
            self.status_label.setText("Risposta generata. Contesto recuperato dal database.")
        elif context.startswith("⚠️"):
            self.local_status_label.setText("Risposta generata senza contesto database (database bloccato).")
            self.status_label.setText("Risposta generata senza contesto database.")
        else:
            self.local_status_label.setText("Risposta generata. Nessun contesto disponibile.")
            self.status_label.setText("Risposta generata. Nessun contesto disponibile.")
    
    def on_generation_error(self, error_msg: str):
        """Gestisce errori durante la generazione"""
        self.generate_button.setEnabled(True)
        self.local_status_label.setText(f"Errore: {error_msg[:100]}")
        self.status_label.setText(f"Errore nella generazione: {error_msg[:50]}")
        QMessageBox.critical(self, "Error", f"Errore nella generazione della risposta:\n{error_msg}")
    
    def open_memory_viewer(self):
        """Apre la finestra RAG Memory Viewer"""
        try:
            from ui.common.window_helpers import show_auxiliary_window
            from ui.windows.ai.rag_memory_viewer import RAGMemoryViewer
            memory_viewer = RAGMemoryViewer(self)
            show_auxiliary_window(memory_viewer)
            self.status_label.setText("Memory Viewer chiuso.")
        except ImportError as e:
            QMessageBox.critical(self, "Error", f"Impossibile importare RAG Memory Viewer:\n{e}")
            self.status_label.setText("Errore nell'apertura di Memory Viewer")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Errore nell'apertura di Memory Viewer:\n{e}")
            self.status_label.setText(f"Errore: {str(e)[:50]}")
    
    def on_show_reasoning(self):
        """
        Mostra il reasoning dell'ultima risposta.
        Se non disponibile, lo genera on-demand usando explain_reasoning().
        """
        # Verifica se abbiamo già un reasoning salvato
        if hasattr(self, '_last_reasoning') and self._last_reasoning:
            reasoning = self._last_reasoning
        else:
            # Genera reasoning on-demand
            self.local_status_label.setText("Generazione reasoning in corso...")
            self.status_label.setText("Generazione reasoning...")
            
            try:
                reasoning = self.rag_engine.explain_reasoning()
                self._last_reasoning = reasoning
            except Exception as e:
                reasoning = f"Errore nella generazione del reasoning: {str(e)[:200]}"
            
            self.local_status_label.setText("Reasoning generato.")
            self.status_label.setText("Reasoning disponibile.")
        
        # Mostra reasoning in una finestra di dialogo
        if reasoning and reasoning != "Reasoning non disponibile. Genera prima una risposta.":
            # Usa QMessageBox con testo scrollabile per reasoning lungo
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Reasoning")
            msg_box.setText("Reasoning della risposta:")
            msg_box.setInformativeText(reasoning[:500] + "..." if len(reasoning) > 500 else reasoning)
            msg_box.setDetailedText(reasoning)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.exec_()
        else:
            QMessageBox.information(self, "Reasoning", "Reasoning non disponibile. Genera prima una risposta.")
    
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

