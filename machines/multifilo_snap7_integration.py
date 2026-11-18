"""
Integrazione Snap7 Python per Multifilo
Sostituisce l'integrazione Rust con client Python Snap7 per simulazione
"""

import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
from PyQt5.QtCore import QTimer, QObject, pyqtSignal, QThread, QMutex

# Import condizionale per type hints
if TYPE_CHECKING:
    from plc.snap7_multifilo_client import MultifiloPLCClient

try:
    from plc.snap7_multifilo_client import MultifiloPLCClient
    SNAP7_AVAILABLE = True
except ImportError:
    SNAP7_AVAILABLE = False
    MultifiloPLCClient = None  # Placeholder per evitare NameError
    print("⚠ snap7_multifilo_client non disponibile")


class MultifiloStatus:
    """Classe per contenere lo stato della macchina Multifilo"""
    
    def __init__(self):
        # DB1: Stato macchina
        self.stato = 0  # 0=Idle, 1=Run, 2=Alarm
        self.allarme_attivo = False
        self.emergenza = False
        self.porte_aperte = False
        
        # DB2: Parametri macchina
        self.velocita_filo = 0.0  # m/s
        self.tensione_filo = 0.0  # N
        self.pressione_acqua = 0.0  # bar
        self.assorbimento_motore = 0.0  # A
        self.metri = 0.0  # metri tagliati
        self.spreco = 0.0  # spreco (%)
        self.deviazione = 0.0  # deviazione (mm)
        
        # Stato connessione
        self.connessa = False
        self.ultimo_aggiornamento = None
        
        # Calcolati
        self.avanzamento = 0.0  # % (simulato basato su stato)
        self.tempo_residuo = 0  # secondi (simulato)
        self.allarmi = 0  # Codice allarme (0=nessuno)
        
        # Materiale in lavorazione
        self.materiale = "Granito"  # Granito / Marmo / Quarzo / Altro
        self.quantita_lastre = 10  # Numero lastre da lavorare
        self.spessore = 20.0  # mm
        self.finitura = "Tagliato"  # Tagliato / Lucidato / Spazzolato / Fiammato
        self.colore_tipo = "Bianco Carrara"  # Opzionale
        self.cliente_commessa = "Commessa #12345"  # Opzionale
        self.tempo_stimato = 0  # secondi (calcolato)
        self.tempo_inizio_lavorazione = None  # Timestamp inizio
    
    def update_from_db1(self, db1_data: Dict[str, Any]):
        """Aggiorna da DB1 (Stato macchina)"""
        self.stato = db1_data.get("stato", 0)
        self.allarme_attivo = db1_data.get("allarme_attivo", False)
        self.emergenza = db1_data.get("emergenza", False)
        self.porte_aperte = db1_data.get("porte_aperte", False)
        
        # Se quantità lastre = 0, passa automaticamente a HOLD
        if hasattr(self, 'quantita_lastre') and self.quantita_lastre == 0:
            if self.stato == 1:  # Se era in RUN, passa a HOLD
                self.stato = 0  # HOLD
                # Reset avanzamento e tempi
                if hasattr(self, 'avanzamento'):
                    self.avanzamento = 0.0
                if hasattr(self, 'tempo_stimato'):
                    self.tempo_stimato = 0
                if hasattr(self, 'tempo_residuo'):
                    self.tempo_residuo = 0
        
        # Calcola codice allarme
        if self.allarme_attivo:
            self.allarmi = 1
        elif self.emergenza:
            self.allarmi = 2
        else:
            self.allarmi = 0
    
    def update_from_db2(self, db2_data: Dict[str, Any]):
        """Aggiorna da DB2 (Parametri macchina)"""
        self.velocita_filo = db2_data.get("velocita_filo", 0.0)
        self.tensione_filo = db2_data.get("tensione_filo", 0.0)
        self.pressione_acqua = db2_data.get("pressione_acqua", 0.0)
        self.assorbimento_motore = db2_data.get("assorbimento_motore", 0.0)
        self.metri = db2_data.get("metri", 0.0)
        self.spreco = db2_data.get("spreco", 0.0)
        self.deviazione = db2_data.get("deviazione", 0.0)
        
        # Calcola avanzamento materiale basato su metri tagliati - Logica dinamica
        import time
        metri_per_lastra = 5.0
        
        # Inizializza quantità iniziale se non esiste
        if not hasattr(self, '_quantita_iniziale'):
            self._quantita_iniziale = self.quantita_lastre if self.quantita_lastre > 0 else 10
            self.quantita_lastre = self._quantita_iniziale
        
        # Calcola avanzamento progressivo per la lastra corrente
        metri_lastra_corrente = self.metri % metri_per_lastra
        avanzamento_lastra_corrente = (metri_lastra_corrente / metri_per_lastra) * 100.0
        
        # Calcola lastre completate
        lastre_completate = int(self.metri / metri_per_lastra)
        
        # Se una lastra è stata completata, decrementa quantità e resetta avanzamento
        if not hasattr(self, '_lastre_completate_precedenti'):
            self._lastre_completate_precedenti = 0
        
        if lastre_completate > self._lastre_completate_precedenti:
            # Lastra completata: decrementa quantità
            self.quantita_lastre = max(0, self._quantita_iniziale - lastre_completate)
            self._lastre_completate_precedenti = lastre_completate
            # Se quantità = 0, passa a HOLD (gestito in update_from_db1)
            if self.quantita_lastre == 0:
                self.avanzamento = 0.0
                self.tempo_stimato = 0
                self.tempo_residuo = 0
                return
        
        # Avanzamento totale: percentuale lastre completate + avanzamento lastra corrente
        if self._quantita_iniziale > 0:
            percentuale_lastre_completate = (lastre_completate / self._quantita_iniziale) * 100.0
            avanzamento_per_lastra = 100.0 / self._quantita_iniziale
            self.avanzamento = min(100.0, percentuale_lastre_completate + (avanzamento_lastra_corrente * avanzamento_per_lastra / 100.0))
        else:
            self.avanzamento = 0.0
        
        # Calcola tempo stimato e rimanente
        if self.stato == 1:  # RUN
            if self.velocita_filo > 0 and self.quantita_lastre > 0:
                # Metri rimanenti per completare tutte le lastre
                metri_rimanenti = (self.quantita_lastre * metri_per_lastra) - metri_lastra_corrente
                if metri_rimanenti > 0:
                    produzione_oraria = self.velocita_filo * 60.0  # m/h
                    self.tempo_stimato = int((metri_rimanenti / produzione_oraria) * 3600)  # secondi
                else:
                    self.tempo_stimato = 0
                
                # Inizia timer quando inizia la lavorazione
                if self.tempo_inizio_lavorazione is None:
                    self.tempo_inizio_lavorazione = time.time()
                
                # Calcola tempo rimanente
                if self.tempo_inizio_lavorazione and self.tempo_stimato > 0:
                    tempo_trascorso = time.time() - self.tempo_inizio_lavorazione
                    self.tempo_residuo = max(0, int(self.tempo_stimato - tempo_trascorso))
                else:
                    self.tempo_residuo = self.tempo_stimato
            else:
                self.tempo_stimato = 0
                self.tempo_residuo = 0
        elif self.stato == 0:  # HOLD
            # Durante HOLD, tempo rimanente congelato
            if hasattr(self, 'tempo_residuo'):
                pass  # Mantieni valore corrente
            else:
                self.tempo_residuo = 0
        else:  # ERROR o altri stati
            self.tempo_stimato = 0
            self.tempo_residuo = 0
            self.tempo_inizio_lavorazione = None


