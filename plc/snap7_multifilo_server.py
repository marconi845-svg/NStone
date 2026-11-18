"""
Snap7 Server - Simulazione PLC Multifilo
Simula un PLC Siemens S7-1200/S7-1500 per testare il Motore Neurale

DB1: Stato macchina (4 byte)
- Byte 0: Stato generale (0=Idle, 1=Run, 2=Alarm)
- Byte 1: Allarme attivo (0=No, 1=Sì)
- Byte 2: Emergenza (0=No, 1=Sì)
- Byte 3: Porte aperte (0=No, 1=Sì)

DB2: Parametri macchina (16 byte = 4 Real)
- Real 0: Velocità filo (m/s)
- Real 4: Tensione filo (N)
- Real 8: Pressione acqua (bar)
- Real 12: Assorbimento motore (A)

DB3: Comandi macchina (3 byte)
- Byte 0: Start (1=Start)
- Byte 1: Stop (1=Stop)
- Byte 2: Reset (1=Reset)
"""

import sys
import os
import ctypes
from pathlib import Path

# Carica snap7.dll esplicitamente prima di importare snap7
# Questo è necessario per gli eseguibili PyInstaller standalone
if getattr(sys, 'frozen', False):
    # Eseguibile compilato con PyInstaller
    base_dir = Path(sys.executable).parent
    meipass_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else None
    
    # Cerca snap7.dll in tutti i percorsi possibili
    snap7_dll_paths = []
    
    # Prima cerca nella directory temporanea di PyInstaller (_MEIPASS)
    if meipass_dir:
        snap7_dll_paths.extend([
            meipass_dir / 'bin' / 'snap7.dll',
            meipass_dir / 'snap7.dll',
        ])
    
    # Poi cerca nella directory dell'eseguibile
    snap7_dll_paths.extend([
        base_dir / 'snap7.dll',  # PRIMA cerca nella root (più semplice e diretto)
        base_dir / 'bin' / 'snap7.dll',
        base_dir / '_internal' / 'bin' / 'snap7.dll',  # Fallback a dove PyInstaller la mette
        base_dir / '_internal' / 'snap7.dll',
    ])
    
    # Aggiungi tutte le directory possibili al PATH delle DLL
    dll_dirs = set()
    if meipass_dir:
        dll_dirs.add(str(meipass_dir))
        if (meipass_dir / 'bin').exists():
            dll_dirs.add(str(meipass_dir / 'bin'))
    # Aggiungi _internal/bin (dove PyInstaller mette le DLL per gli eseguibili standalone)
    if (base_dir / '_internal' / 'bin').exists():
        dll_dirs.add(str(base_dir / '_internal' / 'bin'))
    if (base_dir / '_internal').exists():
        dll_dirs.add(str(base_dir / '_internal'))
    if (base_dir / 'bin').exists():
        dll_dirs.add(str(base_dir / 'bin'))
    dll_dirs.add(str(base_dir))
    
    for dll_dir in dll_dirs:
        try:
            os.add_dll_directory(dll_dir)
        except Exception:
            pass
else:
    # Script Python normale
    base_dir = Path(__file__).parent
    snap7_dll_paths = [
        base_dir / 'bin' / 'snap7.dll',  # PRIMA cerca in bin/
        base_dir / 'snap7.dll',
    ]

# Prova a caricare la DLL
snap7_dll_loaded = False
loaded_dll_path = None
for dll_path in snap7_dll_paths:
    if dll_path.exists():
        try:
            ctypes.CDLL(str(dll_path))
            snap7_dll_loaded = True
            loaded_dll_path = str(dll_path)
            break
        except Exception as e:
            continue

# Log per debug
if getattr(sys, 'frozen', False):
    import logging
    logger = logging.getLogger(__name__)
    if snap7_dll_loaded:
        logger.info(f"snap7.dll caricata da: {loaded_dll_path}")
    else:
        logger.warning(f"snap7.dll non trovata. Percorsi cercati: {[str(p) for p in snap7_dll_paths]}")

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
DB1_SIZE = 4  # Stato macchina (4 byte)
DB2_SIZE = 28  # Parametri (28 byte = 7 Real: velocità, tensione, pressione, assorbimento, metri, spreco, deviazione)
DB3_SIZE = 3  # Comandi (3 byte)

# Verifica che le dimensioni siano valide (> 0)
assert DB1_SIZE > 0, "DB1_SIZE deve essere > 0"
assert DB2_SIZE > 0, "DB2_SIZE deve essere > 0"
assert DB3_SIZE > 0, "DB3_SIZE deve essere > 0"

# Valori iniziali DB2
INITIAL_WIRE_SPEED = 0.0  # m/s
INITIAL_TENSION = 0.0  # N
INITIAL_PRESSURE = 0.0  # bar
INITIAL_CURRENT = 0.0  # A
INITIAL_METRI = 0.0  # metri tagliati
INITIAL_SPRECO = 0.0  # spreco (%)
INITIAL_DEVIAZIONE = 0.0  # deviazione (mm)


