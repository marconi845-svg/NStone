"""
Validazione CNC - Modulo per validazione tecnica dei suggerimenti operativi CNC
Controlla range parametri, stato macchina, allarmi, condizioni di sicurezza, collisioni
"""

from typing import Dict, Optional, Any
from enum import Enum


class ValidationStatus(Enum):
    """Stati di validazione"""
    VALID = "Validato"
    INVALID = "Non valido"
    WARNING = "Avviso"
    PENDING = "In attesa"


class ValidazioneCNC:
    """
    Classe per validazione tecnica dei suggerimenti operativi CNC
    
    Controlli:
    - Range parametri (feed rate, spindle speed)
    - Limiti assi
    - Tool load
    - Rischio collisioni
    - Override
    - Stato macchina (RUN/STOP/HOLD)
    - Allarmi attivi
    - Condizioni di sicurezza
    """
    
    # Range parametri CNC (esempi - da configurare in base al controllo reale)
    PARAMETER_RANGES = {
        "feed_rate": {"min": 0.0, "max": 50000.0, "unit": "mm/min"},
        "spindle_speed": {"min": 0.0, "max": 24000.0, "unit": "RPM"},
        "feed_override": {"min": 0.0, "max": 200.0, "unit": "%"},
        "spindle_override": {"min": 0.0, "max": 200.0, "unit": "%"},
        "tool_load": {"min": 0.0, "max": 100.0, "unit": "%"},
        "spindle_load": {"min": 0.0, "max": 100.0, "unit": "%"},
    }
    
    # Limiti assi (esempi - da configurare in base alla macchina)
    AXIS_LIMITS = {
        "x": {"min": -1000.0, "max": 1000.0, "unit": "mm"},
        "y": {"min": -1000.0, "max": 1000.0, "unit": "mm"},
        "z": {"min": -500.0, "max": 500.0, "unit": "mm"},
    }
    
    # Condizioni di sicurezza
    SAFETY_CONDITIONS = {
        "require_stop_for_changes": True,  # Richiede STOP per modifiche parametri critici
        "block_on_alarm": True,  # Blocca se allarmi attivi
        "min_feed_rate": 1.0,  # Feed rate minimo (mm/min)
        "max_feed_rate": 50000.0,  # Feed rate massimo (mm/min)
        "max_spindle_speed": 24000.0,  # Velocità spindle massima (RPM)
        "max_tool_load": 90.0,  # Carico tool massimo (%)
        "max_spindle_load": 95.0,  # Carico spindle massimo (%)
        "collision_check_enabled": True,  # Controllo collisioni
    }
    
    def __init__(self):
        """Inizializza il validatore"""
        pass
    
    def validate_suggerimento(
        self, 
        suggerimento: Dict[str, Any], 
        cnc_status: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Valida un suggerimento operativo CNC
        
        Args:
            suggerimento: Dizionario con suggerimento da validare
                - "action": Tipo di azione (es. "set_parameter", "start", "stop", "change_feed")
                - "parameter": Nome parametro (se applicabile)
                - "value": Valore proposto (se applicabile)
                - "description": Descrizione suggerimento
            cnc_status: Stato corrente della macchina CNC (opzionale)
        
        Returns:
            Dizionario con:
            - "valid": bool - Se il suggerimento è valido
            - "status": ValidationStatus - Stato validazione
            - "motivation": str - Motivazione validazione
            - "warnings": List[str] - Avvisi (se presenti)
            - "errors": List[str] - Errori (se presenti)
        """
        valid = True
        status = ValidationStatus.VALID
        motivation = "Suggerimento valido"
        warnings = []
        errors = []
        
        # Estrai informazioni dal suggerimento
        action = suggerimento.get("action", "").lower()
        parameter = suggerimento.get("parameter", "")
        value = suggerimento.get("value")
        description = suggerimento.get("description", "")
        
        # Estrai stato CNC
        machine_state = None
        alarm_code = 0
        if cnc_status:
            machine_state = getattr(cnc_status, 'machine_state', None)
            alarm_code = getattr(cnc_status, 'alarm_code', 0)
            if hasattr(machine_state, 'value'):
                machine_state = machine_state.value
        
        # Controllo 1: Allarmi attivi
        if self.SAFETY_CONDITIONS["block_on_alarm"] and alarm_code > 0:
            valid = False
            status = ValidationStatus.INVALID
            errors.append(f"Allarme attivo (codice: {alarm_code}). Impossibile eseguire azioni.")
            motivation = "Allarme attivo - azione bloccata per sicurezza"
        
        # Controllo 2: Stato macchina per modifiche parametri
        if action in ["set_parameter", "modify_parameter", "change_parameter", "change_feed", "change_spindle"]:
            if self.SAFETY_CONDITIONS["require_stop_for_changes"]:
                if machine_state and machine_state.upper() in ["RUN", "CYCLE"]:
                    valid = False
                    status = ValidationStatus.INVALID
                    errors.append("Macchina in RUN. Modifiche parametri richiedono STOP.")
                    motivation = "Macchina in esecuzione - modifiche parametri non permesse"
        
        # Controllo 3: Range parametri
        if parameter and value is not None:
            if parameter in self.PARAMETER_RANGES:
                param_range = self.PARAMETER_RANGES[parameter]
                min_val = param_range["min"]
                max_val = param_range["max"]
                unit = param_range.get("unit", "")
                
                try:
                    value_float = float(value)
                    if value_float < min_val or value_float > max_val:
                        valid = False
                        status = ValidationStatus.INVALID
                        errors.append(
                            f"Valore {value_float} {unit} fuori range "
                            f"({min_val}-{max_val} {unit})"
                        )
                        motivation = f"Valore fuori range consentito"
                    elif value_float < min_val * 1.1 or value_float > max_val * 0.9:
                        # Valore vicino ai limiti
                        warnings.append(
                            f"Valore {value_float} {unit} vicino ai limiti "
                            f"({min_val}-{max_val} {unit})"
                        )
                        if status == ValidationStatus.VALID:
                            status = ValidationStatus.WARNING
                except (ValueError, TypeError):
                    valid = False
                    status = ValidationStatus.INVALID
                    errors.append(f"Valore non numerico: {value}")
                    motivation = "Valore non valido"
        
        # Controllo 4: Condizioni di sicurezza specifiche
        if parameter == "feed_rate" and value is not None:
            try:
                feed_val = float(value)
                if feed_val < self.SAFETY_CONDITIONS["min_feed_rate"]:
                    valid = False
                    status = ValidationStatus.INVALID
                    errors.append(
                        f"Feed rate {feed_val} mm/min inferiore al minimo "
                        f"{self.SAFETY_CONDITIONS['min_feed_rate']} mm/min"
                    )
                    motivation = "Feed rate troppo basso - rischio qualità"
                elif feed_val > self.SAFETY_CONDITIONS["max_feed_rate"]:
                    valid = False
                    status = ValidationStatus.INVALID
                    errors.append(
                        f"Feed rate {feed_val} mm/min superiore al massimo "
                        f"{self.SAFETY_CONDITIONS['max_feed_rate']} mm/min"
                    )
                    motivation = "Feed rate troppo alto - rischio sicurezza"
            except (ValueError, TypeError):
                pass
        
        if parameter == "spindle_speed" and value is not None:
            try:
                spindle_val = float(value)
                if spindle_val > self.SAFETY_CONDITIONS["max_spindle_speed"]:
                    valid = False
                    status = ValidationStatus.INVALID
                    errors.append(
                        f"Velocità spindle {spindle_val} RPM superiore al massimo "
                        f"{self.SAFETY_CONDITIONS['max_spindle_speed']} RPM"
                    )
                    motivation = "Velocità spindle troppo alta - rischio sicurezza"
            except (ValueError, TypeError):
                pass
        
        if parameter == "tool_load" and value is not None:
            try:
                tool_load_val = float(value)
                if tool_load_val > self.SAFETY_CONDITIONS["max_tool_load"]:
                    warnings.append(
                        f"Carico tool {tool_load_val}% superiore al limite consigliato "
                        f"{self.SAFETY_CONDITIONS['max_tool_load']}%"
                    )
                    if status == ValidationStatus.VALID:
                        status = ValidationStatus.WARNING
            except (ValueError, TypeError):
                pass
        
        if parameter == "spindle_load" and value is not None:
            try:
                spindle_load_val = float(value)
                if spindle_load_val > self.SAFETY_CONDITIONS["max_spindle_load"]:
                    warnings.append(
                        f"Carico spindle {spindle_load_val}% superiore al limite consigliato "
                        f"{self.SAFETY_CONDITIONS['max_spindle_load']}%"
                    )
                    if status == ValidationStatus.VALID:
                        status = ValidationStatus.WARNING
            except (ValueError, TypeError):
                pass
        
        # Controllo 5: Rischio collisioni (se posizione assi disponibile)
        if cnc_status and hasattr(cnc_status, 'position'):
            position = cnc_status.position
            if position:
                # Controlla limiti assi
                for axis_name, axis_limits in self.AXIS_LIMITS.items():
                    axis_value = getattr(position, axis_name, None)
                    if axis_value is not None:
                        if axis_value < axis_limits["min"] or axis_value > axis_limits["max"]:
                            warnings.append(
                                f"Asse {axis_name.upper()} fuori limiti "
                                f"({axis_limits['min']}-{axis_limits['max']} {axis_limits['unit']})"
                            )
                            if status == ValidationStatus.VALID:
                                status = ValidationStatus.WARNING
        
        # Controllo 6: Azioni pericolose
        dangerous_actions = ["emergency_stop", "force_stop", "override_safety", "disable_limits"]
        if action in dangerous_actions:
            warnings.append(f"Azione '{action}' richiede conferma esplicita")
            if status == ValidationStatus.VALID:
                status = ValidationStatus.WARNING
        
        # Costruisci risultato
        result = {
            "valid": valid,
            "status": status.value,
            "motivation": motivation,
            "warnings": warnings,
            "errors": errors,
            "action": action,
            "parameter": parameter,
            "value": value,
        }
        
        return result
    
    def get_parameter_ranges(self) -> Dict[str, Dict]:
        """Restituisce i range dei parametri"""
        return self.PARAMETER_RANGES.copy()
    
    def get_axis_limits(self) -> Dict[str, Dict]:
        """Restituisce i limiti degli assi"""
        return self.AXIS_LIMITS.copy()
    
    def get_safety_conditions(self) -> Dict[str, Any]:
        """Restituisce le condizioni di sicurezza"""
        return self.SAFETY_CONDITIONS.copy()