class MultifiloPLCWorker(QThread):
    """Worker thread per leggere dati PLC ogni 200ms"""
    
    status_updated = pyqtSignal(object)  # Emette MultifiloStatus
    connection_changed = pyqtSignal(bool)  # Emette stato connessione
    
    def __init__(self, client: Optional["MultifiloPLCClient"], parent=None):
        super().__init__(parent)
        self.client = client
        self.running = False
        self.mutex = QMutex()
        self.status = MultifiloStatus()
    
    def run(self):
        """Loop di lettura PLC"""
        if self.client is None:
            print("⚠ Client PLC non disponibile, worker non avviato")
            return
        
        self.running = True
        
        while self.running:
            try:
                self.mutex.lock()
                
                # Leggi DB1 (Stato macchina)
                db1_data = self.client.read_db1_all()
                if db1_data:
                    self.status.update_from_db1(db1_data)
                    self.status.connessa = True
                    self.status.ultimo_aggiornamento = datetime.now()
                    self.connection_changed.emit(True)
                else:
                    self.status.connessa = False
                    self.connection_changed.emit(False)
                
                # Leggi DB2 (Parametri macchina)
                db2_data = self.client.read_db2_all()
                if db2_data:
                    self.status.update_from_db2(db2_data)
                
                # Emetti segnale con stato aggiornato
                self.status_updated.emit(self.status)
                
                self.mutex.unlock()
                
                # Attendi 200ms prima della prossima lettura
                self.msleep(200)
                
            except Exception as e:
                self.mutex.unlock()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Errore lettura PLC: {e}")
                self.status.connessa = False
                self.connection_changed.emit(False)
                
                # Prova riconnessione
                if self.client and not self.client.is_connected():
                    self.client.reconnect()
                
                self.msleep(200)
    
    def stop(self):
        """Ferma il worker"""
        self.running = False
        self.wait(1000)  # Attendi max 1 secondo
    
    def get_status(self) -> MultifiloStatus:
        """Ottiene lo stato corrente (thread-safe)"""
        self.mutex.lock()
        status = self.status
        self.mutex.unlock()
        return status


