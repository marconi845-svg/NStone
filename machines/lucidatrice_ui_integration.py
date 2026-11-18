"""
Modulo per integrare i dati PLC Lucidatrice con la UI PyQt5
Gestisce l'aggiornamento automatico dei widget ogni 100ms
"""
import rust_engine
from PyQt5.QtCore import QTimer, QObject, pyqtSignal, QRunnable, QThreadPool


class LucidatriceStatusWorker(QRunnable):
    """Worker per leggere i dati dal PLC in background"""
    
    def __init__(self, plc, ui_status):
        super().__init__()
        self.plc = plc
        self.ui_status = ui_status
    
    def run(self):
        """Esegue la lettura dal PLC e aggiorna lo stato"""
        try:
            rust_engine.update_gestione_lucidatrice_py(self.plc, self.ui_status)
        except Exception as e:
            print(f"Errore lettura PLC Lucidatrice: {e}")


class LucidatriceUIUpdater(QObject):
    """Gestore per l'aggiornamento automatico della UI Lucidatrice"""
    
    status_updated = pyqtSignal(object)
    
    def __init__(self, plc_ip="192.168.0.2", db_number=2, parent=None):
        super().__init__(parent)
        self.plc = None
        self.ui_status = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.thread_pool = QThreadPool.globalInstance()
        
        try:
            self.plc = rust_engine.PyPlcClient(plc_ip, db_number)
            self.ui_status = rust_engine.PyGestioneLucidatriceUI()
            print(f"✓ PLC Lucidatrice connesso: {plc_ip}, DB{db_number}")
        except Exception as e:
            print(f"✗ Errore connessione PLC Lucidatrice: {e}")
            self.plc = None
            self.ui_status = None
    
    def start(self, interval_ms=100):
        """Avvia l'aggiornamento automatico"""
        if self.plc is None or self.ui_status is None:
            print("⚠ PLC Lucidatrice non connesso, impossibile avviare aggiornamento")
            return
        self.timer.start(interval_ms)
        print(f"✓ Aggiornamento UI Lucidatrice avviato (ogni {interval_ms}ms)")
    
    def stop(self):
        """Ferma l'aggiornamento automatico"""
        self.timer.stop()
        if self.plc:
            try:
                self.plc.disconnect()
            except:
                pass
        print("✓ Aggiornamento UI Lucidatrice fermato")
    
    def update_status(self):
        """Aggiorna lo stato dal PLC (chiamato dal timer)"""
        if self.plc is None or self.ui_status is None:
            return
        
        try:
            # Aggiorna i dati dal PLC (la lettura è veloce, non blocca la UI)
            rust_engine.update_gestione_lucidatrice_py(self.plc, self.ui_status)
            
            # Emetti il segnale con i dati aggiornati
            self.status_updated.emit(self.ui_status)
        except Exception as e:
            print(f"Errore aggiornamento PLC Lucidatrice: {e}")
    
    def get_current_status(self):
        """Restituisce lo stato corrente (per uso sincrono)"""
        return self.ui_status


def refresh_lucidatrice_ui(status, status_widget, produzione_widget, parametri_widget):
    """
    Aggiorna i widget della UI con i dati dal PLC
    
    Args:
        status: PyGestioneLucidatriceUI con i dati aggiornati
        status_widget: QTextEdit per lo stato macchina
        produzione_widget: QTextEdit per la produzione
        parametri_widget: QTextEdit per i parametri
    """
    if status is None:
        return
    
    # Aggiorna widget "Stato Macchina"
    stato_text = getattr(status, 'stato_macchina', 'STOP')
    velocita_text = f"{getattr(status, 'velocita_nastro', 0.0):.2f} m/min"
    pressione_text = f"{getattr(status, 'pressione_teste', 0.0):.2f} bar"
    temperatura_text = f"{getattr(status, 'temperatura_motori', 0.0):.1f} °C"
    consumo_text = f"{getattr(status, 'consumo_acqua', 0.0):.2f} L/min"
    allarmi = getattr(status, 'allarmi', 0)
    allarmi_text = "Nessun allarme" if allarmi == 0 else f"Allarme: {allarmi}"
    
    machine_status_text = f"Stato: {stato_text}\n"
    machine_status_text += f"Velocità nastro: {velocita_text}\n"
    machine_status_text += f"Pressione teste: {pressione_text}\n"
    machine_status_text += f"Temperatura motori: {temperatura_text}\n"
    machine_status_text += f"Consumo acqua: {consumo_text}\n"
    machine_status_text += f"Allarmi: {allarmi_text}"
    
    if status_widget:
        status_widget.setPlainText(machine_status_text)
    
    # Aggiorna widget "Produzione"
    metri_text = f"{getattr(status, 'metri_lavorati', 0.0):.2f} m"
    produzione_text = f"{getattr(status, 'produzione_ora', 0.0):.2f} m/h"
    qualita_text = getattr(status, 'qualita_superficie', '--')
    contatore_text = f"{getattr(status, 'contatore_pezzi', 0)}"
    
    produzione_ui_text = f"Metri lavorati: {metri_text}\n"
    produzione_ui_text += f"Produzione ora: {produzione_text}\n"
    produzione_ui_text += f"Qualità superficie: {qualita_text}\n"
    produzione_ui_text += f"Contatore pezzi: {contatore_text}"
    
    if produzione_widget:
        produzione_widget.setPlainText(produzione_ui_text)
    
    # Aggiorna widget "Parametri"
    setpoint_velocita_text = f"{getattr(status, 'setpoint_velocita', 0.0):.2f} m/min"
    setpoint_pressione_text = f"{getattr(status, 'setpoint_pressione', 0.0):.2f} bar"
    setpoint_abrasivi_text = getattr(status, 'setpoint_abrasivi', '--')
    modalita_text = getattr(status, 'modalita_lavoro', '--')
    
    parametri_ui_text = f"Setpoint velocità: {setpoint_velocita_text}\n"
    parametri_ui_text += f"Setpoint pressione: {setpoint_pressione_text}\n"
    parametri_ui_text += f"Setpoint abrasivi: {setpoint_abrasivi_text}\n"
    parametri_ui_text += f"Modalità lavoro: {modalita_text}"
    
    if parametri_widget:
        parametri_widget.setPlainText(parametri_ui_text)




