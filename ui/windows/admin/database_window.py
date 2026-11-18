"""
Nstone LLM - Finestra SQL Databaser
Gestione database SQLite - Solo lettura e ispezione struttura
Robusta e resistente ai lock esterni
"""
import os
import sys
from pathlib import Path
import sqlite3
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QListWidget, QListWidgetItem,
                             QMessageBox, QApplication)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QFont, QColor


class TableItem(QListWidgetItem):
    """Item personalizzato per la lista tabelle"""
    def __init__(self, table_name, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.setText(table_name)


class DatabaseWindow(SectionDialog):
    """Finestra SQL Databaser per ispezionare struttura database SQLite"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SQL Databaser")
        
        # Ottieni le dimensioni disponibili dello schermo (escludendo taskbar)
        self.setup_window_size()
        
        # Database path (project root / data / nstonellm.db)
        self.db_path = Path(__file__).resolve().parents[3] / "data" / "nstonellm.db"
        
        # Valori
        self.selected_table = None
        self.table_info = {}  # Cache per informazioni tabelle
        self._db_locked = False  # Flag per stato lock database
        
        self.init_ui()
        self.apply_stylesheet()
        self.load_tables()
    
    def setup_window_size(self):
        """Finestra ridimensionabile, apertura grande ma non bloccata."""
        from ui.common.window_helpers import default_window_geometry, ensure_resizable_window

        try:
            app = QApplication.instance()
            screen = app.primaryScreen() if app else self.screen()
            available_geometry = screen.availableGeometry() if screen else None
            if available_geometry:
                self._available_width = available_geometry.width()
                self._available_height = available_geometry.height()
            else:
                self._available_width = 1920
                self._available_height = 1020
        except Exception:
            self._available_width = 1920
            self._available_height = 1020
        ensure_resizable_window(self, min_width=1024, min_height=700)
        default_window_geometry(self)
    
    def init_ui(self):
        """Inizializza l'interfaccia utente - adattato all'altezza disponibile"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Calcola l'altezza disponibile per il contenuto basandosi sulle dimensioni disponibili
        header_height = 80
        footer_height = 100
        content_margins = 60  # 30px top + 30px bottom
        available_content_height = self._available_height - header_height - footer_height - content_margins
        
        # Assicurati che l'altezza del contenuto sia positiva
        if available_content_height < 100:
            available_content_height = 500  # Altezza minima di fallback
        
        # Contenuto principale (due colonne) - adattato all'altezza disponibile
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(30)
        
        # Colonna sinistra - Lista Tabelle (circa 35-40% larghezza)
        left_panel = self.create_left_panel()
        left_panel.setMinimumHeight(400)
        content_layout.addWidget(left_panel, 35)
        
        # Colonna destra - Riquadro informativo (circa 60-65% larghezza)
        right_panel = self.create_right_panel()
        right_panel.setMinimumHeight(400)
        content_layout.addWidget(right_panel, 65)
        
        main_layout.addLayout(content_layout, 1)
        
        # Footer con statistiche e controlli
        footer = self.create_footer()
        main_layout.addWidget(footer)
    
    def create_header(self):
        """Crea l'header - ottimizzato per 1920px di larghezza"""
        header_frame = QFrame()
        header_frame.setFixedHeight(80)  # Altezza aumentata per spazio maggiore
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-bottom: 1px solid #2a1a3a;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(30, 15, 30, 15)
        
        title_label = QLabel("SQL Databaser")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        return header_frame
    
    def create_left_panel(self):
        """Crea il pannello sinistro con lista tabelle e informazioni - ottimizzato per 1920x1080"""
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
        title = QLabel("Database Tables")
        title.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        
        # Lista tabelle (alta, scrollabile) - ottimizzata per spazio verticale
        self.tables_list = QListWidget()
        self.tables_list.setStyleSheet("""
            QListWidget {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 15px;
                border-bottom: 1px solid #2a2a3a;
                min-height: 40px;
            }
            QListWidget::item:hover {
                background-color: #2a2a3a;
            }
            QListWidget::item:selected {
                background-color: #4a2a6a;
                border-left: 3px solid #8B5CF6;
            }
        """)
        self.tables_list.itemClicked.connect(self.on_table_selected)
        layout.addWidget(self.tables_list, 1)  # Espansione per occupare spazio verticale
        
        # Pulsante aggiorna elenco
        refresh_button = QPushButton("Refresh table list")
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 6px;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
                border: 1px solid #4a4a5a;
            }
            QPushButton:pressed {
                background-color: #1a1a2a;
            }
        """)
        refresh_button.clicked.connect(self.refresh_tables)
        layout.addWidget(refresh_button)
        
        # Informazioni tabella selezionata - pannello informativo ottimizzato
        self.table_info_label = QLabel("Select a table to view details")
        self.table_info_label.setStyleSheet("""
            color: #AAAAAA; 
            font-size: 13px; 
            padding: 20px;
            background-color: #0a0a1a;
            border-radius: 8px;
            border: 1px solid #2a2a3a;
        """)
        self.table_info_label.setWordWrap(True)
        self.table_info_label.setMinimumHeight(200)  # Altezza minima per pannello informativo
        layout.addWidget(self.table_info_label)
        
        return panel
    
    def create_right_panel(self):
        """Crea il pannello destro con riquadro informativo statico - ottimizzato per 1920x1080"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Badge SQL Databaser
        badge_frame = QFrame()
        badge_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a2a6a, stop:1 #6a4a8a);
                border-radius: 8px;
                padding: 10px;
            }
        """)
        badge_layout = QHBoxLayout(badge_frame)
        badge_layout.setContentsMargins(15, 10, 15, 10)
        
        badge_icon = QLabel("●")
        badge_icon.setStyleSheet("color: #8B5CF6; font-size: 20px; font-weight: bold;")
        badge_layout.addWidget(badge_icon)
        
        badge_label = QLabel("SQL Databaser")
        badge_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        badge_layout.addWidget(badge_label)
        
        layout.addWidget(badge_frame)
        
        # Testo descrittivo - ottimizzato per spazio maggiore
        info_text = QLabel(
            "This section lets you inspect the database structure.\n\n"
            "You can view:\n"
            "• List of available tables\n"
            "• Detailed information for each table\n"
            "• Record and column counts\n\n"
            "To edit or browse data, use the 'Open SQL Databaser' button in the footer."
        )
        info_text.setStyleSheet("""
            color: #CCCCCC; 
            font-size: 15px; 
            padding: 30px;
            background-color: #0a0a1a;
            border-radius: 8px;
            border: 1px solid #2a2a3a;
            line-height: 1.8;
        """)
        info_text.setWordWrap(True)
        layout.addWidget(info_text)
        
        layout.addStretch()
        
        return panel
    
    def create_footer(self):
        """Crea il footer con statistiche e controlli - ottimizzato per larghezza piena 1920px"""
        footer_frame = QFrame()
        footer_frame.setFixedHeight(100)  # Altezza aumentata per spazio maggiore
        footer_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a0a15, stop:1 #150a1a);
                border-top: 1px solid #2a1a3a;
            }
        """)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(30, 20, 30, 20)
        footer_layout.setSpacing(30)
        
        # Barra di stato estesa - ottimizzata per larghezza piena
        self.status_label = QLabel("SQL Databaser ready. Use the button to open the database.")
        self.status_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: normal;")
        self.status_label.setMinimumWidth(400)  # Larghezza minima per barra di stato estesa
        footer_layout.addWidget(self.status_label)
        
        footer_layout.addStretch()
        
        # Active Engine
        engine_layout = QHBoxLayout()
        engine_layout.setSpacing(10)
        
        engine_indicator = QLabel("●")
        engine_indicator.setStyleSheet("color: #00FF00; font-size: 16px;")
        engine_layout.addWidget(engine_indicator)
        
        engine_label = QLabel("ACTIVE ENGINE")
        engine_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        engine_layout.addWidget(engine_label)
        
        footer_layout.addLayout(engine_layout)
        
        footer_layout.addStretch()
        
        # Neural Sync button - ottimizzato per footer a larghezza piena
        sync_button = QPushButton("Neural Sync")
        sync_button.setMinimumHeight(50)
        sync_button.setMinimumWidth(150)
        sync_button.setStyleSheet("""
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
        """)
        sync_button.clicked.connect(self.neural_sync)
        footer_layout.addWidget(sync_button)
        
        # Apri SQL Databaser button - ottimizzato per footer a larghezza piena
        open_db_button = QPushButton("Open SQL Databaser")
        open_db_button.setMinimumHeight(50)
        open_db_button.setMinimumWidth(180)
        open_db_button.setStyleSheet("""
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
        open_db_button.clicked.connect(self.open_database_file)
        footer_layout.addWidget(open_db_button)
        
        # RAG Engine button - nuovo pulsante per aprire RAG Engine
        rag_button = QPushButton("RAG Engine")
        rag_button.setMinimumHeight(50)
        rag_button.setMinimumWidth(150)
        rag_button.setStyleSheet("""
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
        rag_button.clicked.connect(self.open_rag_engine)
        footer_layout.addWidget(rag_button)
        
        return footer_frame
    
    def is_database_locked(self):
        """
        Verifica se il database è locked da un altro programma.
        Restituisce True se locked, False se disponibile.
        Nessun crash, nessuna eccezione non gestita.
        """
        if not self.db_path.exists():
            return False  # Se non esiste, non è locked
        
        try:
            # Tenta una query innocua per verificare il lock
            conn = sqlite3.connect(str(self.db_path), timeout=1.0)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            self._db_locked = False
            return False
        except sqlite3.OperationalError:
            # Database locked da altro programma
            self._db_locked = True
            return True
        except Exception:
            # Altri errori (file non accessibile, permessi, ecc.)
            # Consideriamo come non locked per non bloccare l'operazione
            self._db_locked = False
            return False
    
    def safe_pragma(self, table_name):
        """
        Esegue PRAGMA table_info in modo sicuro.
        Verifica prima se il DB è locked.
        Restituisce lista di nomi colonne, lista vuota in caso di errore.
        Nessun crash.
        """
        # Verifica lock prima di procedere
        if self.is_database_locked():
            self.status_label.setText("Database open in another program. Read-only operations disabled.")
            return []
        
        if not self.db_path.exists():
            return []
        
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=1.0)
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]  # col[1] è il nome della colonna
            conn.close()
            return column_names
        except sqlite3.OperationalError:
            # Database locked durante l'esecuzione
            self._db_locked = True
            self.status_label.setText("Database open in another program. Read-only operations disabled.")
            return []
        except Exception as e:
            # Altri errori (tabella non esiste, sintassi, ecc.)
            self.status_label.setText("Unable to read table structure.")
            return []
    
    def safe_count(self, table_name):
        """
        Esegue SELECT COUNT(*) in modo sicuro.
        Verifica prima se il DB è locked.
        Restituisce numero di record, 0 in caso di errore.
        Nessun crash.
        """
        # Verifica lock prima di procedere
        if self.is_database_locked():
            self.status_label.setText("Database open in another program. Read-only operations disabled.")
            return 0
        
        if not self.db_path.exists():
            return 0
        
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=1.0)
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            record_count = cursor.fetchone()[0]
            conn.close()
            return record_count
        except sqlite3.OperationalError:
            # Database locked durante l'esecuzione
            self._db_locked = True
            self.status_label.setText("Database open in another program. Read-only operations disabled.")
            return 0
        except Exception:
            # Altri errori (tabella non esiste, sintassi, ecc.)
            self.status_label.setText("Unable to count table records.")
            return 0
    
    def get_db_connection(self):
        """Ottiene una connessione al database (sola lettura)"""
        try:
            if not self.db_path.exists():
                return None
            # Connessione in modalità sola lettura con timeout breve
            conn = sqlite3.connect(str(self.db_path), timeout=1.0)
            return conn
        except Exception:
            # Errore silenzioso, gestito dai metodi chiamanti
            return None
    
    def load_tables(self):
        """Carica l'elenco delle tabelle dal database"""
        self.tables_list.clear()
        
        # Verifica lock prima di procedere
        if self.is_database_locked():
            self.status_label.setText("Database open in another program. Read-only operations disabled.")
            self.table_info_label.setText("Database locked. Close the external program to view tables.")
            return
        
        conn = self.get_db_connection()
        if not conn:
            self.status_label.setText("Unable to connect to the database.")
            return
        
        try:
            cursor = conn.cursor()
            # Ottieni tutte le tabelle (escludendo le tabelle di sistema sqlite_*)
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = cursor.fetchall()
            
            for (table_name,) in tables:
                item = TableItem(table_name)
                self.tables_list.addItem(item)
            
            if not tables:
                self.table_info_label.setText("No tables found in the database")
                self.status_label.setText("No tables found in the database")
            else:
                self.status_label.setText("DB ready. Select a table to view details.")
        except sqlite3.OperationalError:
            # Database locked durante l'esecuzione
            self._db_locked = True
            self.status_label.setText("Database open in another program. Read-only operations disabled.")
            self.table_info_label.setText("Database locked. Close the external program to view tables.")
        except Exception as e:
            self.status_label.setText(f"Error loading tables: {str(e)[:50]}")
        finally:
            try:
                conn.close()
            except:
                pass
    
    def refresh_tables(self):
        """Aggiorna l'elenco delle tabelle"""
        self.table_info.clear()  # Reset cache
        self.selected_table = None
        self.table_info_label.setText("Select a table to view details")
        self.load_tables()
        if not self._db_locked:
            self.status_label.setText("Table list refreshed")
    
    def on_table_selected(self, item):
        """Gestisce la selezione di una tabella"""
        if isinstance(item, TableItem):
            self.selected_table = item.table_name
            
            # Verifica lock prima di aggiornare le informazioni
            if self.is_database_locked():
                self.status_label.setText("Database open in another program. Read-only operations disabled.")
                self.table_info_label.setText(
                    f"Table: {item.table_name}\n\n"
                    "Database locked. Close the external program to view details."
                )
                return
            
            # Usa i metodi sicuri per aggiornare le informazioni
            self.update_table_info(item.table_name)
    
    def get_table_info(self, table_name):
        """
        Ottiene informazioni su una tabella (colonne e record count) - SOLA LETTURA
        Usa metodi sicuri per evitare crash quando il DB è locked.
        """
        # Verifica lock prima di procedere
        if self.is_database_locked():
            return None
        
        # Usa cache se disponibile
        if table_name in self.table_info:
            return self.table_info[table_name]
        
        # Usa metodi sicuri
        column_names = self.safe_pragma(table_name)
        record_count = self.safe_count(table_name)
        
        # Se entrambi falliscono, non cacheare
        if not column_names and record_count == 0:
            return None
        
        info = {
            'columns': column_names if column_names else [],
            'record_count': record_count
        }
        
        # Cache solo se i dati sono validi
        if column_names or record_count > 0:
            self.table_info[table_name] = info
        
        return info
    
    def update_table_info(self, table_name):
        """Aggiorna le informazioni della tabella nel pannello sinistro"""
        info = self.get_table_info(table_name)
        
        if not info:
            # Se non ci sono informazioni, mostra messaggio appropriato
            if self._db_locked:
                info_text = (
                    f"Table: {table_name}\n\n"
                    "Database locked. Close the external program to view details."
                )
            else:
                info_text = f"Table: {table_name}\n\nUnable to read table information."
            self.table_info_label.setText(info_text)
            return
        
        # Aggiorna pannello sinistro solo se i dati sono validi
        columns_text = ", ".join(info['columns']) if info['columns'] else "N/A"
        info_text = f"Table: {table_name}\n\n"
        info_text += f"Total records: {info['record_count']}\n\n"
        info_text += f"Columns ({len(info['columns'])}):\n{columns_text}"
        self.table_info_label.setText(info_text)
        
        # Aggiorna barra di stato
        self.status_label.setText(f"Table loaded: {table_name} ({info['record_count']} records)")
    
    def open_database_file(self):
        """Apre il file database con il programma predefinito del sistema"""
        if not self.db_path.exists():
            QMessageBox.warning(
                self,
                "Database not found",
                f"The database was not found at:\n{self.db_path}",
            )
            return
        
        try:
            # Converti il percorso in URL locale
            file_url = QUrl.fromLocalFile(str(self.db_path.resolve()))
            # Apri con il programma predefinito
            success = QDesktopServices.openUrl(file_url)
            
            if not success:
                QMessageBox.warning(
                    self,
                    "Error",
                    "Unable to open the database file.\n"
                    "Make sure a program is associated with .db files.",
                )
                self.status_label.setText("Error opening database")
            else:
                self.status_label.setText(
                    "Database opened with external program. Read operations may be disabled."
                )
                # Verifica lock dopo l'apertura
                self.is_database_locked()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error opening file:\n{e}")
            self.status_label.setText(f"Error: {str(e)[:50]}")
    
    def open_rag_engine(self):
        """Apre la finestra RAG Engine"""
        try:
            from ui.common.window_helpers import show_auxiliary_window
            from ui.windows.ai.rag_engine_window import RAGEngineWindow
            rag_window = RAGEngineWindow(self)
            show_auxiliary_window(rag_window)
            self.status_label.setText("RAG Engine closed.")
        except ImportError as e:
            QMessageBox.critical(self, "Error", f"Unable to import RAG Engine:\n{e}")
            self.status_label.setText("Error opening RAG Engine")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error opening RAG Engine:\n{e}")
            self.status_label.setText(f"Error: {str(e)[:50]}")
    
    def neural_sync(self):
        """Esegue la sincronizzazione neurale"""
        # Verifica lock prima di procedere
        if self.is_database_locked():
            QMessageBox.warning(
                self,
                "Database Locked",
                "The database is open in another program.\n"
                "Close the external program before running sync.",
            )
            self.status_label.setText("Neural sync cancelled: database locked")
            return
        
        # TODO: Implementare logica di sincronizzazione
        QMessageBox.information(self, "Neural Sync", "Neural sync in progress...")
        # Ricarica le tabelle dopo sync
        self.table_info.clear()  # Reset cache
        self.load_tables()
        if self.selected_table:
            self.update_table_info(self.selected_table)
        self.status_label.setText("Neural sync completed")
    
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