class MultifiloSnap7Updater(QObject):
    """Gestore per l'aggiornamento automatico della UI Multifilo con Snap7 Python"""
    
    status_updated = pyqtSignal(object)  # Emette MultifiloStatus
    connection_changed = pyqtSignal(bool)
    
    def __init__(self, plc_ip: str = "127.0.0.1", rack: int = 0, slot: int = 1, parent=None):
        super().__init__(parent)
        
        if not SNAP7_AVAILABLE:
            print("⚠ Snap7 non disponibile")
            self.client = None
            self.worker = None
            return
        
        # Crea client Snap7
        self.client = MultifiloPLCClient(ip=plc_ip, rack=rack, slot=slot)
        
        # Connetti al PLC
        if not self.client.connect():
            print(f"⚠ Impossibile connettersi al PLC {plc_ip}")
            print("   Assicurati che il server Snap7 sia in esecuzione")
            self.client = None
            self.worker = None
            return
        
        print(f"✓ PLC Multifilo connesso: {plc_ip} (Rack={rack}, Slot={slot})")
        
        # Crea worker thread per lettura PLC
        self.worker = MultifiloPLCWorker(self.client, parent=self)
        self.worker.status_updated.connect(self.status_updated.emit)
        self.worker.connection_changed.connect(self.connection_changed.emit)
        
        # Logging
        self.log_enabled = True
        self.last_logged_state = None
    
    def start(self, interval_ms: int = 200):
        """Avvia l'aggiornamento automatico (il worker legge ogni 200ms)"""
        if self.worker is None:
            print("⚠ PLC non connesso, impossibile avviare aggiornamento")
            return
        
        self.worker.start()
        print(f"✓ Aggiornamento UI Multifilo avviato (lettura ogni 200ms)")
    
    def stop(self):
        """Ferma l'aggiornamento automatico"""
        if self.worker:
            self.worker.stop()
        
        if self.client:
            self.client.disconnect()
        
        print("✓ Aggiornamento UI Multifilo fermato")
    
    def send_start(self) -> bool:
        """Invia comando Start al PLC"""
        if not self.client or not self.client.is_connected():
            print("⚠ PLC non connesso, impossibile inviare comando Start")
            return False
        
        success = self.client.write_start()
        if success and self.log_enabled:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COMANDO: Start inviato")
        return success
    
    def send_stop(self) -> bool:
        """Invia comando Stop al PLC"""
        if not self.client or not self.client.is_connected():
            print("⚠ PLC non connesso, impossibile inviare comando Stop")
            return False
        
        success = self.client.write_stop()
        if success and self.log_enabled:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COMANDO: Stop inviato")
        return success
    
    def send_reset(self) -> bool:
        """Invia comando Reset al PLC"""
        if not self.client or not self.client.is_connected():
            print("⚠ PLC non connesso, impossibile inviare comando Reset")
            return False
        
        success = self.client.write_reset()
        if success and self.log_enabled:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] COMANDO: Reset inviato")
        return success
    
    def get_current_status(self) -> Optional[MultifiloStatus]:
        """Restituisce lo stato corrente (per uso sincrono)"""
        if self.worker:
            return self.worker.get_status()
        return None
    
    def is_connected(self) -> bool:
        """Verifica se il PLC è connesso"""
        if self.client:
            return self.client.is_connected()
        return False


