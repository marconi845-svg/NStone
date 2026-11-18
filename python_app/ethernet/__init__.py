"""
Modulo Ethernet - Comunicazione PLC Siemens S7-1200/S7-1500 via Ethernet
Predisposto per integrazione con UI e RAG Engine
"""

from .plc_config import (
    PLC_IP, PLC_PORT, PLC_DB_LUCIDATRICE, PLC_DB_MULTIFILO,
    PLC_CONNECTION_TIMEOUT, PLC_MONITOR_INTERVAL_MS
)
from .plc_connection_manager import PlcConnectionManager, ConnectionState
from .plc_status_monitor import PlcStatusMonitor

__all__ = [
    'PLC_IP', 'PLC_PORT', 'PLC_DB_LUCIDATRICE', 'PLC_DB_MULTIFILO',
    'PLC_CONNECTION_TIMEOUT', 'PLC_MONITOR_INTERVAL_MS',
    'PlcConnectionManager', 'ConnectionState', 'PlcStatusMonitor',
]




