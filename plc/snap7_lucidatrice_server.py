"""
Snap7 Server - Simulazione PLC Lucidatrice/Calibratrice
Simula un PLC Siemens S7-1200/S7-1500 per testare il Motore Neurale

DB1: Stato macchina (7 byte)
- Byte 0: Stato generale (0=Idle, 1=Run, 2=Alarm, 3=Testine_Error, 4=Nastro_Error)
- Byte 1: Allarme attivo (0=No, 1=Sì)
- Byte 2: Emergenza (0=No, 1=Sì)
- Byte 3: Pressione fuori range (0=No, 1=Sì)
- Byte 4: Assorbimento anomalo (0=No, 1=Sì)
- Byte 5: Encoder trave error (0=No, 1=Sì)
- Byte 6: Finecorsa attivo (0=No, 1=Sì)

DB2: Parametri macchina (44 byte = 11 Real)
- Real 0: Posizione trave (mm)
- Real 4: Velocità nastro (m/min)
- Real 8: Pressione testine (bar)
- Real 12: Assorbimento motore principale (A)
- Real 16: Assorbimento motore nastro (A)
- Real 20: Metri lavorati (m)
- Real 24: Qualità superficie (%)
- Real 28: Assorbimento testine (A)
- Real 32: Velocità trave (mm/s)
- Real 36: Produzione oraria (m/h)
- Real 40: Contatore pezzi (pezzi)

DB3: Comandi macchina (3 byte)
- Byte 0: Start (1=Start)
- Byte 1: Stop (1=Stop)
- Byte 2: Reset (1=Reset)
"""

import snap7
import struct
import time
import random
import threading
import logging
import ctypes
from datetime import datetime
from typing import Optional

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Costanti - Dimensioni Data Block
DB1_SIZE = 7  # Stato macchina (7 byte)
DB2_SIZE = 44  # Parametri (44 byte = 11 Real: posizione, velocità nastro, pressione, assorbimenti, metri, qualità, assorbimento testine, velocità trave, produzione oraria, contatore pezzi)
DB3_SIZE = 3  # Comandi (3 byte)

# Verifica che le dimensioni siano valide (> 0)
assert DB1_SIZE > 0, "DB1_SIZE deve essere > 0"
assert DB2_SIZE > 0, "DB2_SIZE deve essere > 0"
assert DB3_SIZE > 0, "DB3_SIZE deve essere > 0"

# Valori iniziali DB2
INITIAL_POSIZIONE_TRAVE = 0.0  # mm
INITIAL_VELOCITA_NASTRO = 0.0  # m/min
INITIAL_PRESSIONE_TESTINE = 0.0  # bar
INITIAL_ASSORBIMENTO_PRINCIPALE = 0.0  # A
INITIAL_ASSORBIMENTO_NASTRO = 0.0  # A
INITIAL_METRI_LAVORATI = 0.0  # m
INITIAL_QUALITA_SUPERFICIE = 0.0  # %
INITIAL_ASSORBIMENTO_TESTINE = 0.0  # A
INITIAL_VELOCITA_TRAVE = 0.0  # mm/s
INITIAL_PRODUZIONE_ORARIA = 0.0  # m/h
INITIAL_CONTATORE_PEZZI = 0.0  # pezzi


