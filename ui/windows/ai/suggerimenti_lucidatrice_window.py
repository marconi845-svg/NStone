"""
Suggerimenti Lucidatrice Window - Finestra per suggerimenti operativi generati da Gemini
Con validazione tecnica e approvazione operatore
"""

import sys
from ui.common.section_window import SectionDialog, SectionMainWindow
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFrame, QTextEdit,
                             QMessageBox, QGroupBox, QApplication)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from typing import Optional, Any, Dict

# Importa validazione
try:
    from plc.validazione_lucidatrice import ValidazioneLucidatrice, ValidationStatus
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    print("⚠ Modulo validazione_lucidatrice non disponibile")

# Importa RAG Engine
try:
    from llm.rag_engine import RAGEngine
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠ Modulo RAG Engine non disponibile")

# Importa Gemini Service
try:
    from llm.gemini_service import GeminiService
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠ Modulo Gemini Service non disponibile")


class SuggerimentiWorker(QThread):
    """Worker thread per generare suggerimenti con Gemini senza bloccare la UI"""
    result_ready = pyqtSignal(dict)  # Emette il suggerimento quando finisce
    error = pyqtSignal(str)  # Emette errore se qualcosa va storto
    
    def __init__(self, gemini_service, machine_context):
        super().__init__()
        self.gemini_service = gemini_service
        self.machine_context = machine_context
    
    def run(self):
        """Esegue la generazione del suggerimento"""
        try:
            # Costruisci prompt per suggerimento operativo
            prompt = f"""Sei un esperto di macchine Lucidatrice/Calibratrice per finitura superfici marmo.

Analizza lo stato attuale della macchina e genera un suggerimento operativo concreto e sicuro.

[STATO MACCHINA LUCIDATRICE]
{self.machine_context}

Genera un suggerimento operativo che:
1. Identifica un problema o opportunità di miglioramento
2. Propone un'azione concreta e sicura
3. Spiega il beneficio atteso
4. Indica i parametri da modificare (se applicabile)

Formato risposta:
[AZIONE]
Tipo azione (es. "set_parameter", "start", "stop", "optimize")

[PARAMETRO]
Nome parametro da modificare (se applicabile, altrimenti "N/A")

[VALORE]
Valore proposto (se applicabile, altrimenti "N/A")

[DESCRIZIONE]
Descrizione dettagliata del suggerimento, problema identificato, azione proposta, beneficio atteso.

[RAGIONAMENTO]
Spiegazione del perché questo suggerimento è appropriato per lo stato attuale.

Mantieni un tono tecnico e professionale. Proponi solo azioni sicure e validate."""
            
            # Genera suggerimento con Gemini
            response = self.gemini_service.send_message(prompt)
            
            # Estrai informazioni strutturate dalla risposta
            suggerimento = self._parse_suggerimento(response)
            
            self.result_ready.emit(suggerimento)
        except Exception as e:
            self.error.emit(str(e))
    
    def _parse_suggerimento(self, response: str) -> Dict[str, Any]:
        """Estrae informazioni strutturate dal suggerimento di Gemini"""
        suggerimento = {
            "raw_response": response,
            "action": "N/A",
            "parameter": "N/A",
            "value": None,
            "description": response,
            "reasoning": "",
        }
        
        # Estrai sezioni dalla risposta
        lines = response.split('\n')
        current_section = None
        description_parts = []
        reasoning_parts = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('[AZIONE]'):
                current_section = 'action'
            elif line.startswith('[PARAMETRO]'):
                current_section = 'parameter'
            elif line.startswith('[VALORE]'):
                current_section = 'value'
            elif line.startswith('[DESCRIZIONE]'):
                current_section = 'description'
            elif line.startswith('[RAGIONAMENTO]'):
                current_section = 'reasoning'
            elif line and current_section:
                if current_section == 'action':
                    suggerimento['action'] = line.lower()
                elif current_section == 'parameter':
                    suggerimento['parameter'] = line
                elif current_section == 'value':
                    try:
                        suggerimento['value'] = float(line)
                    except ValueError:
                        suggerimento['value'] = line
                elif current_section == 'description':
                    description_parts.append(line)
                elif current_section == 'reasoning':
                    reasoning_parts.append(line)
        
        if description_parts:
            suggerimento['description'] = '\n'.join(description_parts)
        if reasoning_parts:
            suggerimento['reasoning'] = '\n'.join(reasoning_parts)
        
        return suggerimento


