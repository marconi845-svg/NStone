"""
Finestra di dettaglio per una singola richiesta - Versione semplificata
"""
import requests
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QTextEdit, QLineEdit,
                             QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from typing import Optional, Dict


def _http_timeout_for_elabora() -> int:
    """Allinea il timeout HTTP al tempo massimo Ollama in config (+ margine)."""
    try:
        from llm.llm_service import load_llm_config

        ollama_cfg = load_llm_config().get("ollama") or {}
        return int(ollama_cfg.get("timeout_seconds", 180)) + 45
    except Exception:
        return 225


class RequestWorker(QThread):
    """Worker thread per chiamate HTTP asincrone"""
    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, method: str, url: str, timeout: Optional[int] = None):
        super().__init__()
        self.method = method.upper()
        self.url = url
        self.timeout = timeout
    
    def run(self):
        """Esegue la chiamata HTTP nel thread separato"""
        try:
            if self.method == "GET":
                timeout = self.timeout if self.timeout is not None else 10
                response = requests.get(self.url, timeout=timeout)
            elif self.method == "POST":
                timeout = self.timeout if self.timeout is not None else 30
                response = requests.post(self.url, timeout=timeout)
            elif self.method == "DELETE":
                timeout = self.timeout if self.timeout is not None else 10
                response = requests.delete(self.url, timeout=timeout)
            else:
                raise ValueError(f"Metodo HTTP non supportato: {self.method}")
            
            if not response.ok:
                detail = response.text
                try:
                    payload = response.json()
                    if isinstance(payload, dict) and payload.get("detail"):
                        detail = payload["detail"]
                except ValueError:
                    pass
                self.error.emit(f"{response.status_code} — {detail}")
                return
            self.result_ready.emit(response.json())
        except requests.RequestException as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))