def refresh_multifilo_ui(status: MultifiloStatus, machine_status_widget, feedback_widget):
    """
    Aggiorna i widget della UI con i dati dal PLC
    
    Args:
        status: MultifiloStatus con i dati aggiornati
        machine_status_widget: QTextEdit per lo stato macchina
        feedback_widget: QTextEdit per il feedback produzione
    """
    if status is None:
        return
    
    # Aggiorna widget "Stato Macchina"
    connessa_text = "✓ Connessa" if status.connessa else "✗ Sconnessa"
    
    stato_text = "Idle"
    if status.stato == 1:
        stato_text = "Run"
    elif status.stato == 2:
        stato_text = "Alarm"
    
    avanzamento_text = f"{status.avanzamento:.1f}%"
    tempo_residuo_text = f"{status.tempo_residuo}s" if status.tempo_residuo > 0 else "--"
    
    if status.allarmi == 0:
        allarmi_text = "Nessun allarme"
    else:
        allarmi_text = f"Allarme: {status.allarmi}"
    
    machine_status_text = f"{connessa_text}\n"
    machine_status_text += f"Stato: {stato_text}\n"
    machine_status_text += f"Avanzamento: {avanzamento_text}\n"
    machine_status_text += f"Tempo residuo: {tempo_residuo_text}\n"
    machine_status_text += f"Allarmi: {allarmi_text}"
    
    if status.emergenza:
        machine_status_text += "\n⚠ EMERGENZA"
    if status.porte_aperte:
        machine_status_text += "\n⚠ Porte aperte"
    
    if machine_status_widget:
        machine_status_widget.setPlainText(machine_status_text)
    
    # Aggiorna widget "Feedback Produzione"
    feedback_text = f"Velocità filo: {status.velocita_filo:.2f} m/s\n"
    feedback_text += f"Tensione filo: {status.tensione_filo:.2f} N\n"
    feedback_text += f"Pressione acqua: {status.pressione_acqua:.2f} bar\n"
    feedback_text += f"Assorbimento motore: {status.assorbimento_motore:.2f} A\n"
    feedback_text += f"Metri tagliati: {status.metri:.2f} m\n"
    feedback_text += f"Spreco: {status.spreco:.2f} %\n"
    feedback_text += f"Deviazione: {status.deviazione:.2f} mm"
    
    if feedback_widget:
        feedback_widget.setPlainText(feedback_text)

