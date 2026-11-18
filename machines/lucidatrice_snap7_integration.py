"""
Integrazione Snap7 Python per Lucidatrice/Calibratrice
Replica del pattern architetturale Multifilo per mantenere coerenza e robustezza
"""

import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
from PyQt5.QtCore import QTimer, QObject, pyqtSignal, QThread, QMutex

# Import condizionale per type hints
if TYPE_CHECKING:
    from plc.snap7_lucidatrice_client import LucidatricePLCClient

try:
    from plc.snap7_lucidatrice_client import LucidatricePLCClient
    SNAP7_AVAILABLE = True
except ImportError:
    SNAP7_AVAILABLE = False
    LucidatricePLCClient = None  # Placeholder per evitare NameError
    print("⚠ snap7_lucidatrice_client non disponibile")


class LucidatriceStatus:
    """Classe per contenere lo stato della macchina Lucidatrice/Calibratrice"""
    
    def __init__(self):
        # DB1: Stato macchina
        self.stato = 0  # 0=Idle, 1=Run, 2=Alarm, 3=Testine_Error, 4=Nastro_Error
        self.allarme_attivo = False
        self.emergenza = False
        self.pressione_fuori_range = False
        self.assorbimento_anomalo = False
        self.encoder_trave_error = False
        self.finecorsa_attivo = False
        
        # DB2: Parametri macchina
        self.posizione_trave = 0.0  # mm
        self.velocita_nastro = 0.0  # m/min
        self.pressione_testine = 0.0  # bar
        self.assorbimento_motore_principale = 0.0  # A
        self.assorbimento_motore_nastro = 0.0  # A
        self.metri_lavorati = 0.0  # m
        self.qualita_superficie = 0.0  # %
        self.assorbimento_testine = 0.0  # A
        self.velocita_trave = 0.0  # mm/s
        self.produzione_oraria = 0.0  # m/h
        self.contatore_pezzi = 0.0  # pezzi
        
        # Stato connessione
        self.connessa = False
        self.ultimo_aggiornamento = None
        
        # Calcolati
        self.avanzamento = 0.0  # % (simulato basato su stato)
        self.tempo_residuo = 0  # secondi (simulato)
        self.allarmi = 0  # Codice allarme (0=nessuno)
        
        # Parametri simulati/calcolati per UI
        self.temperatura_motori = 0.0  # °C (calcolato da assorbimento)
        self.consumo_acqua = 0.0  # L/min (calcolato da velocità nastro)
        self.contropressione_teste = 0.0  # bar (calcolato come % di pressione_testine)
        
        # Materiale in lavorazione
        self.materiale = "Granito"  # Granito / Marmo / Quarzo / Altro
        self.quantita_lastre = 10  # Numero lastre da lavorare
        self.spessore = 20.0  # mm
        self.finitura = "Lucidato"  # Lucidato / Spazzolato / Fiammato / Exx
        self.colore_tipo = "Bianco Carrara"  # Opzionale
        self.cliente_commessa = "Commessa #12345"  # Opzionale
        self.tempo_stimato = 0  # secondi (calcolato)
        self.tempo_inizio_lavorazione = None  # Timestamp inizio
    
    def update_from_db1(self, db1_data: Dict[str, Any]):
        """Aggiorna da DB1 (Stato macchina)"""
        self.stato = db1_data.get("stato", 0)
        self.allarme_attivo = db1_data.get("allarme_attivo", False)
        self.emergenza = db1_data.get("emergenza", False)
        self.pressione_fuori_range = db1_data.get("pressione_fuori_range", False)
        self.assorbimento_anomalo = db1_data.get("assorbimento_anomalo", False)
        self.encoder_trave_error = db1_data.get("encoder_trave_error", False)
        self.finecorsa_attivo = db1_data.get("finecorsa_attivo", False)
        
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
            if self.pressione_fuori_range:
                self.allarmi = 1
            elif self.assorbimento_anomalo:
                self.allarmi = 2
            elif self.encoder_trave_error:
                self.allarmi = 3
            elif self.finecorsa_attivo:
                self.allarmi = 4
            else:
                self.allarmi = 1  # Allarme generico
        elif self.emergenza:
            self.allarmi = 5
        else:
            self.allarmi = 0
    
    def update_from_db2(self, db2_data: Dict[str, Any]):
        """Aggiorna da DB2 (Parametri macchina) - Pattern identico a Multifilo"""
        self.posizione_trave = db2_data.get("posizione_trave", 0.0)
        self.velocita_nastro = db2_data.get("velocita_nastro", 0.0)
        self.pressione_testine = db2_data.get("pressione_testine", 0.0)
        self.assorbimento_motore_principale = db2_data.get("assorbimento_motore_principale", 0.0)
        self.assorbimento_motore_nastro = db2_data.get("assorbimento_motore_nastro", 0.0)
        self.metri_lavorati = db2_data.get("metri_lavorati", 0.0)
        self.qualita_superficie = db2_data.get("qualita_superficie", 0.0)
        self.assorbimento_testine = db2_data.get("assorbimento_testine", 0.0)
        self.velocita_trave = db2_data.get("velocita_trave", 0.0)
        self.produzione_oraria = db2_data.get("produzione_oraria", 0.0)
        self.contatore_pezzi = db2_data.get("contatore_pezzi", 0.0)
        
        # Calcola parametri simulati per UI
        # Temperatura motori: proporzionale all'assorbimento principale (base 25°C + 2°C per A)
        self.temperatura_motori = 25.0 + (self.assorbimento_motore_principale * 2.0)
        self.temperatura_motori = max(25.0, min(85.0, self.temperatura_motori))  # Range 25-85°C
        
        # Consumo acqua: proporzionale alla velocità nastro (base 5 L/min + 0.5 L/min per m/min)
        self.consumo_acqua = 5.0 + (self.velocita_nastro * 0.5)
        self.consumo_acqua = max(0.0, min(30.0, self.consumo_acqua))  # Range 0-30 L/min
        
        # Contropressione teste: 70% della pressione principale (tipico per lucidatrici)
        self.contropressione_teste = self.pressione_testine * 0.7
        
        # Calcola avanzamento materiale basato su metri lavorati - Logica dinamica
        import time
        metri_per_lastra = 10.0
        
        # Inizializza quantità iniziale se non esiste
        if not hasattr(self, '_quantita_iniziale'):
            self._quantita_iniziale = self.quantita_lastre if self.quantita_lastre > 0 else 10
            self.quantita_lastre = self._quantita_iniziale
        
        # Calcola avanzamento progressivo per la lastra corrente
        metri_lastra_corrente = self.metri_lavorati % metri_per_lastra
        avanzamento_lastra_corrente = (metri_lastra_corrente / metri_per_lastra) * 100.0
        
        # Calcola lastre completate
        lastre_completate = int(self.metri_lavorati / metri_per_lastra)
        
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
            if self.produzione_oraria > 0 and self.quantita_lastre > 0:
                # Metri rimanenti per completare tutte le lastre
                metri_rimanenti = (self.quantita_lastre * metri_per_lastra) - metri_lastra_corrente
                if metri_rimanenti > 0:
                    self.tempo_stimato = int((metri_rimanenti / self.produzione_oraria) * 3600)  # secondi
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


