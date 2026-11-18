"""
PLC Connection Manager - Gestione connessione, riconnessione e stato PLC Ethernet
Predisposto per PLC Siemens S7-1200/S7-1500
"""

import time
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime, timedelta
from .plc_config import (
    PLC_IP, PLC_PORT, PLC_CONNECTION_TIMEOUT, PLC_RECONNECT_DELAY,
    PLC_MAX_RETRIES, PLC_RETRY_DELAY, PLC_PACKET_TIMEOUT_MS
)

# Import Rust core (quando disponibile)
try:
    import rust_core
    RUST_CORE_AVAILABLE = True
except ImportError:
    RUST_CORE_AVAILABLE = False
    print("⚠ rust_core non disponibile - Modalità offline")


class ConnectionState(Enum):
    """Stati della connessione PLC"""
    DISCONNECTED = "Disconnesso"
    CONNECTING = "In Connessione"
    CONNECTED = "Connesso"
    ERROR = "Errore"
    RECONNECTING = "Riconnessione"


class PlcConnectionManager:
    """
    Manager per gestione connessione PLC Ethernet
    
    Gestisce:
    - Connessione
    - Riconnessione automatica
    - Stato connessione
    - Errori
    - Ping PLC
    - Fallback offline
    """
    
    def __init__(self, ip: str = PLC_IP, port: int = PLC_PORT):
        self.ip = ip
        self.port = port
        self.state = ConnectionState.DISCONNECTED
        self.last_connection_time: Optional[datetime] = None
        self.last_packet_time: Optional[datetime] = None
        self.latency_ms: int = 0
        self.error_count: int = 0
        self.reconnect_attempts: int = 0
        self.last_error: Optional[str] = None
        
        # Statistiche
        self.total_packets: int = 0
        self.failed_packets: int = 0
        self.connection_duration: Optional[timedelta] = None
    
    def connect(self) -> bool:
        """
        Tenta la connessione al PLC
        
        Returns:
            True se connesso, False altrimenti
        """
        self.state = ConnectionState.CONNECTING
        self.last_error = None
        
        if not RUST_CORE_AVAILABLE:
            self.state = ConnectionState.DISCONNECTED
            self.last_error = "rust_core non disponibile"
            return False
        
        try:
            # TODO: Implementare connessione quando rust_core sarà disponibile
            # connected = rust_core.check_plc_connection(self.ip, self.port)
            
            # Per ora, simulazione (non invasiva)
            connected = False
            
            if connected:
                self.state = ConnectionState.CONNECTED
                self.last_connection_time = datetime.now()
                self.last_packet_time = datetime.now()
                self.reconnect_attempts = 0
                self.error_count = 0
                return True
            else:
                self.state = ConnectionState.DISCONNECTED
                self.last_error = "Connessione fallita"
                return False
                
        except Exception as e:
            self.state = ConnectionState.ERROR
            self.last_error = str(e)
            self.error_count += 1
            return False
    
    def disconnect(self):
        """Disconnette dal PLC"""
        self.state = ConnectionState.DISCONNECTED
        self.last_packet_time = None
        if self.last_connection_time:
            self.connection_duration = datetime.now() - self.last_connection_time
    
    def is_connected(self) -> bool:
        """Verifica se è connesso"""
        return self.state == ConnectionState.CONNECTED
    
    def ping(self) -> Optional[int]:
        """
        Esegue ping al PLC
        
        Returns:
            Latenza in ms se riuscito, None altrimenti
        """
        if not self.is_connected():
            return None
        
        if not RUST_CORE_AVAILABLE:
            return None
        
        try:
            # TODO: Implementare ping quando rust_core sarà disponibile
            # latency = rust_core.ping_plc(self.ip, self.port)
            
            # Per ora, simulazione
            latency = 0
            
            if latency is not None:
                self.latency_ms = latency
                self.last_packet_time = datetime.now()
                self.total_packets += 1
                return latency
            else:
                self.failed_packets += 1
                return None
                
        except Exception as e:
            self.failed_packets += 1
            self.last_error = f"Ping fallito: {e}"
            return None
    
    def reconnect(self) -> bool:
        """
        Tenta riconnessione automatica
        
        Returns:
            True se riconnesso, False altrimenti
        """
        self.state = ConnectionState.RECONNECTING
        self.reconnect_attempts += 1
        
        time.sleep(PLC_RECONNECT_DELAY)
        
        return self.connect()
    
    def auto_reconnect(self) -> bool:
        """
        Riconnessione automatica con retry
        
        Returns:
            True se riconnesso, False altrimenti
        """
        for attempt in range(PLC_MAX_RETRIES):
            if self.reconnect():
                return True
            if attempt < PLC_MAX_RETRIES - 1:
                time.sleep(PLC_RETRY_DELAY)
        
        return False
    
    def check_timeout(self) -> bool:
        """
        Verifica se la connessione è in timeout
        
        Returns:
            True se in timeout, False altrimenti
        """
        if not self.last_packet_time:
            return False
        
        timeout_delta = timedelta(milliseconds=PLC_PACKET_TIMEOUT_MS)
        if datetime.now() - self.last_packet_time > timeout_delta:
            return True
        
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Ottiene lo stato completo della connessione
        
        Returns:
            Dizionario con stato, latenza, errori, ecc.
        """
        return {
            "state": self.state.value,
            "ip": self.ip,
            "port": self.port,
            "connected": self.is_connected(),
            "latency_ms": self.latency_ms,
            "last_packet_time": self.last_packet_time.isoformat() if self.last_packet_time else None,
            "last_connection_time": self.last_connection_time.isoformat() if self.last_connection_time else None,
            "error_count": self.error_count,
            "reconnect_attempts": self.reconnect_attempts,
            "last_error": self.last_error,
            "total_packets": self.total_packets,
            "failed_packets": self.failed_packets,
            "timeout": self.check_timeout(),
        }
    
    def update_packet_time(self):
        """Aggiorna il timestamp dell'ultimo pacchetto"""
        self.last_packet_time = datetime.now()
        self.total_packets += 1




