"""
Snap7 Client - Client Python per comunicazione con PLC Multifilo simulato
Usato dal Motore Neurale per leggere/scrivere dati dal PLC
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
    
    # Prova a caricare la DLL
    snap7_dll_loaded = False
    for dll_path in snap7_dll_paths:
        if dll_path.exists():
            try:
                ctypes.CDLL(str(dll_path))
                snap7_dll_loaded = True
                break
            except Exception:
                continue

import snap7
import struct
import time
from typing import Optional, Tuple
from datetime import datetime


class MultifiloPLCClient:
    """Client Snap7 per comunicazione con PLC Multifilo"""
    
    def __init__(self, ip: str = "127.0.0.1", rack: int = 0, slot: int = 1, timeout: int = 3000):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.timeout = timeout
        self.client = snap7.client.Client()
        self.connected = False
        
        # Configura timeout (opzionale, compatibile con python-snap7 2.0.2)
        try:
            # Prova a impostare il timeout PDU se disponibile
            if hasattr(snap7, 'snap7types') and hasattr(snap7.snap7types, 'PDURequest'):
                self.client.set_param(snap7.snap7types.PDURequest, timeout)
        except (AttributeError, Exception):
            # Se set_param non è disponibile o fallisce, continua senza timeout esplicito
            # Il timeout sarà gestito dalla connessione stessa
            pass
    
    def connect(self) -> bool:
        """
        Connetti al PLC
        
        Returns:
            True se connesso, False altrimenti
        """
        try:
            self.client.connect(self.ip, self.rack, self.slot)
            self.connected = True
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connesso a PLC {self.ip}")
            return True
        except Exception as e:
            self.connected = False
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Errore connessione: {e}")
            return False
    
    def disconnect(self):
        """Disconnetti dal PLC"""
        try:
            if self.connected:
                self.client.disconnect()
                self.connected = False
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Disconnesso da PLC")
        except Exception as e:
            print(f"Errore disconnessione: {e}")
    
    def is_connected(self) -> bool:
        """Verifica se è connesso"""
        if not self.connected:
            return False
        try:
            return self.client.get_connected()
        except:
            self.connected = False
            return False
    
    def reconnect(self) -> bool:
        """Riconnessione automatica"""
        self.disconnect()
        time.sleep(0.5)
        return self.connect()
    
    def _read_bytes(self, db_number: int, offset: int, size: int) -> Optional[bytearray]:
        """Legge bytes da un DB"""
        if not self.is_connected():
            if not self.reconnect():
                return None
        
        try:
            data = self.client.db_read(db_number, offset, size)
            return data
        except Exception as e:
            print(f"Errore lettura DB{db_number} offset {offset}: {e}")
            self.connected = False
            return None
    
    def _write_bytes(self, db_number: int, offset: int, data: bytearray) -> bool:
        """Scrive bytes in un DB"""
        if not self.is_connected():
            if not self.reconnect():
                return False
        
        try:
            self.client.db_write(db_number, offset, data)
            return True
        except Exception as e:
            print(f"Errore scrittura DB{db_number} offset {offset}: {e}")
            self.connected = False
            return False
    
    def _read_real(self, db_number: int, offset: int) -> Optional[float]:
        """Legge un valore REAL (32-bit float)"""
        data = self._read_bytes(db_number, offset, 4)
        if data is None:
            return None
        return struct.unpack('>f', data)[0]
    
    def _write_byte(self, db_number: int, offset: int, value: int) -> bool:
        """Scrive un byte"""
        data = bytearray([value])
        return self._write_bytes(db_number, offset, data)
    
    # ========== DB1: Stato Macchina ==========
    
    def read_status(self) -> Optional[int]:
        """
        Legge lo stato generale della macchina (DB1, Byte 0)
        
        Returns:
            0=Idle, 1=Run, 2=Alarm, None se errore
        """
        data = self._read_bytes(1, 0, 1)
        if data is None:
            return None
        return int(data[0])
    
    def read_alarm_active(self) -> Optional[bool]:
        """Legge se c'è allarme attivo (DB1, Byte 1)"""
        data = self._read_bytes(1, 1, 1)
        if data is None:
            return None
        return bool(data[0])
    
    def read_emergency(self) -> Optional[bool]:
        """Legge se c'è emergenza (DB1, Byte 2)"""
        data = self._read_bytes(1, 2, 1)
        if data is None:
            return None
        return bool(data[0])
    
    def read_doors_open(self) -> Optional[bool]:
        """Legge se le porte sono aperte (DB1, Byte 3)"""
        data = self._read_bytes(1, 3, 1)
        if data is None:
            return None
        return bool(data[0])
    
    def read_db1_all(self) -> Optional[dict]:
        """Legge tutti i dati di DB1"""
        data = self._read_bytes(1, 0, 4)
        if data is None:
            return None
        
        return {
            "stato": int(data[0]),  # 0=Idle, 1=Run, 2=Alarm
            "allarme_attivo": bool(data[1]),
            "emergenza": bool(data[2]),
            "porte_aperte": bool(data[3])
        }
    
    # ========== DB2: Parametri Macchina ==========
    
    def read_wire_speed(self) -> Optional[float]:
        """Legge velocità filo (DB2, Real 0) in m/s"""
        return self._read_real(2, 0)
    
    def read_tension(self) -> Optional[float]:
        """Legge tensione filo (DB2, Real 4) in N"""
        return self._read_real(2, 4)
    
    def read_pressure(self) -> Optional[float]:
        """Legge pressione acqua (DB2, Real 8) in bar"""
        return self._read_real(2, 8)
    
    def read_current(self) -> Optional[float]:
        """Legge assorbimento motore (DB2, Real 12) in A"""
        return self._read_real(2, 12)
    
    def read_db2_all(self) -> Optional[dict]:
        """Legge tutti i parametri di DB2 (28 byte = 7 Real)"""
        data = self._read_bytes(2, 0, 28)
        if data is None:
            return None
        
        return {
            "velocita_filo": struct.unpack('>f', data[0:4])[0],      # m/s (offset 0-3)
            "tensione_filo": struct.unpack('>f', data[4:8])[0],     # N (offset 4-7)
            "pressione_acqua": struct.unpack('>f', data[8:12])[0],  # bar (offset 8-11)
            "assorbimento_motore": struct.unpack('>f', data[12:16])[0],  # A (offset 12-15)
            "metri": struct.unpack('>f', data[16:20])[0],           # metri tagliati (offset 16-19)
            "spreco": struct.unpack('>f', data[20:24])[0],          # spreco % (offset 20-23)
            "deviazione": struct.unpack('>f', data[24:28])[0]       # deviazione mm (offset 24-27)
        }
    
    # ========== DB3: Comandi Macchina ==========
    
    def write_start(self) -> bool:
        """Scrive comando Start (DB3, Byte 0 = 1)"""
        return self._write_byte(3, 0, 1)
    
    def write_stop(self) -> bool:
        """Scrive comando Stop (DB3, Byte 1 = 1)"""
        return self._write_byte(3, 1, 1)
    
    def write_reset(self) -> bool:
        """Scrive comando Reset (DB3, Byte 2 = 1)"""
        return self._write_byte(3, 2, 1)
    
    def read_db3_all(self) -> Optional[dict]:
        """Legge tutti i comandi di DB3"""
        data = self._read_bytes(3, 0, 3)
        if data is None:
            return None
        
        return {
            "start": bool(data[0]),
            "stop": bool(data[1]),
            "reset": bool(data[2])
        }