class LucidatricePLCWorker(QThread):
    """Worker thread per leggere dati PLC ogni 200ms - Pattern identico a Multifilo"""
    
    status_updated = pyqtSignal(object)  # Emette LucidatriceStatus
    connection_changed = pyqtSignal(bool)  # Emette stato connessione
    
    def __init__(self, client: Optional["LucidatricePLCClient"], parent=None):
        super().__init__(parent)
        self.client = client
        self.running = False
        self.mutex = QMutex()
        self.status = LucidatriceStatus()
    
    def run(self):
        """Loop di lettura PLC - Pattern identico a Multifilo"""
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
        """Ferma il worker - Pattern identico a Multifilo"""
        self.running = False
        self.wait(1000)  # Attendi max 1 secondo
    
    def get_status(self) -> LucidatriceStatus:
        """Ottiene lo stato corrente (thread-safe) - Pattern identico a Multifilo"""
        self.mutex.lock()
        status = self.status
        self.mutex.unlock()
        return status


class LucidatriceSnap7Updater(QObject):
    """Gestore per l'aggiornamento automatico della UI Lucidatrice con Snap7 Python
    Pattern architetturale identico a MultifiloSnap7Updater"""
    
    status_updated = pyqtSignal(object)  # Emette LucidatriceStatus
    connection_changed = pyqtSignal(bool)
    
    def __init__(self, plc_ip: str = "127.0.0.1", rack: int = 0, slot: int = 1, parent=None):
        super().__init__(parent)
        
        if not SNAP7_AVAILABLE:
            print("⚠ Snap7 non disponibile")
            self.client = None
            self.worker = None
            return
        
        # Crea client Snap7
        self.client = LucidatricePLCClient(ip=plc_ip, rack=rack, slot=slot)
        
        # Connetti al PLC
        if not self.client.connect():
            print(f"⚠ Impossibile connettersi al PLC {plc_ip}")
            print("   Assicurati che il server Snap7 sia in esecuzione")
            self.client = None
            self.worker = None
            return
        
        print(f"✓ PLC Lucidatrice connesso: {plc_ip} (Rack={rack}, Slot={slot})")
        
        # Crea worker thread per lettura PLC
        self.worker = LucidatricePLCWorker(self.client, parent=self)
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
        print(f"✓ Aggiornamento UI Lucidatrice avviato (lettura ogni 200ms)")
    
    def stop(self):
        """Ferma l'aggiornamento automatico - Pattern identico a Multifilo"""
        if self.worker:
            self.worker.stop()
        
        if self.client:
            self.client.disconnect()
        
        print("✓ Aggiornamento UI Lucidatrice fermato")
    
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
    
    def get_current_status(self) -> Optional[LucidatriceStatus]:
        """Restituisce lo stato corrente (per uso sincrono)"""
        if self.worker:
            return self.worker.get_status()
        return None
    
    def is_connected(self) -> bool:
        """Verifica se il PLC è connesso"""
        if self.client:
            return self.client.is_connected()
        return False


