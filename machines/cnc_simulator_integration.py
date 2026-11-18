"""
Integrazione Simulatore CNC con UI
Pattern identico a multifilo_snap7_integration.py e lucidatrice_snap7_integration.py
"""
import sys
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from PyQt5.QtCore import QTimer, QObject, pyqtSignal, QThread, QMutex
from PyQt5.QtWidgets import QMessageBox

try:
    from machines.cnc_simulator import get_simulator, CNCSimulatorStatus, MachineState, CNCAxisPosition
    SIMULATOR_AVAILABLE = True
except ImportError:
    SIMULATOR_AVAILABLE = False
    print("⚠ Modulo cnc_simulator non disponibile")


class CNCSimulatorWorker(QThread):
    """Worker thread per leggere dati simulatore ogni 100ms - Pattern identico a Multifilo/Lucidatrice"""
    
    status_updated = pyqtSignal(object)  # Emette CNCSimulatorStatus
    connection_changed = pyqtSignal(bool)  # Emette stato connessione
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.simulator = None
        self.running = False
        self.mutex = QMutex()
        self.status = None
    
    def run(self):
        """Loop di lettura simulatore"""
        if not SIMULATOR_AVAILABLE:
            print("⚠ Simulatore CNC non disponibile, worker non avviato")
            return
        
        try:
            self.simulator = get_simulator()
            # Avvia simulatore se non è già in esecuzione
            if not self.simulator.running:
                self.simulator.start()
            
            self.running = True
            self.connection_changed.emit(True)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Simulatore CNC connesso e attivo")
            
            while self.running:
                try:
                    self.mutex.lock()
                    
                    # Leggi stato simulatore
                    self.status = self.simulator.get_status()
                    
                    # Emetti segnale aggiornamento
                    if self.status:
                        self.status_updated.emit(self.status)
                    
                    self.mutex.unlock()
                    
                    # Attendi 100ms
                    self.msleep(100)
                    
                except Exception as e:
                    print(f"⚠ Errore lettura simulatore: {e}")
                    self.mutex.unlock()
                    self.msleep(100)
        
        except Exception as e:
            print(f"⚠ Errore worker simulatore: {e}")
            self.connection_changed.emit(False)
        finally:
            self.running = False
    
    def stop(self):
        """Ferma il worker"""
        self.running = False
        self.wait(1000)  # Timeout 1s
    
    def get_status(self):
        """Restituisce stato corrente (per uso sincrono)"""
        self.mutex.lock()
        status = self.status
        self.mutex.unlock()
        return status


class CNCSimulatorUpdater(QObject):
    """Updater per integrazione simulatore CNC con UI - Pattern identico a Multifilo/Lucidatrice"""
    
    status_updated = pyqtSignal(object)  # Emette CNCSimulatorStatus
    connection_changed = pyqtSignal(bool)  # Emette stato connessione
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.timer = None
        self.log_enabled = True
    
    def start(self, interval_ms: int = 100):
        """Avvia aggiornamento simulatore"""
        if not SIMULATOR_AVAILABLE:
            print("⚠ Simulatore CNC non disponibile")
            return
        
        try:
            # Crea worker thread
            self.worker = CNCSimulatorWorker(parent=self)
            self.worker.status_updated.connect(self.status_updated.emit)
            self.worker.connection_changed.connect(self.connection_changed.emit)
            
            # Avvia worker
            self.worker.start()
            
            if self.log_enabled:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Simulatore CNC avviato (intervallo: {interval_ms}ms)")
        
        except Exception as e:
            print(f"⚠ Errore avvio simulatore: {e}")
    
    def stop(self):
        """Ferma aggiornamento simulatore"""
        if self.worker:
            self.worker.stop()
            self.worker = None
        
        if self.timer:
            self.timer.stop()
            self.timer = None
    
    def send_start(self) -> bool:
        """Invia comando Start al simulatore"""
        if not SIMULATOR_AVAILABLE:
            return False
        
        try:
            simulator = get_simulator()
            simulator.set_machine_state(MachineState.RUN)
            if self.log_enabled:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COMANDO: Start → Stato: RUN")
            return True
        except Exception as e:
            print(f"⚠ Errore comando Start: {e}")
            return False
    
    def send_stop(self) -> bool:
        """Invia comando Stop al simulatore"""
        if not SIMULATOR_AVAILABLE:
            return False
        
        try:
            simulator = get_simulator()
            simulator.set_machine_state(MachineState.STOP)
            if self.log_enabled:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COMANDO: Stop → Stato: STOP")
            return True
        except Exception as e:
            print(f"⚠ Errore comando Stop: {e}")
            return False
    
    def send_hold(self) -> bool:
        """Invia comando Hold al simulatore"""
        if not SIMULATOR_AVAILABLE:
            return False
        
        try:
            simulator = get_simulator()
            simulator.set_machine_state(MachineState.HOLD)
            if self.log_enabled:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COMANDO: Hold → Stato: HOLD")
            return True
        except Exception as e:
            print(f"⚠ Errore comando Hold: {e}")
            return False
    
    def send_reset(self) -> bool:
        """Invia comando Reset al simulatore"""
        if not SIMULATOR_AVAILABLE:
            return False
        
        try:
            simulator = get_simulator()
            simulator.reset()
            simulator.set_machine_state(MachineState.READY)
            if self.log_enabled:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] COMANDO: Reset → Stato: READY")
            return True
        except Exception as e:
            print(f"⚠ Errore comando Reset: {e}")
            return False
    
    def get_current_status(self) -> Optional[CNCSimulatorStatus]:
        """Restituisce lo stato corrente (per uso sincrono)"""
        if self.worker:
            return self.worker.get_status()
        return None
    
    def is_connected(self) -> bool:
        """Verifica se il simulatore è connesso"""
        return SIMULATOR_AVAILABLE and self.worker is not None and self.worker.running

