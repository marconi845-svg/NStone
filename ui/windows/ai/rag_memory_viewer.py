"""
RAG Memory Viewer - Visualizzatore della memoria evolutiva del RAG Engine
Interfaccia PyQt5 per consultare le interazioni salvate
"""
import os
import sys
from pathlib import Path
import sqlite3
from datetime import datetime
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QTextEdit, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QApplication,
                             QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor


class RAGMemoryViewer(SectionDialog):
    """Finestra per visualizzare la memoria evolutiva del RAG Engine"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RAG Memory Viewer")
        # Percorso database
        self.db_path = Path(__file__).parent / "data" / "nstonellm.db"
        
        # Setup dimensione finestra
        self.setup_window_size()
        
        self.init_ui()
        self.apply_stylesheet()
        self.load_memory()
    
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
        
        # Contenuto principale
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(20)
        
        # Tabella memoria
        self.memory_table = self.create_memory_table()
        content_layout.addWidget(self.memory_table, 1)
        
        # Pulsanti
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        refresh_button = QPushButton("Refresh")
        refresh_button.setMinimumHeight(40)
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        refresh_button.clicked.connect(self.load_memory)
        buttons_layout.addWidget(refresh_button)
        
        buttons_layout.addStretch()
        
        content_layout.addLayout(buttons_layout)
        
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
        
        title_label = QLabel("RAG Memory Viewer")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        return header_frame
    
    def create_memory_table(self):
        """Crea la tabella per visualizzare la memoria"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["ID", "Timestamp", "Domanda", "Risposta", "Tag"])
        table.setStyleSheet("""
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
            }
        """)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Sola lettura
        table.setSortingEnabled(True)
        table.doubleClicked.connect(self.on_row_double_clicked)
        
        # Configura colonne
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 60)  # ID
        table.setColumnWidth(1, 200)  # Timestamp
        table.setColumnWidth(2, 400)  # Domanda
        table.setColumnWidth(3, 500)  # Risposta
        table.setColumnWidth(4, 100)  # Tag
        
        return table
    
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
        self.status_label = QLabel("Memoria RAG - Sola lettura")
        self.status_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        footer_layout.addWidget(self.status_label)
        
        footer_layout.addStretch()
        
        # Badge
        badge_layout = QHBoxLayout()
        badge_layout.setSpacing(10)
        
        badge_indicator = QLabel("●")
        badge_indicator.setStyleSheet("color: #8B5CF6; font-size: 16px;")
        badge_layout.addWidget(badge_indicator)
        
        badge_label = QLabel("MEMORY VIEWER")
        badge_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        badge_layout.addWidget(badge_label)
        
        footer_layout.addLayout(badge_layout)
        
        return footer_frame
    
    def load_memory(self):
        """Carica la memoria dal database"""
        self.memory_table.setRowCount(0)
        
        if not self.db_path.exists():
            self.status_label.setText("Database non trovato.")
            return
        
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=1.0)
            cursor = conn.cursor()
            
            # Verifica se la tabella esiste
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='rag_memory'
            """)
            if not cursor.fetchone():
                self.status_label.setText("Tabella rag_memory non trovata. Nessuna memoria salvata.")
                conn.close()
                return
            
            # Carica tutte le interazioni
            cursor.execute("""
                SELECT id, timestamp, question, answer, tags
                FROM rag_memory
                ORDER BY timestamp DESC
            """)
            rows = cursor.fetchall()
            
            # Popola la tabella
            for row in rows:
                row_pos = self.memory_table.rowCount()
                self.memory_table.insertRow(row_pos)
                
                # ID
                self.memory_table.setItem(row_pos, 0, QTableWidgetItem(str(row[0])))
                
                # Timestamp (formattato)
                timestamp = row[1]
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamp_formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp_formatted = timestamp
                self.memory_table.setItem(row_pos, 1, QTableWidgetItem(timestamp_formatted))
                
                # Domanda (troncata)
                question = row[2] or ""
                question_display = question[:100] + "..." if len(question) > 100 else question
                self.memory_table.setItem(row_pos, 2, QTableWidgetItem(question_display))
                # Salva domanda completa come tooltip
                if question:
                    self.memory_table.item(row_pos, 2).setToolTip(question)
                
                # Risposta (troncata)
                answer = row[3] or ""
                answer_display = answer[:150] + "..." if len(answer) > 150 else answer
                self.memory_table.setItem(row_pos, 3, QTableWidgetItem(answer_display))
                # Salva risposta completa come tooltip
                if answer:
                    self.memory_table.item(row_pos, 3).setToolTip(answer)
                
                # Tag
                tags = row[4] or ""
                self.memory_table.setItem(row_pos, 4, QTableWidgetItem(tags))
            
            conn.close()
            
            self.status_label.setText(f"Caricate {len(rows)} interazioni dalla memoria.")
            
        except sqlite3.OperationalError:
            self.status_label.setText("Database bloccato. Impossibile caricare la memoria.")
        except Exception as e:
            self.status_label.setText(f"Errore nel caricamento: {str(e)[:50]}")
    
    def on_row_double_clicked(self, index):
        """Gestisce il doppio click su una riga - apre finestra dettagliata"""
        row = index.row()
        
        if row < 0 or row >= self.memory_table.rowCount():
            return
        
        # Ottieni ID dalla prima colonna
        id_item = self.memory_table.item(row, 0)
        if not id_item:
            return
        
        memory_id = int(id_item.text())
        
        # Carica dettagli completi
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=1.0)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, timestamp, question, context, answer, reasoning, tags
                FROM rag_memory
                WHERE id = ?
            """, (memory_id,))
            
            record = cursor.fetchone()
            conn.close()
            
            if record:
                self.show_memory_details(record)
            else:
                QMessageBox.warning(self, "Error", "Record non trovato.")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Errore nel caricamento dettagli:\n{e}")
    
    def show_memory_details(self, record):
        """Mostra finestra dettagliata con tutte le informazioni"""
        # record: (id, timestamp, question, context, answer, reasoning, tags)
        mem_id = record[0]
        mem_timestamp = record[1]
        mem_question = record[2] or ""
        mem_context = record[3] or ""
        mem_answer = record[4] or ""
        mem_reasoning = record[5] or ""
        mem_tags = record[6] or ""
        
        # Formatta timestamp
        try:
            dt = datetime.fromisoformat(mem_timestamp)
            timestamp_formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            timestamp_formatted = mem_timestamp
        
        # Crea finestra di dialogo
        details_dialog = QDialog(self)
        details_dialog.setWindowTitle(f"Dettagli Memoria RAG - ID {mem_id}")
        details_dialog.setMinimumSize(800, 600)
        details_dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
        """)
        
        layout = QVBoxLayout(details_dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header_label = QLabel(f"Interazione #{mem_id} - {timestamp_formatted}")
        header_label.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(header_label)
        
        # Domanda
        question_label = QLabel("Domanda:")
        question_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        layout.addWidget(question_label)
        
        question_text = QTextEdit()
        question_text.setPlainText(mem_question)
        question_text.setReadOnly(True)
        question_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 13px;
                padding: 10px;
            }
        """)
        question_text.setMaximumHeight(100)
        layout.addWidget(question_text)
        
        # Contesto
        context_label = QLabel("Contesto:")
        context_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        layout.addWidget(context_label)
        
        context_text = QTextEdit()
        context_text.setPlainText(mem_context)
        context_text.setReadOnly(True)
        context_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #CCCCCC;
                font-size: 12px;
                padding: 10px;
            }
        """)
        context_text.setMaximumHeight(150)
        layout.addWidget(context_text)
        
        # Risposta
        answer_label = QLabel("Risposta:")
        answer_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        layout.addWidget(answer_label)
        
        answer_text = QTextEdit()
        answer_text.setPlainText(mem_answer)
        answer_text.setReadOnly(True)
        answer_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 13px;
                padding: 10px;
            }
        """)
        layout.addWidget(answer_text, 1)
        
        # Reasoning (se disponibile)
        if mem_reasoning:
            reasoning_label = QLabel("Reasoning:")
            reasoning_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
            layout.addWidget(reasoning_label)
            
            reasoning_text = QTextEdit()
            reasoning_text.setPlainText(mem_reasoning)
            reasoning_text.setReadOnly(True)
            reasoning_text.setStyleSheet("""
                QTextEdit {
                    background-color: #0a0a1a;
                    border: 1px solid #2a2a3a;
                    border-radius: 8px;
                    color: #AAAAAA;
                    font-size: 12px;
                    padding: 10px;
                }
            """)
            reasoning_text.setMaximumHeight(200)
            layout.addWidget(reasoning_text)
        
        # Tag
        if mem_tags:
            tags_label = QLabel(f"Tag: {mem_tags}")
            tags_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
            layout.addWidget(tags_label)
        
        # Pulsante chiudi
        close_button = QPushButton("Chiudi")
        close_button.setMinimumHeight(40)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a;
                color: #FFFFFF;
                border: 1px solid #5a3a7a;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #5a3a7a;
                border: 1px solid #6a4a8a;
            }
            QPushButton:pressed {
                background-color: #3a1a5a;
            }
        """)
        close_button.clicked.connect(details_dialog.close)
        layout.addWidget(close_button)
        
        show_auxiliary_window(details_dialog)
    
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




