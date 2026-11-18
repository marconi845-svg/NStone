"""
Modulo per integrare i dati PLC Multifilo con la UI PyQt5
Gestisce l'aggiornamento automatico dei widget ogni 100ms
"""
import rust_engine
from PyQt5.QtCore import QTimer, QObject, pyqtSignal, QRunnable, QThreadPool


class MultifiloStatusWorker(QRunnable):
    """Worker per leggere i dati dal PLC in background"""
    
    def __init__(self, plc, ui_status):
        super().__init__()
        self.plc = plc
        self.ui_status = ui_status
    
    def run(self):
        """Esegue la lettura dal PLC e aggiorna lo stato"""
        try:
            rust_engine.update_gestione_multifilo_py(self.plc, self.ui_status)
        except Exception as e:
            print(f"Errore lettura PLC: {e}")


class MultifiloUIUpdater(QObject):
    """Gestore per l'aggiornamento automatico della UI Multifilo"""
    
    status_updated = pyqtSignal(object)
    
    def __init__(self, plc_ip="192.168.0.1", db_number=1, parent=None):
        super().__init__(parent)
        self.plc = None
        self.ui_status = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.thread_pool = QThreadPool.globalInstance()
        
        try:
            self.plc = rust_engine.PyPlcClient(plc_ip, db_number)
            self.ui_status = rust_engine.PyGestioneMultifiloUI()
            print(f"✓ PLC Multifilo connesso: {plc_ip}, DB{db_number}")
        except Exception as e:
            print(f"✗ Errore connessione PLC: {e}")
            self.plc = None
            self.ui_status = None
    
    def start(self, interval_ms=100):
        """Avvia l'aggiornamento automatico"""
        if self.plc is None or self.ui_status is None:
            print("⚠ PLC non connesso, impossibile avviare aggiornamento")
            return
        self.timer.start(interval_ms)
        print(f"✓ Aggiornamento UI Multifilo avviato (ogni {interval_ms}ms)")
    
    def stop(self):
        """Ferma l'aggiornamento automatico"""
        self.timer.stop()
        if self.plc:
            try:
                self.plc.disconnect()
            except:
                pass
        print("✓ Aggiornamento UI Multifilo fermato")
    
    def update_status(self):
        """Aggiorna lo stato dal PLC (chiamato dal timer)"""
        if self.plc is None or self.ui_status is None:
            return
        
        try:
            # Aggiorna i dati dal PLC (la lettura è veloce, non blocca la UI)
            rust_engine.update_gestione_multifilo_py(self.plc, self.ui_status)
            
            # Emetti il segnale con i dati aggiornati
            self.status_updated.emit(self.ui_status)
        except Exception as e:
            print(f"Errore aggiornamento PLC: {e}")
    
    def get_current_status(self):
        """Restituisce lo stato corrente (per uso sincrono)"""
        return self.ui_status


def refresh_multifilo_ui(status, machine_status_widget, feedback_widget):
    """
    Aggiorna i widget della UI con i dati dal PLC
    
    Args:
        status: PyGestioneMultifiloUI con i dati aggiornati
        machine_status_widget: QTextEdit per lo stato macchina
        feedback_widget: QTextEdit per il feedback produzione
    """
    if status is None:
        return
    
    # Aggiorna widget "Stato Macchina"
    connessa_text = "✓ Connessa" if status.connessa else "✗ Sconnessa"
    avanzamento_text = f"{status.avanzamento:.1f}%"
    tempo_residuo_text = f"{status.tempo_residuo}s" if status.tempo_residuo > 0 else "--"
    
    if status.allarmi == 0:
        allarmi_text = "Nessun allarme"
    else:
        allarmi_text = f"Allarme: {status.allarmi}"
    
    machine_status_text = f"{connessa_text}\n"
    machine_status_text += f"Avanzamento: {avanzamento_text}\n"
    machine_status_text += f"Tempo residuo: {tempo_residuo_text}\n"
    machine_status_text += f"Allarmi: {allarmi_text}"
    
    if machine_status_widget:
        machine_status_widget.setPlainText(machine_status_text)
    
    # Aggiorna widget "Feedback Produzione"
    spreco_text = f"{status.spreco_reale:.2f}" if status.spreco_reale is not None else "--"
    tempo_reale_text = f"{status.tempo_reale:.2f}s" if status.tempo_reale is not None else "--"
    deviazioni_text = status.deviazioni if status.deviazioni else "--"
    
    feedback_text = f"Spreco reale: {spreco_text}\n"
    feedback_text += f"Tempo reale: {tempo_reale_text}\n"
    feedback_text += f"Deviazioni: {deviazioni_text}"
    
    if feedback_widget:
        feedback_widget.setPlainText(feedback_text)

