"""
PLC Status Monitor - Thread dedicato per monitoraggio stato PLC
Aggiorna UI ogni 100ms e segnala disconnessioni
"""

import time
import threading
from typing import Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal
from .plc_connection_manager import PlcConnectionManager, ConnectionState
from .plc_config import PLC_MONITOR_INTERVAL_MS

# Import Rust core (quando disponibile)
try:
    import rust_core
    RUST_CORE_AVAILABLE = True
except ImportError:
    RUST_CORE_AVAILABLE = False
    print("⚠ rust_core non disponibile - Modalità offline")


class PlcStatusMonitor(QObject):
    """
    Monitor per stato PLC con aggiornamento automatico
    
    Thread dedicato che:
    - Ogni 100ms → chiama Rust
    - Aggiorna UI
    - Aggiorna indicatori
    - Segnala disconnessioni
    """
    
    # Segnali Qt
    status_updated = pyqtSignal(dict)  # Emette stato aggiornato
    connection_changed = pyqtSignal(bool)  # Emette quando connessione cambia
    error_occurred = pyqtSignal(str)  # Emette quando si verifica un errore
    
    def __init__(self, connection_manager: PlcConnectionManager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Callback personalizzati
        self.on_status_update: Optional[Callable] = None
        self.on_connection_change: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
    
    def start(self, interval_ms: int = PLC_MONITOR_INTERVAL_MS):
        """
        Avvia il monitoraggio
        
        Args:
            interval_ms: Intervallo aggiornamento in millisecondi
        """
        if self.monitoring:
            return
        
        self.monitoring = True
        self.stop_event.clear()
        
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval_ms / 1000.0,),  # Converti in secondi
            daemon=True
        )
        self.monitor_thread.start()
    
    def stop(self):
        """Ferma il monitoraggio"""
        self.monitoring = False
        self.stop_event.set()
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
    
    def _monitor_loop(self, interval: float):
        """Loop principale di monitoraggio"""
        last_connection_state = None
        
        while self.monitoring and not self.stop_event.is_set():
            try:
                # Verifica timeout
                if self.connection_manager.check_timeout():
                    if self.connection_manager.is_connected():
                        self.connection_manager.disconnect()
                        self.connection_changed.emit(False)
                        if self.on_connection_change:
                            self.on_connection_change(False)
                
                # Esegui ping se connesso
                if self.connection_manager.is_connected():
                    latency = self.connection_manager.ping()
                    if latency is None:
                        # Ping fallito, tenta riconnessione
                        if not self.connection_manager.auto_reconnect():
                            self.error_occurred.emit("Connessione persa")
                            if self.on_error:
                                self.on_error("Connessione persa")
                else:
                    # Tenta connessione se disconnesso
                    if self.connection_manager.state == ConnectionState.DISCONNECTED:
                        self.connection_manager.connect()
                
                # Verifica cambio stato connessione
                current_state = self.connection_manager.is_connected()
                if last_connection_state != current_state:
                    self.connection_changed.emit(current_state)
                    if self.on_connection_change:
                        self.on_connection_change(current_state)
                    last_connection_state = current_state
                
                # Ottieni stato completo
                status = self.connection_manager.get_status()
                
                # Emetti segnale
                self.status_updated.emit(status)
                
                # Callback personalizzato
                if self.on_status_update:
                    self.on_status_update(status)
                
            except Exception as e:
                error_msg = f"Errore monitoraggio PLC: {e}"
                self.error_occurred.emit(error_msg)
                if self.on_error:
                    self.on_error(error_msg)
            
            # Attendi intervallo
            time.sleep(interval)
    
    def set_status_callback(self, callback: Callable):
        """Imposta callback per aggiornamenti stato"""
        self.on_status_update = callback
    
    def set_connection_callback(self, callback: Callable):
        """Imposta callback per cambi connessione"""
        self.on_connection_change = callback
    
    def set_error_callback(self, callback: Callable):
        """Imposta callback per errori"""
        self.on_error = callback