def main():
    """Test del client"""
    print("=" * 60)
    print("Snap7 Client - Test Connessione PLC Multifilo")
    print("=" * 60)
    print()
    
    client = MultifiloPLCClient(ip="127.0.0.1", rack=0, slot=1)
    
    if not client.connect():
        print("❌ Impossibile connettersi al PLC")
        print("   Assicurati che il server Snap7 sia in esecuzione")
        return
    
    print("\n✓ Connesso al PLC\n")
    
    try:
        # Test lettura DB1
        print("--- DB1: Stato Macchina ---")
        db1 = client.read_db1_all()
        if db1:
            print(f"Stato: {db1['stato']} ({'Idle' if db1['stato'] == 0 else 'Run' if db1['stato'] == 1 else 'Alarm'})")
            print(f"Allarme attivo: {db1['allarme_attivo']}")
            print(f"Emergenza: {db1['emergenza']}")
            print(f"Porte aperte: {db1['porte_aperte']}")
        
        # Test lettura DB2
        print("\n--- DB2: Parametri Macchina ---")
        db2 = client.read_db2_all()
        if db2:
            print(f"Velocità filo: {db2['velocita_filo']:.2f} m/s")
            print(f"Tensione filo: {db2['tensione_filo']:.2f} N")
            print(f"Pressione acqua: {db2['pressione_acqua']:.2f} bar")
            print(f"Assorbimento motore: {db2['assorbimento_motore']:.2f} A")
        
        # Test comandi
        print("\n--- DB3: Comandi ---")
        print("Invio comando Start...")
        if client.write_start():
            print("✓ Comando Start inviato")
            time.sleep(0.5)
            
            db1 = client.read_db1_all()
            if db1:
                print(f"Nuovo stato: {db1['stato']}")
        
        time.sleep(1)
        
        print("\nInvio comando Stop...")
        if client.write_stop():
            print("✓ Comando Stop inviato")
            time.sleep(0.5)
            
            db1 = client.read_db1_all()
            if db1:
                print(f"Nuovo stato: {db1['stato']}")
        
    except KeyboardInterrupt:
        print("\n\nInterrotto dall'utente")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()