class LucidatricePLCServer:
    """Server Snap7 che simula il PLC Lucidatrice/Calibratrice"""
    
    def __init__(self, ip: str = "127.0.0.1", rack: int = 0, slot: int = 1):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.server = snap7.server.Server()
        
        # Buffer per i DB - Inizializzati con dimensioni corrette
        if DB1_SIZE <= 0 or DB2_SIZE <= 0 or DB3_SIZE <= 0:
            raise ValueError(f"Dimensioni DB non valide: DB1={DB1_SIZE}, DB2={DB2_SIZE}, DB3={DB3_SIZE}")
        
        # Crea bytearray per i DB
        self.db1 = bytearray(DB1_SIZE)  # Stato macchina (7 byte)
        self.db2 = bytearray(DB2_SIZE)  # Parametri (44 byte = 11 Real)
        self.db3 = bytearray(DB3_SIZE)  # Comandi (3 byte)
        
        # Verifica che i bytearray siano stati creati correttamente
        assert len(self.db1) == DB1_SIZE, f"DB1 dimensione errata: {len(self.db1)} != {DB1_SIZE}"
        assert len(self.db2) == DB2_SIZE, f"DB2 dimensione errata: {len(self.db2)} != {DB2_SIZE}"
        assert len(self.db3) == DB3_SIZE, f"DB3 dimensione errata: {len(self.db3)} != {DB3_SIZE}"
        
        # Verifica che i bytearray non siano vuoti
        assert len(self.db1) > 0, "DB1 è vuoto"
        assert len(self.db2) > 0, "DB2 è vuoto"
        assert len(self.db3) > 0, "DB3 è vuoto"
        
        # Inizializza DB1 (Stato: Idle, nessun allarme)
        self.db1[0] = 0  # Stato: Idle
        self.db1[1] = 0  # Allarme: No
        self.db1[2] = 0  # Emergenza: No
        self.db1[3] = 0  # Pressione fuori range: No
        self.db1[4] = 0  # Assorbimento anomalo: No
        self.db1[5] = 0  # Encoder trave error: No
        self.db1[6] = 0  # Finecorsa attivo: No
        
        # Inizializza DB2 (Parametri a zero)
        self._write_real(self.db2, 0, INITIAL_POSIZIONE_TRAVE)   # Posizione trave (offset 0-3)
        self._write_real(self.db2, 4, INITIAL_VELOCITA_NASTRO)     # Velocità nastro (offset 4-7)
        self._write_real(self.db2, 8, INITIAL_PRESSIONE_TESTINE)     # Pressione testine (offset 8-11)
        self._write_real(self.db2, 12, INITIAL_ASSORBIMENTO_PRINCIPALE)    # Assorbimento principale (offset 12-15)
        self._write_real(self.db2, 16, INITIAL_ASSORBIMENTO_NASTRO)       # Assorbimento nastro (offset 16-19)
        self._write_real(self.db2, 20, INITIAL_METRI_LAVORATI)       # Metri lavorati (offset 20-23)
        self._write_real(self.db2, 24, INITIAL_QUALITA_SUPERFICIE)  # Qualità superficie (offset 24-27)
        self._write_real(self.db2, 28, INITIAL_ASSORBIMENTO_TESTINE)  # Assorbimento testine (offset 28-31)
        self._write_real(self.db2, 32, INITIAL_VELOCITA_TRAVE)  # Velocità trave (offset 32-35)
        self._write_real(self.db2, 36, INITIAL_PRODUZIONE_ORARIA)  # Produzione oraria (offset 36-39)
        self._write_real(self.db2, 40, INITIAL_CONTATORE_PEZZI)  # Contatore pezzi (offset 40-43)
        
        # Variabili per simulazione dinamica
        self.tempo_attivo_ore = 0.0  # Ore di lavoro attivo per calcolo produzione oraria
        self.ultimo_ciclo_trave = 0.0  # Posizione trave all'ultimo ciclo completato
        self.ciclo_lunghezza = 3000.0  # Lunghezza ciclo trave in mm (per contatore pezzi)
        
        # Inizializza DB3 (Comandi a zero)
        self.db3[0] = 0  # Start
        self.db3[1] = 0  # Stop
        self.db3[2] = 0  # Reset
        
        # Thread per aggiornamento DB2
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
    
    def _write_real(self, buffer: bytearray, offset: int, value: float):
        """Scrive un valore REAL (32-bit float) nel buffer"""
        struct.pack_into('>f', buffer, offset, value)
    
    def _read_real(self, buffer: bytearray, offset: int) -> float:
        """Legge un valore REAL (32-bit float) dal buffer"""
        return struct.unpack_from('>f', buffer, offset)[0]
    
    def _register_db(self, db_number: int, size: int, buffer: bytearray):
        """Registra un Data Block nel server"""
        if buffer is None:
            raise ValueError(f"Buffer DB{db_number} è None")
        if not isinstance(buffer, bytearray):
            raise TypeError(f"Buffer DB{db_number} deve essere bytearray, trovato: {type(buffer)}")
        if len(buffer) != size:
            raise ValueError(f"Buffer DB{db_number} dimensione errata: {len(buffer)} != {size}")
        if len(buffer) == 0:
            raise ValueError(f"Buffer DB{db_number} ha dimensione 0")
        
        try:
            area_enum = snap7.server.SrvArea.DB
            ctypes_buffer = (ctypes.c_ubyte * size).from_buffer(buffer)
            self.server.register_area(area_enum, db_number, ctypes_buffer)
            logger.info(f"DB{db_number} registrato (dimensione: {size} byte)")
        except Exception as e:
            logger.error(f"Errore registrazione DB{db_number}: {e}")
            logger.error(f"Tipo buffer: {type(buffer)}, Dimensione: {len(buffer)}")
            raise
    
    def _update_db2_parameters(self):
        """Aggiorna i parametri DB2 ogni 500ms con variazioni casuali - Pattern identico a Multifilo"""
        import time as time_module
        start_time = time_module.time()
        
        while self.running:
            try:
                # Leggi stato corrente
                stato = self.db1[0]
                delta_tempo = 0.5  # 500ms = 0.5 secondi
                
                # Se la macchina è in Run, aggiorna i parametri con oscillazioni percentuali realistiche
                if stato == 1:  # Run
                    # Aggiorna tempo attivo per calcolo produzione oraria
                    self.tempo_attivo_ore += delta_tempo / 3600.0  # Converti secondi in ore
                    
                    # Leggi valori attuali
                    current_posizione = self._read_real(self.db2, 0)
                    current_velocita = self._read_real(self.db2, 4)
                    current_pressione = self._read_real(self.db2, 8)
                    current_assorb_principale = self._read_real(self.db2, 12)
                    current_assorb_nastro = self._read_real(self.db2, 16)
                    current_metri = self._read_real(self.db2, 20)
                    current_qualita = self._read_real(self.db2, 24)
                    current_assorb_testine = self._read_real(self.db2, 28)
                    current_velocita_trave = self._read_real(self.db2, 32)
                    current_produzione_oraria = self._read_real(self.db2, 36)
                    current_contatore_pezzi = self._read_real(self.db2, 40)
                    
                    # Posizione trave: movimento lento (posizione += velocità_trave * delta_tempo)
                    # Simula movimento trave proporzionale alla velocità trave
                    if current_velocita_trave > 0:
                        new_posizione = current_posizione + (current_velocita_trave * delta_tempo)
                        new_posizione = max(0.0, min(3000.0, new_posizione))  # Limiti fisici 0-3000mm
                        self._write_real(self.db2, 0, new_posizione)
                        
                        # Contatore pezzi: incrementa quando la trave completa un ciclo
                        # Ciclo = quando la posizione supera la lunghezza ciclo e torna a 0
                        if new_posizione >= self.ciclo_lunghezza:
                            new_contatore_pezzi = current_contatore_pezzi + 1.0
                            self._write_real(self.db2, 40, new_contatore_pezzi)
                            # Reset posizione per nuovo ciclo
                            self._write_real(self.db2, 0, 0.0)
                            self.ultimo_ciclo_trave = time.time()  # Timestamp ultimo ciclo
                    else:
                        new_posizione = current_posizione
                    
                    # Velocità nastro: oscillazione ±2% (simula variazioni naturali)
                    new_velocita = current_velocita * (1 + random.uniform(-0.02, 0.02))
                    new_velocita = max(0.0, min(50.0, new_velocita))  # Limiti fisici 0-50 m/min
                    self._write_real(self.db2, 4, new_velocita)
                    
                    # Pressione testine: oscillazione lenta ±1% (sistema idraulico stabile)
                    new_pressione = current_pressione * (1 + random.uniform(-0.01, 0.01))
                    new_pressione = max(1.0, min(10.0, new_pressione))  # Limiti fisici 1-10 bar
                    self._write_real(self.db2, 8, new_pressione)
                    
                    # Assorbimento motore principale: micro-rumore ±0.5%
                    new_assorb_principale = current_assorb_principale * (1 + random.uniform(-0.005, 0.005))
                    new_assorb_principale = max(3.0, min(20.0, new_assorb_principale))  # Limiti fisici
                    self._write_real(self.db2, 12, new_assorb_principale)
                    
                    # Assorbimento motore nastro: micro-rumore ±0.5%
                    new_assorb_nastro = current_assorb_nastro * (1 + random.uniform(-0.005, 0.005))
                    new_assorb_nastro = max(2.0, min(15.0, new_assorb_nastro))  # Limiti fisici
                    self._write_real(self.db2, 16, new_assorb_nastro)
                    
                    # Assorbimento testine: oscillazione naturale ±5-10% durante RUN
                    # Pattern identico a Multifilo per assorbimento
                    new_assorb_testine = current_assorb_testine * (1 + random.uniform(-0.10, 0.10))
                    new_assorb_testine = max(1.0, min(12.0, new_assorb_testine))  # Limiti fisici 1-12 A
                    self._write_real(self.db2, 28, new_assorb_testine)
                    
                    # Velocità trave: variazione graduale verso il target (simula movimento trave)
                    # Target velocità trave basato sulla velocità nastro (proporzionale)
                    target_velocita_trave = new_velocita * 0.5  # mm/s proporzionale a m/min nastro
                    # Variazione graduale (non salti improvvisi)
                    if abs(current_velocita_trave - target_velocita_trave) > 0.1:
                        # Avvicinamento graduale al target
                        diff = target_velocita_trave - current_velocita_trave
                        new_velocita_trave = current_velocita_trave + (diff * 0.1)  # 10% del gap per ciclo
                    else:
                        new_velocita_trave = target_velocita_trave
                    new_velocita_trave = max(0.0, min(25.0, new_velocita_trave))  # Limiti fisici 0-25 mm/s
                    self._write_real(self.db2, 32, new_velocita_trave)
                    
                    # Metri lavorati: incremento continuo = velocità_trave * delta_tempo (in metri)
                    # velocità_trave è in mm/s, convertiamo in m/s moltiplicando per 0.001
                    incremento_metri = (new_velocita_trave * 0.001) * delta_tempo  # m/s * s = m
                    new_metri = current_metri + incremento_metri
                    self._write_real(self.db2, 20, new_metri)
                    
                    # Produzione oraria: calcolo = metri_lavorati / tempo_attivo (m/h)
                    if self.tempo_attivo_ore > 0:
                        new_produzione_oraria = new_metri / self.tempo_attivo_ore
                    else:
                        new_produzione_oraria = 0.0
                    self._write_real(self.db2, 36, new_produzione_oraria)
                    
                    # Qualità superficie: oscillazione lenta ±0.1% (simula qualità variabile)
                    new_qualita = current_qualita * (1 + random.uniform(-0.001, 0.001))
                    new_qualita = max(85.0, min(100.0, new_qualita))  # Limiti fisici 85-100%
                    self._write_real(self.db2, 24, new_qualita)
                    
                    logger.debug("Parametri simulati aggiornati")
                elif stato == 0:  # Idle (HOLD)
                    # Durante HOLD, parametri rimangono stabili (non tendono a zero)
                    # Assorbimento testine: valore stabile durante HOLD
                    current_assorb_testine = self._read_real(self.db2, 28)
                    # Mantiene valore corrente (non cambia)
                    
                    # Velocità trave: zero durante HOLD
                    self._write_real(self.db2, 32, 0.0)
                    
                    # Altri parametri rimangono invariati durante HOLD
                else:  # Alarm o Error
                    # Durante ERROR, parametri tendono a zero
                    current_velocita = self._read_real(self.db2, 4)
                    if current_velocita > 0.01:
                        self._write_real(self.db2, 4, current_velocita * 0.9)
                    
                    current_pressione = self._read_real(self.db2, 8)
                    if current_pressione > 0.1:
                        self._write_real(self.db2, 8, current_pressione * 0.9)
                    
                    current_assorb_principale = self._read_real(self.db2, 12)
                    if current_assorb_principale > 0.1:
                        self._write_real(self.db2, 12, current_assorb_principale * 0.9)
                    
                    current_assorb_nastro = self._read_real(self.db2, 16)
                    if current_assorb_nastro > 0.1:
                        self._write_real(self.db2, 16, current_assorb_nastro * 0.9)
                    
                    # Assorbimento testine: zero durante ERROR
                    self._write_real(self.db2, 28, 0.0)
                    
                    # Velocità trave: zero durante ERROR
                    self._write_real(self.db2, 32, 0.0)
                
                time.sleep(0.5)  # Aggiorna ogni 500ms
                
            except Exception as e:
                logger.error(f"Errore aggiornamento DB2: {e}")
                time.sleep(0.5)
    
    def _process_commands(self):
        """Processa i comandi da DB3 e aggiorna DB1"""
        # Start
        if self.db3[0] == 1:
            if self.db1[0] == 0:  # Se Idle
                self.db1[0] = 1  # Passa a Run
                # Inizializza valori target per simulazione realistica
                if self._read_real(self.db2, 4) < 0.1:  # Se velocità nastro è zero
                    self._write_real(self.db2, 4, 25.0)  # Imposta velocità nastro iniziale
                if self._read_real(self.db2, 8) < 0.1:  # Se pressione è zero
                    self._write_real(self.db2, 8, 5.0)  # Imposta pressione iniziale
                if self._read_real(self.db2, 12) < 0.1:  # Se assorbimento principale è zero
                    self._write_real(self.db2, 12, 10.0)  # Imposta assorbimento iniziale
                if self._read_real(self.db2, 16) < 0.1:  # Se assorbimento nastro è zero
                    self._write_real(self.db2, 16, 5.0)  # Imposta assorbimento nastro iniziale
                if self._read_real(self.db2, 28) < 0.1:  # Se assorbimento testine è zero
                    self._write_real(self.db2, 28, 6.0)  # Imposta assorbimento testine iniziale
                logger.info("COMANDO: Start → Stato: Run")
            self.db3[0] = 0  # Reset comando
        
        # Stop
        if self.db3[1] == 1:
            if self.db1[0] == 1:  # Se Run
                self.db1[0] = 0  # Passa a Idle
                logger.info("COMANDO: Stop → Stato: Idle")
            self.db3[1] = 0  # Reset comando
        
        # Reset
        if self.db3[2] == 1:
            if self.db1[1] == 1:  # Se c'è allarme
                self.db1[1] = 0  # Reset allarme
                if self.db1[0] == 2:  # Se era in Alarm
                    self.db1[0] = 0  # Passa a Idle
                logger.info("COMANDO: Reset → Allarme resettato")
            # Reset anche contatore pezzi e tempo attivo (opzionale, commentato per non perdere dati)
            # self.tempo_attivo_ore = 0.0
            # self._write_real(self.db2, 40, 0.0)  # Reset contatore pezzi
            self.db3[2] = 0  # Reset comando
    
    def start(self):
        """Avvia il server Snap7"""
        try:
            # Registra i Data Block
            self._register_db(1, DB1_SIZE, self.db1)
            self._register_db(2, DB2_SIZE, self.db2)
            self._register_db(3, DB3_SIZE, self.db3)
            
            # Avvia il server
            self.server.start(102)  # Porta 102 (standard S7)
            logger.info(f"Server Snap7 Lucidatrice avviato su {self.ip}:102 (Rack={self.rack}, Slot={self.slot})")
            logger.info(f"DB1 (Stato): {DB1_SIZE} byte")
            logger.info(f"DB2 (Parametri): {DB2_SIZE} byte")
            logger.info(f"DB3 (Comandi): {DB3_SIZE} byte")
            
            # Avvia thread aggiornamento DB2
            self.running = True
            self.update_thread = threading.Thread(target=self._update_db2_parameters, daemon=True)
            self.update_thread.start()
            
            # Loop principale per processare comandi
            logger.info("Server in esecuzione. Premi Ctrl+C per fermare.")
            while True:
                self._process_commands()
                time.sleep(0.1)  # Controlla comandi ogni 100ms
                
        except KeyboardInterrupt:
            logger.info("Arresto server richiesto dall'utente...")
            self.stop()
        except Exception as e:
            logger.error(f"Errore server: {e}")
            self.stop()
    
    def stop(self):
        """Ferma il server Snap7"""
        self.running = False
        if self.update_thread and self.update_thread.is_alive():
            logger.info("Attesa terminazione thread aggiornamento DB2...")
            self.update_thread.join(timeout=2.0)
            if self.update_thread.is_alive():
                logger.warning("Thread aggiornamento DB2 non terminato in tempo")
        try:
            self.server.stop()
            self.server.destroy()
            logger.info("Server fermato correttamente")
        except Exception as e:
            logger.error(f"Errore durante fermata server: {e}")


def main():
    """Funzione principale"""
    print("=" * 60)
    print("Snap7 Server - Simulazione PLC Lucidatrice/Calibratrice")
    print("=" * 60)
    print()
    
    server = LucidatricePLCServer(ip="127.0.0.1", rack=0, slot=1)
    server.start()


if __name__ == "__main__":
    main()

