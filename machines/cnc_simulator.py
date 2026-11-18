"""
Simulatore CNC Universale
Simula una macchina CNC con stati, assi, spindle, feed, tool, G-code, allarmi
Pattern identico a snap7_multifilo_server.py e snap7_lucidatrice_server.py
"""
import time
import random
import logging
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class MachineState(Enum):
    """Stati macchina CNC"""
    READY = "READY"
    RUN = "RUN"
    HOLD = "HOLD"
    ERROR = "ERROR"
    STOP = "STOP"


@dataclass
class CNCAxisPosition:
    """Posizione assi CNC"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class CNCSimulatorStatus:
    """Stato completo simulatore CNC"""
    # Stato macchina
    machine_state: MachineState = MachineState.READY
    program_name: str = "PROGRAM_001.NC"
    current_line: int = 0
    current_block: str = ""
    total_lines: int = 100
    
    # Posizioni assi
    position: CNCAxisPosition = field(default_factory=CNCAxisPosition)
    
    # Spindle
    spindle_speed: float = 0.0  # RPM
    spindle_speed_override: float = 100.0  # %
    spindle_load: float = 0.0  # %
    spindle_temperature: float = 25.0  # °C
    
    # Feed
    feed_rate: float = 0.0  # mm/min
    feed_rate_override: float = 100.0  # %
    feed_rate_programmed: float = 500.0  # mm/min
    
    # Tool
    tool_number: int = 1
    tool_load: float = 0.0  # %
    tool_length_offset: float = 0.0  # mm
    tool_radius_offset: float = 0.0  # mm
    
    # Allarmi
    alarm_code: int = 0
    alarm_message: str = ""
    
    # PLC
    plc_connected: bool = True
    plc_ip: str = "127.0.0.1"
    plc_port: int = 102
    plc_latency: float = 2.5  # ms
    plc_packets_sent: int = 0
    plc_packets_received: int = 0
    plc_errors: int = 0
    
    # Materiale in lavorazione
    materiale: str = "Granito"
    quantita_lastre: int = 10
    spessore: float = 20.0  # mm
    finitura: str = "Fresato"
    cliente_commessa: str = "Commessa #12345"
    avanzamento: float = 0.0  # %
    tempo_stimato: int = 0  # secondi
    tempo_rimanente: int = 0  # secondi
    tempo_inizio_lavorazione: Optional[float] = None
    
    # Pezzi in lavorazione
    dimensioni_l: float = 500.0  # Larghezza (mm)
    dimensioni_h: float = 300.0  # Altezza (mm)
    dimensioni_p: float = 20.0  # Profondità/Spessore (mm)
    pezzi_totali: int = 10  # Numero totale pezzi
    pezzi_completati: int = 0  # Numero pezzi completati
    pezzi_in_lavorazione: int = 1  # Numero pezzi attualmente in lavorazione
    avanzamento_pezzo: float = 0.0  # % avanzamento pezzo corrente
    avanzamento_lotto: float = 0.0  # % avanzamento lotto totale
    
    # Analisi Fanghi - Depurazione
    umidita_residua: float = 75.0  # %
    densita_fango: float = 1200.0  # kg/m³
    granulometria_media: float = 50.0  # µm
    ph: float = 7.2  # pH
    volume_fanghi_prodotti: float = 0.0  # m³/giorno
    cicli_filtropressa: int = 0  # Numero cicli
    tempo_ciclo_medio: int = 45  # minuti
    stato_filtropressa: str = "READY"  # READY / RUN / HOLD / ERROR
    qualita_acqua_riciclata: float = 95.0  # %


class CNCSimulator:
    """Simulatore CNC Universale - Pattern identico a Multifilo/Lucidatrice"""
    
    def __init__(self):
        self.status = CNCSimulatorStatus()
        self.running = False
        self.update_thread = None
        
        # Inizializza pezzi in lavorazione (sincronizzato con quantità lastre se lavora lastre)
        if self.status.quantita_lastre > 0:
            self.status.pezzi_totali = self.status.quantita_lastre
            self.status.pezzi_in_lavorazione = self.status.quantita_lastre
        
        # Variabili per simulazione dinamica
        self.target_spindle_speed = 0.0
        self.target_feed_rate = 0.0
        self.target_position_x = 0.0
        self.target_position_y = 0.0
        self.target_position_z = 0.0
        
        # G-code simulato
        self.gcode_lines = [
            "G00 X0 Y0 Z50",
            "G01 Z-5 F500",
            "G01 X100 Y0 F500",
            "G01 X100 Y100 F500",
            "G01 X0 Y100 F500",
            "G01 X0 Y0 F500",
            "G00 Z50",
            "M30"
        ]
        self.status.total_lines = len(self.gcode_lines)
    
    def start(self):
        """Avvia il simulatore"""
        if self.running:
            return
        
        self.running = True
        import threading
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        logger.info("Simulatore CNC avviato")
    
    def stop(self):
        """Ferma il simulatore"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=2.0)
        logger.info("Simulatore CNC fermato")
    
    def _update_loop(self):
        """Loop di aggiornamento parametri (ogni 100ms)"""
        while self.running:
            try:
                self._update_parameters()
                time.sleep(0.1)  # 100ms
            except Exception as e:
                logger.error(f"Errore aggiornamento simulatore: {e}")
                time.sleep(0.1)
    
    def _update_parameters(self):
        """Aggiorna tutti i parametri simulati"""
        if self.status.machine_state == MachineState.RUN:
            # Durante RUN, aggiorna tutti i parametri
            self._update_spindle()
            self._update_feed()
            self._update_axes()
            self._update_tool()
            self._update_gcode()
            self._update_materiale()
            self._update_pezzi()
            self._update_fanghi()
            self._update_plc_stats()
        elif self.status.machine_state == MachineState.HOLD:
            # Durante HOLD, parametri rimangono stabili
            pass
        elif self.status.machine_state == MachineState.ERROR:
            # Durante ERROR, parametri tendono a zero
            self.status.spindle_speed = max(0.0, self.status.spindle_speed * 0.9)
            self.status.feed_rate = max(0.0, self.status.feed_rate * 0.9)
            self.status.tool_load = max(0.0, self.status.tool_load * 0.9)
        elif self.status.machine_state == MachineState.STOP:
            # Durante STOP, reset parametri
            self.status.spindle_speed = 0.0
            self.status.feed_rate = 0.0
            self.status.tool_load = 0.0
    
    def _update_spindle(self):
        """Aggiorna parametri spindle"""
        # Target RPM basato su stato
        if self.status.machine_state == MachineState.RUN:
            self.target_spindle_speed = 8000.0  # RPM target
        else:
            self.target_spindle_speed = 0.0
        
        # Variazione graduale verso target
        if abs(self.status.spindle_speed - self.target_spindle_speed) > 10.0:
            diff = self.target_spindle_speed - self.status.spindle_speed
            self.status.spindle_speed += diff * 0.1  # 10% del gap
        else:
            self.status.spindle_speed = self.target_spindle_speed
        
        # Carico simulato basato su materiale e profondità
        if self.status.spindle_speed > 0:
            base_load = 30.0  # Carico base
            material_factor = 1.2 if self.status.materiale == "Granito" else 1.0
            depth_factor = abs(self.status.position.z) / 50.0  # Fattore profondità
            self.status.spindle_load = min(100.0, base_load * material_factor * (1 + depth_factor * 0.5))
        else:
            self.status.spindle_load = 0.0
        
        # Temperatura proporzionale a carico
        self.status.spindle_temperature = 25.0 + (self.status.spindle_load * 0.5)
        self.status.spindle_temperature = max(25.0, min(85.0, self.status.spindle_temperature))
    
    def _update_feed(self):
        """Aggiorna parametri feed"""
        # Feedrate basato su feed programmato e override
        if self.status.machine_state == MachineState.RUN:
            self.target_feed_rate = self.status.feed_rate_programmed * (self.status.feed_rate_override / 100.0)
        else:
            self.target_feed_rate = 0.0
        
        # Variazione graduale
        if abs(self.status.feed_rate - self.target_feed_rate) > 1.0:
            diff = self.target_feed_rate - self.status.feed_rate
            self.status.feed_rate += diff * 0.2  # 20% del gap
        else:
            self.status.feed_rate = self.target_feed_rate
    
    def _update_axes(self):
        """Aggiorna posizioni assi con interpolazione lineare"""
        if self.status.machine_state == MachineState.RUN and self.status.feed_rate > 0:
            # Movimento simulato basato su feedrate
            delta_time = 0.1  # 100ms
            delta_distance = (self.status.feed_rate / 60.0) * delta_time  # mm
            
            # Movimento verso target (simula percorso G-code)
            if abs(self.status.position.x - self.target_position_x) > 0.1:
                if self.status.position.x < self.target_position_x:
                    self.status.position.x = min(self.target_position_x, self.status.position.x + delta_distance)
                else:
                    self.status.position.x = max(self.target_position_x, self.status.position.x - delta_distance)
            
            if abs(self.status.position.y - self.target_position_y) > 0.1:
                if self.status.position.y < self.target_position_y:
                    self.status.position.y = min(self.target_position_y, self.status.position.y + delta_distance)
                else:
                    self.status.position.y = max(self.target_position_y, self.status.position.y - delta_distance)
            
            if abs(self.status.position.z - self.target_position_z) > 0.1:
                if self.status.position.z < self.target_position_z:
                    self.status.position.z = min(self.target_position_z, self.status.position.z + delta_distance)
                else:
                    self.status.position.z = max(self.target_position_z, self.status.position.z - delta_distance)
    
    def _update_tool(self):
        """Aggiorna parametri tool"""
        # Carico tool basato su materiale, profondità e feedrate
        if self.status.machine_state == MachineState.RUN:
            base_load = 20.0
            material_factor = 1.3 if self.status.materiale == "Granito" else 1.0
            depth_factor = abs(self.status.position.z) / 50.0
            feed_factor = self.status.feed_rate / 500.0
            self.status.tool_load = min(100.0, base_load * material_factor * (1 + depth_factor * 0.5) * (1 + feed_factor * 0.3))
        else:
            self.status.tool_load = 0.0
    
    def _update_gcode(self):
        """Aggiorna avanzamento G-code"""
        if self.status.machine_state == MachineState.RUN:
            # Avanza linea G-code ogni secondo (simula esecuzione)
            if not hasattr(self, '_last_gcode_update'):
                self._last_gcode_update = time.time()
            
            current_time = time.time()
            if current_time - self._last_gcode_update >= 1.0:  # 1 secondo per linea
                self.status.current_line = min(self.status.total_lines, self.status.current_line + 1)
                if self.status.current_line < len(self.gcode_lines):
                    self.status.current_block = self.gcode_lines[self.status.current_line]
                self._last_gcode_update = current_time
                
                # Aggiorna target posizioni basato su G-code
                if "X" in self.status.current_block:
                    try:
                        x_val = float(self.status.current_block.split("X")[1].split()[0])
                        self.target_position_x = x_val
                    except:
                        pass
                if "Y" in self.status.current_block:
                    try:
                        y_val = float(self.status.current_block.split("Y")[1].split()[0])
                        self.target_position_y = y_val
                    except:
                        pass
                if "Z" in self.status.current_block:
                    try:
                        z_val = float(self.status.current_block.split("Z")[1].split()[0])
                        self.target_position_z = z_val
                    except:
                        pass
                
                # Reset a fine programma
                if self.status.current_line >= self.status.total_lines:
                    self.status.machine_state = MachineState.READY
                    self.status.current_line = 0
                    self.status.position = CNCAxisPosition()
                    self.target_position_x = 0.0
                    self.target_position_y = 0.0
                    self.target_position_z = 0.0
    
    def _update_materiale(self):
        """Aggiorna avanzamento materiale"""
        if self.status.machine_state == MachineState.RUN:
            # Avanzamento basato su linee G-code completate
            if self.status.total_lines > 0:
                self.status.avanzamento = (self.status.current_line / self.status.total_lines) * 100.0
            
            # Calcola tempo stimato e rimanente
            if self.status.feed_rate > 0:
                # Tempo stimato basato su lunghezza programma e feedrate medio
                # Assumiamo percorso totale di ~400mm
                percorso_totale = 400.0  # mm
                feedrate_medio = self.status.feed_rate
                self.status.tempo_stimato = int((percorso_totale / feedrate_medio) * 60)  # secondi
                
                # Inizia timer quando inizia la lavorazione
                if self.status.tempo_inizio_lavorazione is None:
                    self.status.tempo_inizio_lavorazione = time.time()
                
                # Calcola tempo rimanente
                if self.status.tempo_inizio_lavorazione and self.status.tempo_stimato > 0:
                    tempo_trascorso = time.time() - self.status.tempo_inizio_lavorazione
                    self.status.tempo_rimanente = max(0, int(self.status.tempo_stimato - tempo_trascorso))
                else:
                    self.status.tempo_rimanente = self.status.tempo_stimato
            else:
                self.status.tempo_stimato = 0
                self.status.tempo_rimanente = 0
            
            # Quando avanzamento >= 100%, decrementa quantità lastre
            if self.status.avanzamento >= 100.0:
                if not hasattr(self, '_last_quantita'):
                    self._last_quantita = self.status.quantita_lastre
                
                if self.status.quantita_lastre > 0:
                    self.status.quantita_lastre -= 1
                    self.status.avanzamento = 0.0
                    self.status.current_line = 0
                    self.status.tempo_inizio_lavorazione = None
                    
                    # Se quantità = 0, passa a HOLD
                    if self.status.quantita_lastre == 0:
                        self.status.machine_state = MachineState.HOLD
        elif self.status.machine_state == MachineState.HOLD:
            # Durante HOLD, tempo rimanente congelato
            pass
        else:
            self.status.tempo_stimato = 0
            self.status.tempo_rimanente = 0
            self.status.tempo_inizio_lavorazione = None
    
    def _update_pezzi(self):
        """Aggiorna avanzamento pezzi in lavorazione"""
        if self.status.machine_state == MachineState.RUN:
            # Avanzamento pezzo basato su linee G-code completate (stesso del materiale)
            if self.status.total_lines > 0:
                self.status.avanzamento_pezzo = (self.status.current_line / self.status.total_lines) * 100.0
            
            # Quando avanzamento pezzo >= 100%, pezzo completato
            if self.status.avanzamento_pezzo >= 100.0:
                if not hasattr(self, '_pezzi_completati_precedenti'):
                    self._pezzi_completati_precedenti = 0
                
                # Incrementa pezzi completati
                if self.status.pezzi_completati < self.status.pezzi_totali:
                    self.status.pezzi_completati += 1
                    self.status.pezzi_in_lavorazione = max(0, self.status.pezzi_totali - self.status.pezzi_completati)
                    self.status.avanzamento_pezzo = 0.0
                    self.status.current_line = 0
                    self.status.tempo_inizio_lavorazione = None
                    
                    # Se tutti i pezzi sono completati, passa a HOLD
                    if self.status.pezzi_completati >= self.status.pezzi_totali:
                        self.status.machine_state = MachineState.HOLD
                        self.status.pezzi_in_lavorazione = 0
            
            # Calcola avanzamento lotto
            if self.status.pezzi_totali > 0:
                self.status.avanzamento_lotto = (self.status.pezzi_completati / self.status.pezzi_totali) * 100.0
            else:
                self.status.avanzamento_lotto = 0.0
        elif self.status.machine_state == MachineState.HOLD:
            # Durante HOLD, valori congelati
            pass
        else:
            # Durante ERROR o altri stati, avanzamenti fermi
            self.status.avanzamento_pezzo = 0.0
            if self.status.pezzi_totali > 0:
                self.status.avanzamento_lotto = (self.status.pezzi_completati / self.status.pezzi_totali) * 100.0
            else:
                self.status.avanzamento_lotto = 0.0
    
    def _update_fanghi(self):
        """Aggiorna parametri analisi fanghi - Depurazione"""
        if self.status.machine_state == MachineState.RUN:
            # Stato filtropressa sincronizzato con macchina
            self.status.stato_filtropressa = "RUN"
            
            # Umidità varia in base al ciclo filtropressa (diminuisce durante ciclo)
            if not hasattr(self, '_ciclo_filtropressa_start'):
                self._ciclo_filtropressa_start = time.time()
            
            tempo_ciclo_attuale = time.time() - self._ciclo_filtropressa_start
            if tempo_ciclo_attuale >= self.status.tempo_ciclo_medio * 60:  # Completa ciclo
                # Ciclo completato
                self.status.cicli_filtropressa += 1
                self.status.umidita_residua = max(60.0, self.status.umidita_residua - random.uniform(2.0, 5.0))
                self._ciclo_filtropressa_start = time.time()
            else:
                # Durante ciclo, umidità diminuisce gradualmente
                progresso_ciclo = tempo_ciclo_attuale / (self.status.tempo_ciclo_medio * 60)
                umidita_target = 65.0  # Umidità target a fine ciclo
                self.status.umidita_residua = max(umidita_target, 75.0 - (progresso_ciclo * 10.0))
            
            # Densità aumenta con materiale più fine (granulometria più piccola)
            if self.status.granulometria_media < 30.0:
                self.status.densita_fango = min(1400.0, self.status.densita_fango + random.uniform(0.5, 2.0))
            else:
                self.status.densita_fango = max(1000.0, self.status.densita_fango - random.uniform(0.1, 0.5))
            
            # Granulometria dipende dal tipo di lavorazione (fresatura produce particelle più fini)
            if self.status.tool_load > 50.0:  # Lavorazione intensa
                self.status.granulometria_media = max(20.0, self.status.granulometria_media - random.uniform(0.5, 2.0))
            else:
                self.status.granulometria_media = min(100.0, self.status.granulometria_media + random.uniform(0.1, 1.0))
            
            # pH varia leggermente (range 6.5-7.5)
            self.status.ph = max(6.5, min(7.5, self.status.ph + random.uniform(-0.05, 0.05)))
            
            # Volume fanghi cresce durante RUN (proporzionale a feedrate e tool load)
            incremento_volume = (self.status.feed_rate / 500.0) * (self.status.tool_load / 100.0) * 0.001  # m³/giorno
            self.status.volume_fanghi_prodotti += incremento_volume * (0.1 / 3600.0)  # Aggiornamento ogni 100ms
            
            # Tempo ciclo medio varia leggermente
            self.status.tempo_ciclo_medio = max(30, min(60, int(45 + random.uniform(-2, 2))))
            
            # Qualità acqua riciclata dipende da pH e umidità
            if 6.5 <= self.status.ph <= 7.5 and self.status.umidita_residua < 80.0:
                self.status.qualita_acqua_riciclata = min(100.0, self.status.qualita_acqua_riciclata + random.uniform(0.1, 0.5))
            else:
                self.status.qualita_acqua_riciclata = max(80.0, self.status.qualita_acqua_riciclata - random.uniform(0.2, 1.0))
            
            # Allarmi basati su parametri
            if self.status.umidita_residua > 85.0:
                self.status.alarm_code = 100  # Allarme: Umidità troppo alta
                self.status.alarm_message = "Umidità residua troppo alta - Filtropressa inefficiente"
            elif self.status.ph < 6.0 or self.status.ph > 8.5:
                self.status.alarm_code = 101  # Allarme: pH fuori range
                self.status.alarm_message = "pH fuori range - Allarme ambientale"
            elif self.status.volume_fanghi_prodotti > 50.0:  # m³/giorno
                self.status.alarm_code = 102  # Allarme: Volume eccessivo
                self.status.alarm_message = "Volume fanghi eccessivo - Vasca piena"
            elif self.status.tempo_ciclo_medio > 55:
                self.status.alarm_code = 103  # Allarme: Ciclo troppo lungo
                self.status.alarm_message = "Ciclo filtropressa troppo lungo - Manutenzione richiesta"
            else:
                if self.status.alarm_code in [100, 101, 102, 103]:
                    self.status.alarm_code = 0
                    self.status.alarm_message = ""
        
        elif self.status.machine_state == MachineState.HOLD:
            # Durante HOLD, filtropressa in HOLD
            self.status.stato_filtropressa = "HOLD"
            # Parametri rimangono stabili
        elif self.status.machine_state == MachineState.ERROR:
            # Durante ERROR, filtropressa in ERROR
            self.status.stato_filtropressa = "ERROR"
            # Parametri tendono a valori di default
            self.status.umidita_residua = max(75.0, self.status.umidita_residua + random.uniform(0.1, 0.5))
        else:
            # Durante STOP/READY, filtropressa in READY
            self.status.stato_filtropressa = "READY"
    
    def _update_plc_stats(self):
        """Aggiorna statistiche PLC"""
        if self.status.plc_connected:
            self.status.plc_packets_sent += 1
            self.status.plc_packets_received += 1
            self.status.plc_latency = random.uniform(1.0, 5.0)  # ms
            # Simula errori occasionali
            if random.random() < 0.001:  # 0.1% probabilità
                self.status.plc_errors += 1
    
    def set_machine_state(self, state: MachineState):
        """Imposta stato macchina"""
        self.status.machine_state = state
        logger.info(f"Stato macchina: {state.value}")
    
    def get_status(self) -> CNCSimulatorStatus:
        """Restituisce stato corrente"""
        return self.status
    
    def reset(self):
        """Reset simulatore"""
        self.status = CNCSimulatorStatus()
        self.status.total_lines = len(self.gcode_lines)
        logger.info("Simulatore CNC resettato")


# Istanza globale simulatore
_simulator_instance = None

def get_simulator() -> CNCSimulator:
    """Ottiene istanza singleton del simulatore"""
    global _simulator_instance
    if _simulator_instance is None:
        _simulator_instance = CNCSimulator()
    return _simulator_instance


if __name__ == "__main__":
    # Test simulatore
    simulator = get_simulator()
    simulator.start()
    
    try:
        # Simula RUN
        simulator.set_machine_state(MachineState.RUN)
        
        # Loop di test
        for i in range(100):
            status = simulator.get_status()
            print(f"Linea: {status.current_line}/{status.total_lines}, "
                  f"Spindle: {status.spindle_speed:.0f} RPM, "
                  f"Feed: {status.feed_rate:.1f} mm/min, "
                  f"Pos: X={status.position.x:.1f} Y={status.position.y:.1f} Z={status.position.z:.1f}, "
                  f"Avanzamento: {status.avanzamento:.1f}%")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        simulator.stop()