class RequestDetailWindow(SectionDialog):
    """Finestra semplificata per visualizzare e gestire i dettagli di una singola richiesta"""
    
    def __init__(self, request_id: str, parent=None):
        super().__init__(parent)
        self.request_id = request_id
        self.base_url = "http://127.0.0.1:8000"
        self.worker: Optional[RequestWorker] = None
        self.request_data: Optional[Dict] = None
        
        self.setWindowTitle("Request Details")
        self.setMinimumSize(600, 500)
        
        self.init_ui()
        self.load_request_data()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente semplificata"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Nome
        nome_label = QLabel("Nome:")
        nome_label.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        layout.addWidget(nome_label)
        self.nome_field = QLineEdit()
        self.nome_field.setReadOnly(True)
        self.nome_field.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.nome_field)
        
        # Email
        email_label = QLabel("Email:")
        email_label.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        layout.addWidget(email_label)
        self.email_field = QLineEdit()
        self.email_field.setReadOnly(True)
        self.email_field.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.email_field)
        
        # Messaggio
        messaggio_label = QLabel("Messaggio:")
        messaggio_label.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        layout.addWidget(messaggio_label)
        self.messaggio_field = QTextEdit()
        self.messaggio_field.setReadOnly(True)
        self.messaggio_field.setMaximumHeight(120)
        self.messaggio_field.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.messaggio_field)
        
        # Pulsanti azioni
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        elaborate_btn = QPushButton("Process with Gemini")
        elaborate_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9B6CF6;
            }
        """)
        elaborate_btn.clicked.connect(self.elaborate_with_gemini)
        buttons_layout.addWidget(elaborate_btn)
        
        delete_btn = QPushButton("Cancella richiesta")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B0000;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #A00000;
            }
        """)
        delete_btn.clicked.connect(self.delete_request)
        buttons_layout.addWidget(delete_btn)
        
        layout.addLayout(buttons_layout)
        
        # Risposta Gemini
        risposta_label = QLabel("Risposta Gemini:")
        risposta_label.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        layout.addWidget(risposta_label)
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("La risposta generata da Gemini apparirà qui...")
        self.response_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2a;
                color: #FFFFFF;
                border: 1px solid #3a2a4a;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.response_text, 1)
        
        # Pulsante Chiudi
        close_btn = QPushButton("Chiudi")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3a;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 10px 30px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a4a;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        # Applica stile scuro
        self.setStyleSheet("""
            QDialog {
                background-color: #0a0a15;
            }
            QLabel {
                color: #FFFFFF;
            }
        """)
    
    def load_request_data(self):
        """Carica i dati della richiesta dal backend"""
        url = f"{self.base_url}/api/get_request?request_id={self.request_id}"
        self.worker = RequestWorker("GET", url)
        self.worker.result_ready.connect(self.on_request_data_loaded)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    def on_request_data_loaded(self, result: Dict):
        """Callback quando i dati della richiesta sono stati caricati"""
        if result.get("success") and result.get("request"):
            self.request_data = result["request"]
            self.nome_field.setText(self.request_data.get("nome", ""))
            self.email_field.setText(self.request_data.get("email", ""))
            self.messaggio_field.setPlainText(self.request_data.get("messaggio", ""))
            
            # Se c'è già una risposta Gemini, mostrala
            if "risposta_gemini" in self.request_data:
                self.response_text.setPlainText(self.request_data["risposta_gemini"])
        else:
            QMessageBox.warning(self, "Error", "Impossibile caricare i dati della richiesta.")
            self.reject()
    
    def on_error(self, error_msg: str):
        """Callback in caso di errore"""
        QMessageBox.critical(self, "Error", f"Errore: {error_msg}")
        self.reject()
    
    def elaborate_with_gemini(self):
        """Elabora la richiesta con il modello LLM configurato (Ollama locale o Gemini)."""
        if not self.request_data:
            QMessageBox.warning(self, "Attenzione", "Dati richiesta non disponibili.")
            return

        wait_sec = _http_timeout_for_elabora()
        self.response_text.setPlainText(
            f"Elaborazione in corso con il modello locale (Qwen/Ollama)…\n"
            f"Attendi fino a ~{wait_sec // 60} min al primo utilizzo."
        )

        url = f"{self.base_url}/api/elabora?request_id={self.request_id}"
        self.worker = RequestWorker("POST", url, timeout=wait_sec)
        self.worker.result_ready.connect(self.on_elaboration_completed)
        self.worker.error.connect(self.on_elaboration_error)
        self.worker.start()
    
    def on_elaboration_completed(self, result: Dict):
        """Callback quando l'elaborazione è completata"""
        if result.get("success") and result.get("reply"):
            self.response_text.setPlainText(result["reply"])
            if self.request_data:
                self.request_data["risposta_gemini"] = result["reply"]
                self.request_data["stato"] = "ELABORATA"
                self.request_data["email_inviata"] = result.get("email_sent", False)

            if result.get("email_sent"):
                QMessageBox.information(
                    self,
                    "Successo",
                    "Richiesta elaborata.\n\nLa risposta è stata inviata al cliente via Gmail.",
                )
            else:
                err = result.get("email_error") or (
                    "Configure Gmail in Advanced Dataset Options → "
                    "Gmail Reply Sending (SMTP) (email + App Password), then Save."
                )
                QMessageBox.warning(
                    self,
                    "Risposta generata",
                    f"Risposta generata, ma l'email al cliente NON è stata inviata.\n\n{err}",
                )
        else:
            QMessageBox.warning(self, "Error", "Impossibile elaborare la richiesta.")
    
    def on_elaboration_error(self, error_msg: str):
        """Callback in caso di errore nell'elaborazione"""
        QMessageBox.critical(self, "Error", f"Errore durante l'elaborazione:\n{error_msg}")
    
    def delete_request(self):
        """Cancella la richiesta"""
        reply = QMessageBox.question(
            self,
            "Confirm deletion",
            "Sei sicuro di voler eliminare questa richiesta?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            url = f"{self.base_url}/api/delete_request?request_id={self.request_id}"
            self.worker = RequestWorker("DELETE", url)
            self.worker.result_ready.connect(self.on_deletion_completed)
            self.worker.error.connect(self.on_deletion_error)
            self.worker.start()
    
    def on_deletion_completed(self, result: Dict):
        """Callback quando la cancellazione è completata"""
        if result.get("success"):
            # Aggiorna la tabella nella finestra principale prima di chiudere
            if self.parent() and hasattr(self.parent(), 'load_messages_from_backend'):
                self.parent().load_messages_from_backend()
            QMessageBox.information(self, "Successo", "Richiesta eliminata con successo!")
            self.accept()  # Chiudi la finestra modale
        else:
            QMessageBox.warning(self, "Error", "Impossibile eliminare la richiesta.")
    
    def on_deletion_error(self, error_msg: str):
        """Callback in caso di errore nella cancellazione"""
        QMessageBox.critical(self, "Error", f"Errore durante l'eliminazione:\n{error_msg}")
    
    def closeEvent(self, event):
        """Gestisce la chiusura della finestra"""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        event.accept()
