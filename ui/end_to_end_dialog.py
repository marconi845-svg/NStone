"""
Dialog per test end-to-end del flusso completo
UI PyQt5 con tema dark e stile moderno
"""
import sys
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QTextEdit, QScrollArea,
                             QWidget, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

# Import del tester
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from services.end_to_end_tester import EndToEndTester


class TestWorker(QThread):
    """Worker thread per eseguire i test senza bloccare l'UI"""
    
    result_ready = pyqtSignal(dict)  # Emette i risultati quando completato
    log_updated = pyqtSignal(str)  # Emette log in tempo reale
    
    def __init__(self, config=None):
        super().__init__()
        self.config = config
        self.tester = None
    
    def run(self):
        """Esegue i test in background"""
        self.tester = EndToEndTester(self.config)
        
        # Reindirizza i log del tester
        original_log = self.tester.log
        def logged_log(message, level="INFO"):
            original_log(message, level)
            self.log_updated.emit(f"[{level}] {message}")
        self.tester.log = logged_log
        
        # Esegui tutti i test
        results = self.tester.run_all_tests()
        self.result_ready.emit(results)


class EndToEndTestDialog(QDialog):
    """
    Dialog per eseguire e visualizzare i risultati dei test end-to-end.
    
    UI moderna con tema dark, mostra lo stato di ogni test e log in tempo reale.
    """
    
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("Test End-to-End - Diagnostica Sistema")
        self.setMinimumSize(900, 700)
        self.config = config or {}
        
        self.test_worker = None
        self.test_results = {}
        
        self.init_ui()
        self.apply_stylesheet()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Titolo
        title_label = QLabel("🔍 Test End-to-End - Diagnostica Sistema")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold;")
        main_layout.addWidget(title_label)
        
        desc_label = QLabel("Verifica il flusso completo: WhatsApp → Meta → Cloud Function → Windows → AI → Offerte → Outlook")
        desc_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        main_layout.addWidget(desc_label)
        
        # Sezione stati test
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setSpacing(10)
        
        status_title = QLabel("Stato Test")
        status_title.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")
        status_layout.addWidget(status_title)
        
        # Etichette di stato per ogni test
        self.status_labels = {}
        test_names = {
            "cloud_function": "1. Cloud Function",
            "windows_listener": "2. Windows Listener",
            "ai_assistant": "3. AI Assistant",
            "offer_generation": "4. Generazione Offerta",
            "outlook": "5. Outlook COM"
        }
        
        for key, name in test_names.items():
            status_row = QHBoxLayout()
            
            label = QLabel(name)
            label.setStyleSheet("color: #CCCCCC; font-size: 12px;")
            label.setMinimumWidth(200)
            status_row.addWidget(label)
            
            status_indicator = QLabel("⏳ In attesa...")
            status_indicator.setStyleSheet("color: #AAAAAA; font-size: 12px;")
            status_row.addWidget(status_indicator)
            
            status_row.addStretch()
            
            status_layout.addLayout(status_row)
            self.status_labels[key] = status_indicator
        
        main_layout.addWidget(status_frame)
        
        # Area log
        log_frame = QFrame()
        log_frame.setStyleSheet("""
            QFrame {
                background-color: #0a0a1a;
                border: 1px solid #2a2a3a;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.setSpacing(5)
        
        log_title = QLabel("Log Test")
        log_title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        log_layout.addWidget(log_title)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #0a0a0a;
                color: #00FF00;
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                padding: 10px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        self.log_text.setMinimumHeight(300)
        log_layout.addWidget(self.log_text)
        
        main_layout.addWidget(log_frame, 1)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("In attesa...")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #2a2a3a;
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
                background-color: #1a1a2a;
                font-weight: bold;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8B5CF6, stop:1 #6B4CD6);
                border-radius: 5px;
            }
        """)
        main_layout.addWidget(self.progress_bar)
        
        # Pulsanti
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.run_button = QPushButton("▶ Esegui Test")
        self.run_button.setMinimumHeight(40)
        self.run_button.setMinimumWidth(150)
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #9B6CF6;
            }
            QPushButton:disabled {
                background-color: #4a4a4a;
                color: #888888;
            }
        """)
        self.run_button.clicked.connect(self.run_tests)
        buttons_layout.addWidget(self.run_button)
        
        close_button = QPushButton("Chiudi")
        close_button.setMinimumHeight(40)
        close_button.setMinimumWidth(120)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: 1px solid #3a3a4a;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
            }
        """)
        close_button.clicked.connect(self.close)
        buttons_layout.addWidget(close_button)
        
        main_layout.addLayout(buttons_layout)
    
    def run_tests(self):
        """Avvia l'esecuzione dei test"""
        # Reset UI
        self.run_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Esecuzione test...")
        self.log_text.clear()
        
        # Reset stati
        for key, indicator in self.status_labels.items():
            indicator.setText("⏳ In attesa...")
            indicator.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        
        self.add_log("=== INIZIO TEST END-TO-END ===")
        self.add_log("Preparazione test...")
        
        # Crea e avvia worker thread
        self.test_worker = TestWorker(self.config)
        self.test_worker.log_updated.connect(self.on_log_updated)
        self.test_worker.result_ready.connect(self.on_tests_finished)
        self.test_worker.start()
        
        # Aggiorna progress bar durante l'esecuzione
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(100)
    
    def on_log_updated(self, message):
        """Gestisce aggiornamenti log in tempo reale"""
        self.add_log(message)
    
    def on_tests_finished(self, results):
        """Gestisce il completamento dei test"""
        self.progress_timer.stop()
        self.progress_bar.setValue(100)
        
        self.test_results = results
        self.update_test_statuses()
        
        # Mostra summary
        summary = results.get("summary", {})
        self.add_log("")
        self.add_log("=== RISULTATI FINALI ===")
        self.add_log(f"Totale test: {summary.get('total', 0)}")
        self.add_log(f"Passati: {summary.get('passed', 0)}")
        self.add_log(f"Falliti: {summary.get('failed', 0)}")
        self.add_log(f"Tasso successo: {summary.get('success_rate', 0):.1f}%")
        
        self.run_button.setEnabled(True)
        self.progress_bar.setFormat("Completato")
    
    def update_test_statuses(self):
        """Aggiorna le etichette di stato in base ai risultati"""
        results = self.test_results.get("results", {})
        
        for key, indicator in self.status_labels.items():
            test_result = results.get(key, {})
            status = test_result.get("status", "UNKNOWN")
            message = test_result.get("message", "")
            
            if status == "OK":
                indicator.setText("✅ OK")
                indicator.setStyleSheet("color: #00FF00; font-size: 12px; font-weight: bold;")
            elif status == "FAIL":
                indicator.setText("❌ FAIL")
                indicator.setStyleSheet("color: #FF6B6B; font-size: 12px; font-weight: bold;")
            else:
                indicator.setText("⏳ In attesa...")
                indicator.setStyleSheet("color: #AAAAAA; font-size: 12px;")
    
    def update_progress(self):
        """Aggiorna la progress bar durante l'esecuzione"""
        if self.progress_bar.value() < 90:
            self.progress_bar.setValue(self.progress_bar.value() + 2)
    
    def add_log(self, message):
        """Aggiunge un messaggio al log"""
        self.log_text.append(message)
        # Auto-scroll
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def apply_stylesheet(self):
        """Applica lo stylesheet con tema dark"""
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a15, stop:0.5 #150a1a, stop:1 #0a0a15);
            }
            QWidget {
                background: transparent;
            }
        """)

