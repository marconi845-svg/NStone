"""
CNC Adapter - Modulo per compatibilità universale con controlli CNC
Supporta: Siemens 840D, Fanuc FOCAS, Heidenhain TNC, Syntec, OSAI, CNC cinesi aperti
"""

from typing import Dict, Optional, Any, List
from enum import Enum
from dataclasses import dataclass


class CNCControlType(Enum):
    """Tipi di controllo CNC supportati"""
    SIEMENS_840D = "Siemens 840D"
    FANUC_FOCAS = "Fanuc FOCAS"
    HEIDENHAIN_TNC = "Heidenhain TNC"
    SYNTEC = "Syntec"
    OSAI = "OSAI"
    CHINESE_OPEN = "CNC Cinese Aperto"
    GENERIC_PLC = "PLC Generico Aperto"


class MachineState(Enum):
    """Stati macchina universali"""
    RUN = "RUN"
    STOP = "STOP"
    HOLD = "HOLD"
    ALARM = "ALARM"
    JOG = "JOG"
    MDI = "MDI"
    UNKNOWN = "UNKNOWN"


@dataclass
class CNCAxisPosition:
    """Posizione assi CNC"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    a: float = 0.0  # Rotazione X
    b: float = 0.0  # Rotazione Y
    c: float = 0.0  # Rotazione Z
    u: float = 0.0  # Asse aggiuntivo
    v: float = 0.0  # Asse aggiuntivo
    w: float = 0.0  # Asse aggiuntivo


@dataclass
class CNCStatus:
    """Stato completo macchina CNC"""
    # Stato macchina
    machine_state: MachineState = MachineState.UNKNOWN
    
    # Posizioni assi
    position: CNCAxisPosition = None
    position_relative: CNCAxisPosition = None
    position_machine: CNCAxisPosition = None
    
    # Spindle
    spindle_speed: float = 0.0  # RPM
    spindle_speed_override: float = 100.0  # %
    spindle_load: float = 0.0  # %
    spindle_temperature: float = 0.0  # °C
    
    # Feed
    feed_rate: float = 0.0  # mm/min
    feed_rate_override: float = 100.0  # %
    feed_rate_programmed: float = 0.0  # mm/min
    
    # Tool
    tool_number: int = 0
    tool_length_offset: float = 0.0
    tool_radius_offset: float = 0.0
    tool_load: float = 0.0  # %
    
    # G-code
    current_line: int = 0
    current_block: str = ""
    program_name: str = ""
    program_path: str = ""
    
    # Allarmi
    alarm_code: int = 0
    alarm_message: str = ""
    alarms: List[Dict[str, Any]] = None
    
    # PLC (se presente)
    plc_connected: bool = False
    plc_ip: str = ""
    plc_port: int = 0
    plc_latency: float = 0.0  # ms
    
    # Timestamp
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.position is None:
            self.position = CNCAxisPosition()
        if self.position_relative is None:
            self.position_relative = CNCAxisPosition()
        if self.position_machine is None:
            self.position_machine = CNCAxisPosition()
        if self.alarms is None:
            self.alarms = []


class CNCAdapter:
    """
    Adapter universale per controlli CNC
    Mappa i dati specifici del controllo in formato universale
    """
    
    def __init__(self, control_type: CNCControlType):
        """
        Inizializza l'adapter per un tipo di controllo specifico
        
        Args:
            control_type: Tipo di controllo CNC
        """
        self.control_type = control_type
        self.connected = False
        self.connection_params: Dict[str, Any] = {}
        self.last_error: str = ""
    
    def connect(self, **params) -> bool:
        """
        Connetti al controllo CNC.

        FAIL-CLOSED: nessun driver reale è implementato per i tipi di
        controllo elencati, quindi la connessione viene RIFIUTATA invece di
        essere simulata. Il percorso live reale è cnc_live_integration
        (Snap7 + mappa DB). Mai mostrare "Connected" senza una macchina vera.
        
        Returns:
            False sempre, finché non esiste un driver reale per il controllo.
        """
        self.connection_params = params
        self.connected = False
        self.last_error = (
            f"Nessun driver reale implementato per {self.control_type.value}: "
            "connessione rifiutata (fail-closed). "
            "Per PLC Siemens usare cnc_live_integration (Snap7 + mappa DB)."
        )
        return False
    
    def disconnect(self):
        """Disconnetti dal controllo CNC"""
        self.connected = False
    
    def read_status(self) -> Optional[CNCStatus]:
        """
        Legge lo stato completo della macchina CNC
        
        Returns:
            None: nessun driver reale implementato, nessun dato simulato
            viene restituito da questo adapter (fail-closed).
        """
        # Fail-closed: senza driver reale non esistono dati da restituire.
        return None
    
    def read_axis_positions(self) -> Optional[CNCAxisPosition]:
        """
        Legge le posizioni degli assi
        
        Returns:
            CNCAxisPosition con posizioni, None se errore
        """
        if not self.connected:
            return None
        
        # TODO: Implementare lettura assi specifica
        return CNCAxisPosition()
    
    def read_spindle(self) -> Dict[str, float]:
        """
        Legge dati spindle
        
        Returns:
            Dict con: speed, override, load, temperature
        """
        if not self.connected:
            return {}
        
        # TODO: Implementare lettura spindle specifica
        return {
            "speed": 0.0,
            "override": 100.0,
            "load": 0.0,
            "temperature": 0.0
        }
    
    def read_feed(self) -> Dict[str, float]:
        """
        Legge dati feed
        
        Returns:
            Dict con: rate, override, programmed
        """
        if not self.connected:
            return {}
        
        # TODO: Implementare lettura feed specifica
        return {
            "rate": 0.0,
            "override": 100.0,
            "programmed": 0.0
        }
    
    def read_tool(self) -> Dict[str, Any]:
        """
        Legge dati tool
        
        Returns:
            Dict con: number, length_offset, radius_offset, load
        """
        if not self.connected:
            return {}
        
        # TODO: Implementare lettura tool specifica
        return {
            "number": 0,
            "length_offset": 0.0,
            "radius_offset": 0.0,
            "load": 0.0
        }
    
    def read_gcode(self) -> Dict[str, Any]:
        """
        Legge informazioni G-code corrente
        
        Returns:
            Dict con: line, block, program_name, program_path
        """
        if not self.connected:
            return {}
        
        # TODO: Implementare lettura G-code specifica
        return {
            "line": 0,
            "block": "",
            "program_name": "",
            "program_path": ""
        }
    
    def read_alarms(self) -> List[Dict[str, Any]]:
        """
        Legge allarmi attivi
        
        Returns:
            Lista di dict con: code, message, severity
        """
        if not self.connected:
            return []
        
        # TODO: Implementare lettura allarmi specifica
        return []
    
    def read_plc_status(self) -> Dict[str, Any]:
        """
        Legge stato PLC (se presente)
        
        Returns:
            Dict con: connected, ip, port, latency
        """
        if not self.connected:
            return {
                "connected": False,
                "ip": "",
                "port": 0,
                "latency": 0.0
            }
        
        # TODO: Implementare lettura PLC specifica
        return {
            "connected": False,
            "ip": "",
            "port": 0,
            "latency": 0.0
        }
    
    def map_machine_state(self, raw_state: Any) -> MachineState:
        """
        Mappa lo stato macchina raw in formato universale
        
        Args:
            raw_state: Stato raw dal controllo specifico
        
        Returns:
            MachineState universale
        """
        # TODO: Implementare mapping specifico per tipo controllo
        if isinstance(raw_state, str):
            raw_state_upper = raw_state.upper()
            if "RUN" in raw_state_upper or "CYCLE" in raw_state_upper:
                return MachineState.RUN
            elif "STOP" in raw_state_upper or "IDLE" in raw_state_upper:
                return MachineState.STOP
            elif "HOLD" in raw_state_upper or "PAUSE" in raw_state_upper:
                return MachineState.HOLD
            elif "ALARM" in raw_state_upper or "ERROR" in raw_state_upper:
                return MachineState.ALARM
            elif "JOG" in raw_state_upper:
                return MachineState.JOG
            elif "MDI" in raw_state_upper:
                return MachineState.MDI
        
        return MachineState.UNKNOWN


# Factory per creare adapter specifici
def create_cnc_adapter(control_type: str, **params) -> CNCAdapter:
    """
    Factory per creare adapter CNC specifico
    
    Args:
        control_type: Tipo controllo (stringa o CNCControlType)
        **params: Parametri aggiuntivi
    
    Returns:
        CNCAdapter configurato
    """
    if isinstance(control_type, str):
        control_type = control_type.upper()
        if "SIEMENS" in control_type or "840D" in control_type:
            adapter = CNCAdapter(CNCControlType.SIEMENS_840D)
        elif "FANUC" in control_type or "FOCAS" in control_type:
            adapter = CNCAdapter(CNCControlType.FANUC_FOCAS)
        elif "HEIDENHAIN" in control_type or "TNC" in control_type:
            adapter = CNCAdapter(CNCControlType.HEIDENHAIN_TNC)
        elif "SYNTEC" in control_type:
            adapter = CNCAdapter(CNCControlType.SYNTEC)
        elif "OSAI" in control_type:
            adapter = CNCAdapter(CNCControlType.OSAI)
        elif "CHINESE" in control_type or "CINESE" in control_type:
            adapter = CNCAdapter(CNCControlType.CHINESE_OPEN)
        else:
            adapter = CNCAdapter(CNCControlType.GENERIC_PLC)
    else:
        adapter = CNCAdapter(control_type)
    
    # Tentativo di connessione: oggi viene sempre rifiutato (fail-closed),
    # l'esito onesto è visibile in adapter.connected / adapter.last_error.
    if not adapter.connect(**params):
        print(f"⚠ CNC adapter: {adapter.last_error}")
    
    return adapter




