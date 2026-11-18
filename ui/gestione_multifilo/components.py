"""
Componenti UI modulari per Gestione Multifilo
Widget riutilizzabili per la sezione Multifilo
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QGroupBox
from PyQt5.QtCore import Qt
from ui.theme.production_theme import production_monospace_field_stylesheet


class MachineStatusWidget(QGroupBox):
    """Widget per visualizzare lo stato della macchina Multifilo"""
    
    def __init__(self, parent=None):
        super().__init__("Stato Macchina", parent)
        self.init_ui()
    
    def init_ui(self):
        """Inizializza il widget"""
        layout = QVBoxLayout(self)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(120)
        self.status_text.setPlaceholderText("Connessa/Sconnessa\nAvanzamento: 0%\nTempo residuo: --\nAllarmi: nessuno")
        self.status_text.setStyleSheet(production_monospace_field_stylesheet())
        layout.addWidget(self.status_text)
    
    def update_status(self, connessa, avanzamento, tempo_residuo, allarmi):
        """Aggiorna lo stato della macchina"""
        connessa_text = "✓ Connessa" if connessa else "✗ Sconnessa"
        avanzamento_text = f"{avanzamento:.1f}%"
        tempo_residuo_text = f"{tempo_residuo}s" if tempo_residuo > 0 else "--"
        
        if allarmi == 0:
            allarmi_text = "Nessun allarme"
        else:
            allarmi_text = f"Allarme: {allarmi}"
        
        text = f"{connessa_text}\n"
        text += f"Avanzamento: {avanzamento_text}\n"
        text += f"Tempo residuo: {tempo_residuo_text}\n"
        text += f"Allarmi: {allarmi_text}"
        
        self.status_text.setPlainText(text)


class FeedbackProduzioneWidget(QGroupBox):
    """Widget per visualizzare il feedback di produzione"""
    
    def __init__(self, parent=None):
        super().__init__("Feedback Produzione", parent)
        self.init_ui()
    
    def init_ui(self):
        """Inizializza il widget"""
        layout = QVBoxLayout(self)
        
        self.feedback_text = QTextEdit()
        self.feedback_text.setReadOnly(True)
        self.feedback_text.setMaximumHeight(120)
        self.feedback_text.setPlaceholderText("Spreco reale: --\nTempo reale: --\nDeviazioni: --")
        self.feedback_text.setStyleSheet(production_monospace_field_stylesheet())
        layout.addWidget(self.feedback_text)
    
    def update_feedback(self, spreco_reale=None, tempo_reale=None, deviazioni=None,
                       velocita_filo=None, tensione_filo=None, pressione_acqua=None,
                       assorbimento_motore=None, metri=None):
        """Aggiorna il feedback di produzione"""
        velocita_text = f"{velocita_filo:.2f} m/s" if velocita_filo is not None else "-- m/s"
        tensione_text = f"{tensione_filo:.2f} N" if tensione_filo is not None else "-- N"
        pressione_text = f"{pressione_acqua:.2f} bar" if pressione_acqua is not None else "-- bar"
        assorbimento_text = f"{assorbimento_motore:.2f} A" if assorbimento_motore is not None else "-- A"
        
        metri_text = f"{metri:.2f} m" if metri is not None else "-- m"
        spreco_text = f"{spreco_reale:.2f} %" if spreco_reale is not None else "-- %"
        deviazioni_text = f"{deviazioni:.2f} mm" if deviazioni is not None else "-- mm"
        
        text = f"Velocità filo: {velocita_text}\n"
        text += f"Tensione filo: {tensione_text}\n"
        text += f"Pressione acqua: {pressione_text}\n"
        text += f"Assorbimento motore: {assorbimento_text}\n"
        text += f"Metri tagliati: {metri_text}\n"
        text += f"Spreco: {spreco_text}\n"
        text += f"Deviazione: {deviazioni_text}"
        
        self.feedback_text.setPlainText(text)
