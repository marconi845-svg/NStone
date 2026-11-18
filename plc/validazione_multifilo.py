"""
Validazione Multifilo - Modulo per validazione tecnica dei suggerimenti operativi
Controlla range parametri, stato macchina, allarmi, condizioni di sicurezza
"""

from typing import Dict, Optional, Any
from enum import Enum


class ValidationStatus(Enum):
    """Stati di validazione"""
    VALID = "Validato"
    INVALID = "Non valido"
    WARNING = "Avviso"
    PENDING = "In attesa"


class ValidazioneMultifilo:
    """
    Classe per validazione tecnica dei suggerimenti operativi Multifilo
    
    Controlli:
    - Range parametri
    - Stato macchina (RUN/STOP)
    - Allarmi attivi
    - Condizioni di sicurezza
    """
    
    # Range parametri Multifilo (esempi - da configurare in base al PLC reale)
    PARAMETER_RANGES = {
        "wire_speed": {"min": 0.0, "max": 50.0, "unit": "m/s"},
        "feed_rate": {"min": 0.0, "max": 1000.0, "unit": "mm/min"},
        "tension": {"min": 0.0, "max": 5000.0, "unit": "N"},
        "avanzamento": {"min": 0.0, "max": 100.0, "unit": "%"},
    }
    
    # Condizioni di sicurezza
    SAFETY_CONDITIONS = {
        "require_stop_for_changes": True,  # Richiede STOP per modifiche parametri
        "block_on_alarm": True,  # Blocca se allarmi attivi
        "min_tension": 100.0,  # Tensione minima (N)
        "max_wire_speed": 50.0,  # Velocità filo massima (m/s)
    }
    
    def __init__(self):
        """Inizializza il validatore"""
        pass
    
    def validate_suggerimento(
        self, 
        suggerimento: Dict[str, Any], 
        stato_macchina: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Valida un suggerimento operativo
        
        Args:
            suggerimento: Dizionario con suggerimento da validare
                - "action": Tipo di azione (es. "set_parameter", "start", "stop")
                - "parameter": Nome parametro (se applicabile)
                - "value": Valore proposto (se applicabile)
                - "description": Descrizione suggerimento
            stato_macchina: Stato corrente della macchina (opzionale)
        
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
        
        # Estrai stato macchina
        machine_state = None
        allarmi = 0
        if stato_macchina:
            machine_state = getattr(stato_macchina, 'stato_macchina', None)
            allarmi = getattr(stato_macchina, 'allarmi', 0)
            connessa = getattr(stato_macchina, 'connessa', False)
        
        # Controllo 1: Allarmi attivi
        if self.SAFETY_CONDITIONS["block_on_alarm"] and allarmi > 0:
            valid = False
            status = ValidationStatus.INVALID
            errors.append(f"Allarme attivo (codice: {allarmi}). Impossibile eseguire azioni.")
            motivation = "Allarme attivo - azione bloccata per sicurezza"
        
        # Controllo 2: Stato macchina per modifiche parametri
        if action in ["set_parameter", "modify_parameter", "change_parameter"]:
            if self.SAFETY_CONDITIONS["require_stop_for_changes"]:
                if machine_state and machine_state.upper() == "RUN":
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
        if parameter == "tension" and value is not None:
            try:
                tension_val = float(value)
                if tension_val < self.SAFETY_CONDITIONS["min_tension"]:
                    valid = False
                    status = ValidationStatus.INVALID
                    errors.append(
                        f"Tensione {tension_val}N inferiore al minimo "
                        f"{self.SAFETY_CONDITIONS['min_tension']}N"
                    )
                    motivation = "Tensione troppo bassa - rischio sicurezza"
            except (ValueError, TypeError):
                pass
        
        if parameter == "wire_speed" and value is not None:
            try:
                speed_val = float(value)
                if speed_val > self.SAFETY_CONDITIONS["max_wire_speed"]:
                    valid = False
                    status = ValidationStatus.INVALID
                    errors.append(
                        f"Velocità filo {speed_val}m/s superiore al massimo "
                        f"{self.SAFETY_CONDITIONS['max_wire_speed']}m/s"
                    )
                    motivation = "Velocità troppo alta - rischio sicurezza"
            except (ValueError, TypeError):
                pass
        
        # Controllo 5: Azioni pericolose
        dangerous_actions = ["emergency_stop", "force_stop", "override_safety"]
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
    
    def get_safety_conditions(self) -> Dict[str, Any]:
        """Restituisce le condizioni di sicurezza"""
        return self.SAFETY_CONDITIONS.copy()




