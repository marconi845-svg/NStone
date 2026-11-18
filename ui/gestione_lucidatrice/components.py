"""
Componenti UI modulari per Gestione Lucidatrice/Calibratrice
Widget riutilizzabili per la sezione Lucidatrice
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QGroupBox
from PyQt5.QtCore import Qt
from ui.theme.production_theme import production_monospace_field_stylesheet


class LucidatriceStatusWidget(QGroupBox):
    """Widget per visualizzare lo stato della macchina Lucidatrice/Calibratrice"""
    
    def __init__(self, parent=None):
        super().__init__("Stato Macchina", parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        self.status_text.setPlaceholderText(
            "Stato: STOP\n"
            "Velocità nastro: 0.0 m/min\n"
            "Velocità trave: 0.0 mm/s\n"
            "Pressione teste: 0.0 bar\n"
            "Contropressione teste: 0.0 bar\n"
            "Temperatura motori: 0.0 °C\n"
            "Consumo acqua: 0.0 L/min\n"
            "Allarmi: nessuno"
        )
        self.status_text.setStyleSheet(production_monospace_field_stylesheet())
        layout.addWidget(self.status_text)
    
    def update_status(self, stato_macchina=None, velocita_nastro=None, 
                     velocita_trave=None, pressione_teste=None, 
                     contropressione_teste=None, temperatura_motori=None, 
                     consumo_acqua=None, allarmi=None):
        stato_map = {0: "STOP", 1: "RUN", 2: "ALARM", 3: "TESTINE_ERROR", 4: "NASTRO_ERROR"}
        if isinstance(stato_macchina, int) and stato_macchina in stato_map:
            stato_text = stato_map[stato_macchina]
        elif stato_macchina:
            stato_text = str(stato_macchina)
        else:
            stato_text = "STOP"
        
        velocita_nastro_text = f"{velocita_nastro:.2f} m/min" if velocita_nastro is not None else "-- m/min"
        velocita_trave_text = f"{velocita_trave:.2f} mm/s" if velocita_trave is not None else "-- mm/s"
        pressione_text = f"{pressione_teste:.2f} bar" if pressione_teste is not None else "-- bar"
        contropressione_text = f"{contropressione_teste:.2f} bar" if contropressione_teste is not None else "-- bar"
        temperatura_text = f"{temperatura_motori:.1f} °C" if temperatura_motori is not None else "-- °C"
        consumo_text = f"{consumo_acqua:.2f} L/min" if consumo_acqua is not None else "-- L/min"
        
        if allarmi is None or allarmi == 0:
            allarmi_text = "Nessun allarme"
        else:
            allarmi_text = f"Allarme: {allarmi}"
        
        text = f"Stato: {stato_text}\n"
        text += f"Velocità nastro: {velocita_nastro_text}\n"
        text += f"Velocità trave: {velocita_trave_text}\n"
        text += f"Pressione teste: {pressione_text}\n"
        text += f"Contropressione teste: {contropressione_text}\n"
        text += f"Temperatura motori: {temperatura_text}\n"
        text += f"Consumo acqua: {consumo_text}\n"
        text += f"Allarmi: {allarmi_text}"
        
        self.status_text.setPlainText(text)


class LucidatriceProduzioneWidget(QGroupBox):
    """Widget per visualizzare i dati di produzione della Lucidatrice"""
    
    def __init__(self, parent=None):
        super().__init__("Produzione", parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.produzione_text = QTextEdit()
        self.produzione_text.setReadOnly(True)
        self.produzione_text.setMaximumHeight(150)
        self.produzione_text.setPlaceholderText(
            "Metri lavorati: 0.0 m\n"
            "Produzione ora: 0.0 m/h\n"
            "Qualità superficie: --\n"
            "Contatore pezzi: 0"
        )
        self.produzione_text.setStyleSheet(production_monospace_field_stylesheet())
        layout.addWidget(self.produzione_text)
    
    def update_produzione(self, metri_lavorati=None, produzione_ora=None, 
                         qualita_superficie=None, contatore_pezzi=None):
        metri_text = f"{metri_lavorati:.2f} m" if metri_lavorati is not None else "-- m"
        produzione_text = f"{produzione_ora:.2f} m/h" if produzione_ora is not None else "-- m/h"
        qualita_text = f"{qualita_superficie:.2f} %" if qualita_superficie is not None else "--"
        contatore_text = f"{int(contatore_pezzi)}" if contatore_pezzi is not None else "0"
        
        text = f"Metri lavorati: {metri_text}\n"
        text += f"Produzione oraria: {produzione_text}\n"
        text += f"Qualità superficie: {qualita_text}\n"
        text += f"Contatore pezzi: {contatore_text}"
        
        self.produzione_text.setPlainText(text)


class LucidatriceParametriWidget(QGroupBox):
    """Widget per visualizzare e modificare i parametri di lavoro della Lucidatrice"""
    
    def __init__(self, parent=None):
        super().__init__("Parametri di Lavoro", parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.parametri_text = QTextEdit()
        self.parametri_text.setReadOnly(True)
        self.parametri_text.setMaximumHeight(150)
        self.parametri_text.setPlaceholderText(
            "Setpoint velocità: 0.0 m/min\n"
            "Setpoint pressione: 0.0 bar\n"
            "Setpoint abrasivi: --\n"
            "Modalità lavoro: --"
        )
        self.parametri_text.setStyleSheet(production_monospace_field_stylesheet())
        layout.addWidget(self.parametri_text)
    
    def update_parametri(self, setpoint_velocita=None, setpoint_pressione=None, 
                        setpoint_abrasivi=None, modalita_lavoro=None):
        velocita_text = f"{setpoint_velocita:.2f} m/min" if setpoint_velocita is not None else "-- m/min"
        pressione_text = f"{setpoint_pressione:.2f} bar" if setpoint_pressione is not None else "-- bar"
        abrasivi_text = setpoint_abrasivi if setpoint_abrasivi else "--"
        modalita_text = modalita_lavoro if modalita_lavoro else "--"
        
        text = f"Setpoint velocità: {velocita_text}\n"
        text += f"Setpoint pressione: {pressione_text}\n"
        text += f"Setpoint abrasivi: {abrasivi_text}\n"
        text += f"Modalità lavoro: {modalita_text}"
        
        self.parametri_text.setPlainText(text)