class MultifiloPLCServer:
    """Server Snap7 che simula il PLC Multifilo"""
    
    def __init__(self, ip: str = "127.0.0.1", rack: int = 0, slot: int = 1):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.server = snap7.server.Server()
        
        # Buffer per i DB - Inizializzati con dimensioni corrette
        # Verifica che le dimensioni siano valide prima di creare i bytearray
        if DB1_SIZE <= 0 or DB2_SIZE <= 0 or DB3_SIZE <= 0:
            raise ValueError(f"Dimensioni DB non valide: DB1={DB1_SIZE}, DB2={DB2_SIZE}, DB3={DB3_SIZE}")
        
        # Crea bytearray per i DB (python-snap7 2.0.2 richiede bytearray)
        # I bytearray devono essere inizializzati con dimensione > 0
        self.db1 = bytearray(DB1_SIZE)  # Stato macchina (4 byte)
        self.db2 = bytearray(DB2_SIZE)  # Parametri (16 byte)
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
        self.db1[3] = 0  # Porte: Chiuse
        
        # Inizializza DB2 (Parametri a zero)
        self._write_real(self.db2, 0, INITIAL_WIRE_SPEED)   # Velocità filo (offset 0-3)
        self._write_real(self.db2, 4, INITIAL_TENSION)     # Tensione filo (offset 4-7)
        self._write_real(self.db2, 8, INITIAL_PRESSURE)     # Pressione acqua (offset 8-11)
        self._write_real(self.db2, 12, INITIAL_CURRENT)    # Assorbimento motore (offset 12-15)
        self._write_real(self.db2, 16, INITIAL_METRI)       # Metri tagliati (offset 16-19)
        self._write_real(self.db2, 20, INITIAL_SPRECO)      # Spreco (offset 20-23)
        self._write_real(self.db2, 24, INITIAL_DEVIAZIONE)  # Deviazione (offset 24-27)
        
        # Inizializza DB3 (Comandi a zero)
        self.db3[0] = 0  # Start
        self.db3[1] = 0  # Stop
        self.db3[2] = 0  # Reset
        
        # Thread per aggiornamento DB2
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        
        # Nota: python-snap7 2.0.2 non supporta più set_callback()
        # Il server funziona correttamente senza callback.
        # La funzione _server_callback è mantenuta per compatibilità futura
        # ma non viene registrata.
        # self.server.set_callback(self._server_callback)  # Non supportato in python-snap7 2.0.2
    
    def _write_real(self, buffer: bytearray, offset: int, value: float):
        """Scrive un valore REAL (32-bit float) nel buffer"""
        struct.pack_into('>f', buffer, offset, value)
    
    def _read_real(self, buffer: bytearray, offset: int) -> float:
        """Legge un valore REAL (32-bit float) dal buffer"""
        return struct.unpack_from('>f', buffer, offset)[0]
    
    def _server_callback(self, event: int, param: int):
        """Callback per eventi del server Snap7"""
        if event == snap7.server.srvEventClientConnect:
            logger.info(f"Client connesso (param={param})")
        elif event == snap7.server.srvEventClientDisconnect:
            logger.info(f"Client disconnesso (param={param})")
        elif event == snap7.server.srvEventRead:
            logger.debug(f"Lettura DB{param}")
        elif event == snap7.server.srvEventWrite:
            logger.debug(f"Scrittura DB{param}")
    
    def _register_db(self, db_number: int, size: int, buffer: bytearray):
        """Registra un Data Block nel server"""
        # Verifica che il buffer sia valido e abbia dimensione corretta
        if buffer is None:
            raise ValueError(f"Buffer DB{db_number} è None")
        if not isinstance(buffer, bytearray):
            raise TypeError(f"Buffer DB{db_number} deve essere bytearray, trovato: {type(buffer)}")
        if len(buffer) != size:
            raise ValueError(f"Buffer DB{db_number} dimensione errata: {len(buffer)} != {size}")
        if len(buffer) == 0:
            raise ValueError(f"Buffer DB{db_number} ha dimensione 0")
        
        # python-snap7 2.0.2 richiede parametri posizionali per register_area()
        # IMPORTANTE: register_area() richiede:
        # 1. area: enum SrvArea (non intero!) - usa snap7.server.SrvArea.DB
        # 2. index: numero DB (1, 2, 3, ...)
        # 3. data: array ctypes (c_ubyte * size), non bytearray
        # Convertiamo il bytearray in un array ctypes per compatibilità con la libreria C
        try:
            # Usa enum SrvArea.DB invece di 0x84 (intero)
            area_enum = snap7.server.SrvArea.DB
            
            # Converti bytearray in array ctypes per compatibilità con snap7 C library
            # from_buffer() crea un array ctypes che condivide la memoria con il bytearray
            ctypes_buffer = (ctypes.c_ubyte * size).from_buffer(buffer)
            
            # Registra l'area usando l'enum e l'array ctypes
            self.server.register_area(area_enum, db_number, ctypes_buffer)
            logger.info(f"DB{db_number} registrato (dimensione: {size} byte)")
        except Exception as e:
            logger.error(f"Errore registrazione DB{db_number}: {e}")
            logger.error(f"Tipo buffer: {type(buffer)}, Dimensione: {len(buffer)}")
            logger.error(f"Area enum: {snap7.server.SrvArea.DB if hasattr(snap7.server, 'SrvArea') else 'N/A'}, Index: {db_number}")
            raise
    
    def _update_db2_parameters(self):
        """Aggiorna i parametri DB2 ogni 500ms con variazioni casuali"""
        while self.running:
            try:
                # Leggi stato corrente
                stato = self.db1[0]
                
                # Se la macchina è in Run, aggiorna i parametri con oscillazioni percentuali realistiche
                if stato == 1:  # Run
                    # Leggi valori attuali
                    current_speed = self._read_real(self.db2, 0)
                    current_tension = self._read_real(self.db2, 4)
                    current_pressure = self._read_real(self.db2, 8)
                    current_current = self._read_real(self.db2, 12)
                    current_metri = self._read_real(self.db2, 16)
                    current_spreco = self._read_real(self.db2, 20)
                    
                    # Velocità filo: oscillazione ±3% (simula variazioni naturali del processo)
                    new_speed = current_speed * (1 + random.uniform(-0.03, 0.03))
                    new_speed = max(0.0, min(2.5, new_speed))  # Limiti fisici
                    self._write_real(self.db2, 0, new_speed)
                    
                    # Tensione filo: oscillazione ±2% (variazioni di carico)
                    new_tension = current_tension * (1 + random.uniform(-0.02, 0.02))
                    new_tension = max(50.0, min(200.0, new_tension))  # Limiti fisici
                    self._write_real(self.db2, 4, new_tension)
                    
                    # Pressione acqua: oscillazione lenta ±1% (sistema idraulico stabile)
                    new_pressure = current_pressure * (1 + random.uniform(-0.01, 0.01))
                    new_pressure = max(2.0, min(8.0, new_pressure))  # Limiti fisici
                    self._write_real(self.db2, 8, new_pressure)
                    
                    # Assorbimento motore: micro-rumore ±0.5% (rumore elettrico)
                    new_current = current_current * (1 + random.uniform(-0.005, 0.005))
                    new_current = max(5.0, min(15.0, new_current))  # Limiti fisici
                    self._write_real(self.db2, 12, new_current)
                    
                    # Metri tagliati: incremento proporzionale alla velocità (metri += velocità * 0.05)
                    # 0.05 = fattore di conversione (velocità m/s * tempo ciclo 0.5s * fattore = metri)
                    new_metri = current_metri + (new_speed * 0.05)
                    self._write_real(self.db2, 16, new_metri)
                    
                    # Spreco: incremento lento casuale (spreco += random.uniform(0, 0.02))
                    new_spreco = current_spreco + random.uniform(0, 0.02)
                    new_spreco = max(0.0, min(100.0, new_spreco))  # Limite max 100%
                    self._write_real(self.db2, 20, new_spreco)
                    
                    # Deviazione: oscillazione casuale (deviazione = random.uniform(-2.0, 2.0))
                    new_deviazione = random.uniform(-2.0, 2.0)  # mm
                    self._write_real(self.db2, 24, new_deviazione)
                    
                    # Log opzionale per debug
                    logger.debug("Parametri simulati aggiornati")
                else:
                    # Se Idle o Alarm, parametri tendono a zero
                    current_speed = self._read_real(self.db2, 0)
                    if current_speed > 0.01:
                        self._write_real(self.db2, 0, current_speed * 0.9)
                    
                    current_tension = self._read_real(self.db2, 4)
                    if current_tension > 1.0:
                        self._write_real(self.db2, 4, current_tension * 0.9)
                    
                    current_pressure = self._read_real(self.db2, 8)
                    if current_pressure > 0.1:
                        self._write_real(self.db2, 8, current_pressure * 0.9)
                    
                    current_current = self._read_real(self.db2, 12)
                    if current_current > 0.1:
                        self._write_real(self.db2, 12, current_current * 0.9)
                
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
            self.db3[2] = 0  # Reset comando
    
    def start(self):
        """Avvia il server Snap7"""
        try:
            # Registra i Data Block
            self._register_db(1, DB1_SIZE, self.db1)
            self._register_db(2, DB2_SIZE, self.db2)
            self._register_db(3, DB3_SIZE, self.db3)
            
            # Avvia il server
            # python-snap7 2.0.2: start() richiede il parametro posizionale, non keyword argument
            self.server.start(102)  # Porta 102 (standard S7)
            logger.info(f"Server Snap7 avviato su {self.ip}:102 (Rack={self.rack}, Slot={self.slot})")
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
    print("Snap7 Server - Simulazione PLC Multifilo")
    print("=" * 60)
    print()
    
    server = MultifiloPLCServer(ip="127.0.0.1", rack=0, slot=1)
    server.start()


if __name__ == "__main__":
    main()