class SuggerimentiLucidatriceWindow(SectionDialog):
    """
    Finestra per suggerimenti operativi Lucidatrice/Calibratrice
    Con validazione tecnica e approvazione operatore
    """
    
    def __init__(self, machine_status: Optional[Any] = None, 
                 rag_engine: Optional[RAGEngine] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💡 Operational Insights — Polisher")
        self.setMinimumSize(1000, 700)
        # Storage
        self.machine_status = machine_status
        self.rag_engine = rag_engine
        self.current_suggerimento = None
        self.validation_result = None
        
        # Inizializza validazione
        if VALIDATION_AVAILABLE:
            self.validator = ValidazioneLucidatrice()
        else:
            self.validator = None
        
        # Inizializza Gemini Service
        if GEMINI_AVAILABLE:
            self.gemini_service = GeminiService()
        else:
            self.gemini_service = None
        
        # Worker thread
        self.suggestions_worker = None
        
        # Inizializza UI
        self.init_ui()
        self.apply_stylesheet()
        
        # Genera suggerimento automaticamente all'apertura
        if self.gemini_service:
            self.generate_suggestion()
    
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Area suggerimento
        suggestion_group = self.create_suggestion_area()
        main_layout.addWidget(suggestion_group, 1)
        
        # Area validazione
        validation_group = self.create_validation_area()
        main_layout.addWidget(validation_group)
        
        # Area approvazione
        approval_group = self.create_approval_area()
        main_layout.addWidget(approval_group)
        
        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)
    
    def create_header(self):
        """Crea l'header della finestra"""
        header = QFrame()
        header.setFixedHeight(60)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(15, 10, 15, 10)
        
        title = QLabel("💡 Suggerimenti Operativi — Lucidatrice/Calibratrice")
        title.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 20px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(title)
        
        return header
    
    def create_suggestion_area(self):
        """Crea l'area per il suggerimento generato"""
        group = QGroupBox("Suggerimento Generato da Gemini")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        self.suggestion_text = QTextEdit()
        self.suggestion_text.setReadOnly(True)
        self.suggestion_text.setPlaceholderText("Generazione suggerimento in corso...")
        self.suggestion_text.setMinimumHeight(200)
        self.suggestion_text.setStyleSheet("""
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
        layout.addWidget(self.suggestion_text)
        
        # Pulsante rigenera
        button_layout = QHBoxLayout()
        self.regenerate_button = QPushButton("🔄 Rigenera Suggerimento")
        self.regenerate_button.setStyleSheet("""
            QPushButton {
                background-color: #2a1a3a;
                border: 1px solid #4a3a5a;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3a2a4a;
            }
        """)
        self.regenerate_button.clicked.connect(self.generate_suggestion)
        button_layout.addWidget(self.regenerate_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group
    
    def create_validation_area(self):
        """Crea l'area per la validazione tecnica"""
        group = QGroupBox("Validazione Tecnica")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Stato validazione
        status_layout = QHBoxLayout()
        self.validation_status_label = QLabel("Stato: In attesa")
        self.validation_status_label.setStyleSheet("color: #FFD93D; font-size: 14px; font-weight: bold;")
        status_layout.addWidget(self.validation_status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # Dettagli validazione
        self.validation_text = QTextEdit()
        self.validation_text.setReadOnly(True)
        self.validation_text.setPlaceholderText("La validazione apparirà qui dopo la generazione del suggerimento...")
        self.validation_text.setMaximumHeight(150)
        self.validation_text.setStyleSheet("""
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
        layout.addWidget(self.validation_text)
        
        return group
    
    def create_approval_area(self):
        """Crea l'area per l'approvazione operatore"""
        group = QGroupBox("Approvazione Operatore")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Pulsanti
        button_layout = QHBoxLayout()
        
        self.approve_button = QPushButton("✅ APPROVA")
        self.approve_button.setEnabled(False)
        self.approve_button.setStyleSheet("""
            QPushButton {
                background-color: #51CF66;
                border: 1px solid #6FD980;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6FD980;
            }
            QPushButton:disabled {
                background-color: #1a1a2a;
                color: #666666;
            }
        """)
        self.approve_button.clicked.connect(self.on_approve)
        button_layout.addWidget(self.approve_button)
        
        self.reject_button = QPushButton("❌ RIFIUTA")
        self.reject_button.setStyleSheet("""
            QPushButton {
                background-color: #FF6B6B;
                border: 1px solid #FF8E8E;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FF8E8E;
            }
        """)
        self.reject_button.clicked.connect(self.on_reject)
        button_layout.addWidget(self.reject_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group
    
    def create_footer(self):
        """Crea il footer con informazioni"""
        footer = QFrame()
        footer.setFixedHeight(40)
        footer.setStyleSheet("""
            QFrame {
                background-color: #1a1a2a;
                border-top: 1px solid #3a3a4a;
            }
        """)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(15, 5, 15, 5)
        
        info_label = QLabel("⚠️ I suggerimenti richiedono sempre approvazione operatore. Nessun comando viene eseguito automaticamente.")
        info_label.setStyleSheet("color: #FFD93D; font-size: 11px;")
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        return footer
    
    def generate_suggestion(self):
        """Genera un nuovo suggerimento con Gemini"""
        if not self.gemini_service:
            QMessageBox.warning(
                self,
                "Gemini non disponibile",
                "Il servizio Gemini non è disponibile."
            )
            return
        
        # Disabilita pulsanti
        self.regenerate_button.setEnabled(False)
        self.approve_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        
        # Pulisci aree
        self.suggestion_text.clear()
        self.validation_text.clear()
        self.validation_status_label.setText("Stato: Generazione in corso...")
        self.validation_status_label.setStyleSheet("color: #FFD93D; font-size: 14px; font-weight: bold;")
        
        # Costruisci contesto macchina
        machine_context = self.build_machine_context()
        
        # Crea worker thread
        self.suggestions_worker = SuggerimentiWorker(
            self.gemini_service,
            machine_context
        )
        self.suggestions_worker.result_ready.connect(self.on_suggestion_generated)
        self.suggestions_worker.error.connect(self.on_suggestion_error)
        self.suggestions_worker.start()
    
    def build_machine_context(self) -> str:
        """Costruisce il contesto macchina per Gemini"""
        if self.machine_status is None:
            return "[STATO MACCHINA]\nNessun dato macchina disponibile."
        
        status = self.machine_status
        context_parts = ["[STATO MACCHINA LUCIDATRICE]"]
        context_parts.append("")
        
        context_parts.append(f"Stato macchina: {getattr(status, 'stato_macchina', 'N/A')}")
        context_parts.append(f"Velocità nastro: {getattr(status, 'velocita_nastro', 0.0):.2f} m/min")
        context_parts.append(f"Pressione teste: {getattr(status, 'pressione_teste', 0.0):.2f} bar")
        context_parts.append(f"Temperatura motori: {getattr(status, 'temperatura_motori', 0.0):.2f} °C")
        context_parts.append(f"Consumo acqua: {getattr(status, 'consumo_acqua', 0.0):.2f} L/h")
        context_parts.append(f"Metri lavorati: {getattr(status, 'metri_lavorati', 0.0):.2f} m")
        context_parts.append(f"Produzione ora: {getattr(status, 'produzione_ora', 0.0):.2f} m/h")
        context_parts.append(f"Qualità superficie: {getattr(status, 'qualita_superficie', 'N/A')}")
        context_parts.append(f"Contatore pezzi: {getattr(status, 'contatore_pezzi', 0)}")
        context_parts.append(f"Allarmi: {getattr(status, 'allarmi', 0) if getattr(status, 'allarmi', 0) > 0 else 'Nessuno'}")
        
        return "\n".join(context_parts)
    
    def on_suggestion_generated(self, suggerimento: Dict[str, Any]):
        """Callback quando il suggerimento è generato"""
        self.current_suggerimento = suggerimento
        
        # Mostra suggerimento
        suggestion_display = f"""[AZIONE]
{suggerimento.get('action', 'N/A')}

[PARAMETRO]
{suggerimento.get('parameter', 'N/A')}

[VALORE]
{suggerimento.get('value', 'N/A')}

[DESCRIZIONE]
{suggerimento.get('description', '')}

[RAGIONAMENTO]
{suggerimento.get('reasoning', '')}
"""
        self.suggestion_text.setPlainText(suggestion_display)
        
        # Valida suggerimento
        if self.validator:
            self.validation_result = self.validator.validate_suggerimento(
                suggerimento,
                self.machine_status
            )
            self.update_validation_display()
        else:
            self.validation_status_label.setText("Stato: Validazione non disponibile")
            self.validation_status_label.setStyleSheet("color: #FF6B6B; font-size: 14px; font-weight: bold;")
        
        # Riabilita pulsanti
        self.regenerate_button.setEnabled(True)
        self.reject_button.setEnabled(True)
    
    def update_validation_display(self):
        """Aggiorna la visualizzazione della validazione"""
        if not self.validation_result:
            return
        
        status = self.validation_result.get("status", "Waiting")
        valid = self.validation_result.get("valid", False)
        motivation = self.validation_result.get("motivation", "")
        warnings = self.validation_result.get("warnings", [])
        errors = self.validation_result.get("errors", [])
        
        # Aggiorna stato
        if status == "Validato":
            self.validation_status_label.setText("Stato: ✅ Validato")
            self.validation_status_label.setStyleSheet("color: #51CF66; font-size: 14px; font-weight: bold;")
            self.approve_button.setEnabled(True)
        elif status == "Non valido":
            self.validation_status_label.setText("Stato: ❌ Non valido")
            self.validation_status_label.setStyleSheet("color: #FF6B6B; font-size: 14px; font-weight: bold;")
            self.approve_button.setEnabled(False)
        elif status == "Avviso":
            self.validation_status_label.setText("Stato: ⚠️ Avviso")
            self.validation_status_label.setStyleSheet("color: #FFD93D; font-size: 14px; font-weight: bold;")
            self.approve_button.setEnabled(True)  # Permetti approvazione con avviso
        else:
            self.validation_status_label.setText("Stato: In attesa")
            self.validation_status_label.setStyleSheet("color: #FFD93D; font-size: 14px; font-weight: bold;")
            self.approve_button.setEnabled(False)
        
        # Costruisci testo validazione
        validation_text_parts = [f"Motivazione: {motivation}", ""]
        
        if errors:
            validation_text_parts.append("❌ ERRORI:")
            for error in errors:
                validation_text_parts.append(f"  - {error}")
            validation_text_parts.append("")
        
        if warnings:
            validation_text_parts.append("⚠️ AVVISI:")
            for warning in warnings:
                validation_text_parts.append(f"  - {warning}")
            validation_text_parts.append("")
        
        if not errors and not warnings:
            validation_text_parts.append("✅ Nessun problema rilevato. Suggerimento valido.")
        
        self.validation_text.setPlainText("\n".join(validation_text_parts))
    
    def on_suggestion_error(self, error_msg: str):
        """Callback quando si verifica un errore"""
        self.suggestion_text.setPlainText(f"Errore nella generazione del suggerimento:\n{error_msg}")
        self.validation_status_label.setText("Stato: Errore")
        self.validation_status_label.setStyleSheet("color: #FF6B6B; font-size: 14px; font-weight: bold;")
        
        self.regenerate_button.setEnabled(True)
        self.approve_button.setEnabled(False)
    
    def on_approve(self):
        """Gestisce l'approvazione del suggerimento"""
        if not self.current_suggerimento:
            return
        
        if not self.validation_result or not self.validation_result.get("valid", False):
            QMessageBox.warning(
                self,
                "Suggerimento non valido",
                "Non è possibile approvare un suggerimento non valido."
            )
            return
        
        # Conferma operatore
        reply = QMessageBox.question(
            self,
            "Conferma Approvazione",
            f"Sei sicuro di voler approvare questo suggerimento?\n\n"
            f"Azione: {self.current_suggerimento.get('action', 'N/A')}\n"
            f"Parametro: {self.current_suggerimento.get('parameter', 'N/A')}\n"
            f"Valore: {self.current_suggerimento.get('value', 'N/A')}\n\n"
            f"⚠️ ATTENZIONE: Il comando verrà inviato al PLC solo se previsto.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Salva interazione in memoria evolutiva
            if self.rag_engine:
                try:
                    self.rag_engine.save_interaction(
                        question=f"[SUGGERIMENTO APPROVATO] {self.current_suggerimento.get('description', '')}",
                        context=self.build_machine_context(),
                        answer=f"Azione approvata: {self.current_suggerimento.get('action', 'N/A')}",
                        reasoning=f"Validazione: {self.validation_result.get('motivation', '')}",
                        tags="lucidatrice,suggerimenti,approvato"
                    )
                except Exception as e:
                    print(f"Errore salvataggio memoria: {e}")
            
            try:
                from core.action_executor import process_operator_approval

                result = process_operator_approval(
                    "lucidatrice",
                    self.current_suggerimento,
                    parent_window=self.parent(),
                )
                QMessageBox.information(
                    self,
                    "Suggerimento Approvato",
                    f"{result.message}\n\n"
                    f"ID azione in coda: {result.action_id or '—'}",
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Policy / PLC",
                    f"Suggerimento approvato ma esecuzione non completata:\n{e}",
                )

            self.accept()
    
    def on_reject(self):
        """Gestisce il rifiuto del suggerimento"""
        if not self.current_suggerimento:
            return
        
        # Salva interazione in memoria evolutiva
        if self.rag_engine:
            try:
                self.rag_engine.save_interaction(
                    question=f"[SUGGERIMENTO RIFIUTATO] {self.current_suggerimento.get('description', '')}",
                    context=self.build_machine_context(),
                    answer="Suggerimento rifiutato dall'operatore",
                    reasoning=f"Motivo: {self.validation_result.get('motivation', 'N/A') if self.validation_result else 'N/A'}",
                    tags="lucidatrice,suggerimenti,rifiutato"
                )
            except Exception as e:
                print(f"Errore salvataggio memoria: {e}")
        
        QMessageBox.information(
            self,
            "Suggerimento Rifiutato",
            "Il suggerimento è stato rifiutato. Nessuna azione è stata eseguita."
        )
        
        # Chiudi finestra
        self.reject()
    
    def apply_stylesheet(self):
        """Applica lo stylesheet alla finestra"""
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2a, stop:0.5 #2a2a3a, stop:1 #1a1a2a);
            }
            QGroupBox {
                background-color: #1a1a2a;
                border: 2px solid #3a3a4a;
                border-radius: 8px;
                padding: 15px;
                margin-top: 10px;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: #1a1a2a;
            }
            QLabel {
                color: #FFFFFF;
            }
        """)
    
    def closeEvent(self, event):
        """Pulizia quando la finestra viene chiusa"""
        if self.suggestions_worker and self.suggestions_worker.isRunning():
            self.suggestions_worker.terminate()
            self.suggestions_worker.wait()
        super().closeEvent(event)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = SuggerimentiLucidatriceWindow()
    window.show()
    sys.exit(app.exec_())




