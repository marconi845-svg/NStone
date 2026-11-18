import rust_engine
import time
from PyQt5.QtCore import QTimer, QObject, pyqtSignal

class MultifiloPLCUpdater(QObject):
    status_updated = pyqtSignal(object)
    
    def __init__(self, ip_address="192.168.0.1", db_number=1):
        super().__init__()
        self.plc = rust_engine.PyPlcClient(ip_address, db_number)
        self.ui = rust_engine.PyGestioneMultifiloUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        
    def start(self, interval_ms=100):
        self.timer.start(interval_ms)
        
    def stop(self):
        self.timer.stop()
        self.plc.disconnect()
        
    def update_status(self):
        try:
            rust_engine.update_gestione_multifilo_py(self.plc, self.ui)
            self.status_updated.emit(self.ui)
        except Exception as e:
            print(f"Errore aggiornamento PLC: {e}")

if __name__ == "__main__":
    plc = rust_engine.PyPlcClient("192.168.0.1", 1)
    ui = rust_engine.PyGestioneMultifiloUI()
    
    print("Loop di aggiornamento ogni 100ms (Ctrl+C per uscire):")
    try:
        while True:
            status = rust_engine.read_multifilo_inputs_py(plc)
            print(f"Stato: {status.machine_state}, "
                  f"Progresso: {status.progress_percent:.1f}%, "
                  f"Tempo residuo: {status.remaining_time_sec}s, "
                  f"Allarme: {status.alarm_code}")
            
            rust_engine.update_gestione_multifilo_py(plc, ui)
            print(f"UI - Contatore blocchi: {ui.block_counter}, "
                  f"Velocità filo: {ui.wire_speed_actual:.2f} m/min")
            
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDisconnessione dal PLC...")
        plc.disconnect()