def refresh_lucidatrice_ui(status: LucidatriceStatus, machine_status_widget, feedback_widget):
    """
    Aggiorna i widget della UI con i dati dal PLC
    Pattern identico a refresh_multifilo_ui
    
    Args:
        status: LucidatriceStatus con i dati aggiornati
        machine_status_widget: QTextEdit per lo stato macchina
        feedback_widget: QTextEdit per il feedback produzione
    """
    if status is None:
        return
    
    # Aggiorna widget "Stato Macchina"
    connessa_text = "✓ Connessa" if status.connessa else "✗ Sconnessa"
    
    stato_map = {0: "Idle", 1: "Run", 2: "Alarm", 3: "Testine_Error", 4: "Nastro_Error"}
    stato_text = stato_map.get(status.stato, f"Unknown({status.stato})")
    
    avanzamento_text = f"{status.avanzamento:.1f}%"
    tempo_residuo_text = f"{status.tempo_residuo}s" if status.tempo_residuo > 0 else "--"
    
    if status.allarmi == 0:
        allarmi_text = "Nessun allarme"
    else:
        allarmi_text = f"Allarme: {status.allarmi}"
    
    machine_status_text = f"{connessa_text}\n"
    machine_status_text += f"Stato: {stato_text}\n"
    machine_status_text += f"Velocità nastro: {status.velocita_nastro:.2f} m/min\n"
    machine_status_text += f"Velocità trave: {status.velocita_trave:.2f} mm/s\n"
    machine_status_text += f"Pressione teste: {status.pressione_testine:.2f} bar\n"
    machine_status_text += f"Contropressione teste: {status.contropressione_teste:.2f} bar\n"
    machine_status_text += f"Temperatura motori: {status.temperatura_motori:.1f} °C\n"
    machine_status_text += f"Consumo acqua: {status.consumo_acqua:.2f} L/min\n"
    machine_status_text += f"Allarmi: {allarmi_text}"
    
    if status.emergenza:
        machine_status_text += "\n⚠ EMERGENZA"
    if status.pressione_fuori_range:
        machine_status_text += "\n⚠ Pressione fuori range"
    if status.assorbimento_anomalo:
        machine_status_text += "\n⚠ Assorbimento anomalo"
    if status.encoder_trave_error:
        machine_status_text += "\n⚠ Encoder trave error"
    if status.finecorsa_attivo:
        machine_status_text += "\n⚠ Finecorsa attivo"
    
    if machine_status_widget:
        machine_status_widget.setPlainText(machine_status_text)
    
    # Aggiorna widget "Feedback Produzione" - Pattern identico a Multifilo
    feedback_text = f"Posizione trave: {status.posizione_trave:.2f} mm\n"
    feedback_text += f"Velocità nastro: {status.velocita_nastro:.2f} m/min\n"
    feedback_text += f"Velocità trave: {status.velocita_trave:.2f} mm/s\n"
    feedback_text += f"Pressione testine: {status.pressione_testine:.2f} bar\n"
    feedback_text += f"Assorbimento principale: {status.assorbimento_motore_principale:.2f} A\n"
    feedback_text += f"Assorbimento nastro: {status.assorbimento_motore_nastro:.2f} A\n"
    feedback_text += f"Assorbimento testine: {status.assorbimento_testine:.2f} A\n"
    feedback_text += f"Metri lavorati: {status.metri_lavorati:.2f} m\n"
    feedback_text += f"Produzione oraria: {status.produzione_oraria:.2f} m/h\n"
    feedback_text += f"Contatore pezzi: {int(status.contatore_pezzi)}\n"
    feedback_text += f"Qualità superficie: {status.qualita_superficie:.2f} %"
    
    if feedback_widget:
        feedback_widget.setPlainText(feedback_text)

