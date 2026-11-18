"""
CNC UI Integration - Integrazione UI con aggiornamento 100ms per macchine CNC
"""

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from typing import Optional, Any

# Importa adapter CNC
try:
    from machines.cnc_adapter import CNCAdapter, CNCStatus
    CNC_ADAPTER_AVAILABLE = True
except ImportError:
    CNC_ADAPTER_AVAILABLE = False
    print("⚠ Modulo cnc_adapter non disponibile")


class CNCUIUpdater(QObject):
    """
    Aggiornatore UI per macchine CNC
    Esegue aggiornamento ogni 100ms
    """
    
    # Signal per aggiornamento status
    status_updated = pyqtSignal(object)  # Emette CNCStatus quando aggiornato
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cnc_adapter: Optional[CNCAdapter] = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.running = False
    
    def set_cnc_adapter(self, adapter: CNCAdapter):
        """Imposta l'adapter CNC da usare"""
        self.cnc_adapter = adapter
    
    def start(self, interval_ms: int = 100):
        """
        Avvia l'aggiornamento UI
        
        Args:
            interval_ms: Intervallo aggiornamento in millisecondi (default: 100ms)
        """
        if not self.running:
            self.timer.start(interval_ms)
            self.running = True
    
    def stop(self):
        """Ferma l'aggiornamento UI"""
        if self.running:
            self.timer.stop()
            self.running = False
    
    def update_ui(self):
        """Esegue l'aggiornamento UI"""
        if not self.cnc_adapter:
            return
        
        try:
            # Leggi stato CNC
            status = self.cnc_adapter.read_status()
            if status:
                # Emetti signal con nuovo status
                self.status_updated.emit(status)
        except Exception as e:
            print(f"Errore aggiornamento UI CNC: {e}")


def refresh_cnc_ui(window, cnc_status: Optional[CNCStatus]):
    """
    Aggiorna i widget UI della finestra CNC con i nuovi dati
    
    Args:
        window: Finestra GestioneCNCWindow
        cnc_status: Stato CNC aggiornato
    """
    if not cnc_status:
        return
    
    try:
        # Aggiorna stato macchina
        if hasattr(window, 'machine_state_label'):
            machine_state = cnc_status.machine_state
            if hasattr(machine_state, 'value'):
                machine_state = machine_state.value
            window.machine_state_label.setText(f"Stato: {machine_state}")
        
        # Aggiorna programma
        if hasattr(window, 'program_label'):
            program_name = cnc_status.program_name or "--"
            window.program_label.setText(f"Programma: {program_name}")
        
        # Aggiorna linea G-code
        if hasattr(window, 'current_line_label'):
            window.current_line_label.setText(f"Linea G-code: {cnc_status.current_line}")
        
        # Aggiorna allarmi
        if hasattr(window, 'alarm_label'):
            if cnc_status.alarm_code > 0:
                window.alarm_label.setText(f"Allarmi: Codice {cnc_status.alarm_code}")
                window.alarm_label.setStyleSheet("color: #FF6B6B; font-size: 12px;")
            else:
                window.alarm_label.setText("Allarmi: Nessuno")
                window.alarm_label.setStyleSheet("color: #51CF66; font-size: 12px;")
        
        # Aggiorna assi
        if hasattr(window, 'axis_x_label') and cnc_status.position:
            window.axis_x_label.setText(f"X: {cnc_status.position.x:.3f} mm")
        if hasattr(window, 'axis_y_label') and cnc_status.position:
            window.axis_y_label.setText(f"Y: {cnc_status.position.y:.3f} mm")
        if hasattr(window, 'axis_z_label') and cnc_status.position:
            window.axis_z_label.setText(f"Z: {cnc_status.position.z:.3f} mm")
        
        # Aggiorna spindle
        if hasattr(window, 'spindle_speed_label'):
            window.spindle_speed_label.setText(f"Velocità: {cnc_status.spindle_speed:.0f} RPM")
        if hasattr(window, 'spindle_override_label'):
            window.spindle_override_label.setText(f"Override: {cnc_status.spindle_speed_override:.1f} %")
        if hasattr(window, 'spindle_load_label'):
            window.spindle_load_label.setText(f"Carico: {cnc_status.spindle_load:.1f} %")
        
        # Aggiorna feed
        if hasattr(window, 'feed_rate_label'):
            window.feed_rate_label.setText(f"Velocità: {cnc_status.feed_rate:.2f} mm/min")
        if hasattr(window, 'feed_override_label'):
            window.feed_override_label.setText(f"Override: {cnc_status.feed_rate_override:.1f} %")
        
        # Aggiorna tool
        if hasattr(window, 'tool_number_label'):
            window.tool_number_label.setText(f"Numero: {cnc_status.tool_number}")
        if hasattr(window, 'tool_load_label'):
            window.tool_load_label.setText(f"Carico: {cnc_status.tool_load:.1f} %")
        
        # Aggiorna stato CNC nella barra di stato
        if hasattr(window, 'cnc_status_label'):
            if cnc_status.machine_state and hasattr(cnc_status.machine_state, 'value'):
                state = cnc_status.machine_state.value
                if state in ["RUN", "CYCLE"]:
                    window.cnc_status_label.setText("CNC: In esecuzione")
                    window.cnc_status_label.setStyleSheet("color: #51CF66; font-size: 12px;")
                elif state == "ALARM":
                    window.cnc_status_label.setText("CNC: Allarme")
                    window.cnc_status_label.setStyleSheet("color: #FF6B6B; font-size: 12px;")
                else:
                    window.cnc_status_label.setText("CNC: Fermo")
                    window.cnc_status_label.setStyleSheet("color: #FFD93D; font-size: 12px;")
            else:
                window.cnc_status_label.setText("CNC: Non connesso")
                window.cnc_status_label.setStyleSheet("color: #FF6B6B; font-size: 12px;")
        
        # Aggiorna Ethernet status widget (se presente)
        if hasattr(window, 'ethernet_status_widget') and cnc_status.plc_connected:
            if hasattr(window.ethernet_status_widget, 'update_status'):
                window.ethernet_status_widget.update_status(
                    connected=True,
                    ip=cnc_status.plc_ip,
                    port=cnc_status.plc_port,
                    latency=cnc_status.plc_latency
                )
        
        # Salva status corrente per RAG Engine
        window._current_cnc_status = cnc_status
        
    except Exception as e:
        print(f"Errore refresh UI CNC: {e}")




