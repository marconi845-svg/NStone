"""
Modulo per integrare il G-code con il sistema AI
Fornisce analisi intelligente, ottimizzazione e suggerimenti basati su AI
"""
from typing import Dict, Optional
from plc.rust_bridge import run_gcode_analyze, run_gcode_validate, run_gcode_optimize
from llm.gemini_service import GeminiService


class GCodeAIIntegration:
    """
    Classe per integrare l'analisi G-code con l'AI
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Inizializza l'integrazione G-code AI
        
        Args:
            api_key: API key per Gemini (opzionale, usa quella di default se None)
        """
        self.gemini_service = GeminiService(api_key=api_key)
    
    def analyze_with_ai(self, gcode_text: str) -> Dict:
        """
        Analizza il G-code usando il motore neurale Rust e l'AI
        
        Args:
            gcode_text: Testo del programma G-code
            
        Returns:
            Dizionario con analisi completa:
            {
                "metrics": {...},  # Metriche dal motore Rust
                "validation": {...},  # Validazione dal motore Rust
                "ai_analysis": "...",  # Analisi intelligente da AI
                "ai_suggestions": [...]  # Suggerimenti da AI
            }
        """
        # Step 1: Analisi con motore neurale Rust
        metrics_result = run_gcode_analyze(gcode_text)
        validation_result = run_gcode_validate(gcode_text)
        
        if metrics_result["status"] != "ok" or validation_result["status"] != "ok":
            return {
                "error": "Errore nell'analisi G-code",
                "metrics_error": metrics_result.get("error"),
                "validation_error": validation_result.get("error")
            }
        
        metrics = metrics_result.get("data", {})
        validation = validation_result.get("data", {})
        
        # Step 2: Prepara contesto per AI
        context = self._prepare_ai_context(gcode_text, metrics, validation)
        
        # Step 3: Chiama AI per analisi intelligente
        ai_prompt = f"""Sei un esperto di programmazione CNC e ottimizzazione G-code per macchine da taglio.

Analizza il seguente programma G-code e fornisci:
1. Valutazione generale della qualità del programma
2. Identificazione di potenziali problemi o inefficienze
3. Suggerimenti per ottimizzazione
4. Stima miglioramenti possibili in termini di tempo e qualità

**Metriche del programma:**
{self._format_metrics(metrics)}

**Validazione:**
{self._format_validation(validation)}

**Programma G-code:**
```
{gcode_text[:2000]}
```

Rispondi in formato strutturato con:
- Analisi generale
- Problemi identificati
- Suggerimenti di ottimizzazione
- Stima miglioramenti"""
        
        try:
            ai_response = self.gemini_service.send_message(ai_prompt)
            
            # Estrai suggerimenti dalla risposta AI
            suggestions = self._extract_suggestions(ai_response)
            
            return {
                "metrics": metrics,
                "validation": validation,
                "ai_analysis": ai_response,
                "ai_suggestions": suggestions,
                "status": "ok"
            }
        except Exception as e:
            return {
                "metrics": metrics,
                "validation": validation,
                "ai_analysis": None,
                "ai_suggestions": [],
                "error": f"Errore nella chiamata AI: {str(e)}",
                "status": "partial"
            }
    
    def optimize_with_ai(self, gcode_text: str) -> Dict:
        """
        Ottimizza il G-code usando motore Rust + AI
        
        Args:
            gcode_text: Testo del programma G-code originale
            
        Returns:
            Dizionario con G-code ottimizzato e analisi
        """
        # Step 1: Ottimizzazione automatica con Rust
        optimize_result = run_gcode_optimize(gcode_text)
        
        if optimize_result["status"] != "ok":
            return {
                "error": "Errore nell'ottimizzazione G-code",
                "details": optimize_result.get("error")
            }
        
        optimized_gcode = optimize_result.get("data", {}).get("optimized_gcode", "")
        
        # Step 2: Analisi AI dell'ottimizzazione
        ai_prompt = f"""Sei un esperto di ottimizzazione G-code.

Ho ottimizzato un programma G-code. Confronta l'originale con l'ottimizzato e valuta:

**G-code Originale:**
```
{gcode_text[:1500]}
```

**G-code Ottimizzato:**
```
{optimized_gcode[:1500]}
```

Fornisci:
1. Valutazione dei miglioramenti ottenuti
2. Ulteriori suggerimenti se possibile
3. Verifica che l'ottimizzazione non abbia introdotto errori"""
        
        try:
            ai_feedback = self.gemini_service.send_message(ai_prompt)
            
            return {
                "optimized_gcode": optimized_gcode,
                "original_gcode": gcode_text,
                "ai_feedback": ai_feedback,
                "optimization_metrics": optimize_result.get("data", {}),
                "status": "ok"
            }
        except Exception as e:
            return {
                "optimized_gcode": optimized_gcode,
                "original_gcode": gcode_text,
                "ai_feedback": None,
                "optimization_metrics": optimize_result.get("data", {}),
                "error": f"Errore nella chiamata AI: {str(e)}",
                "status": "partial"
            }
    
    def _prepare_ai_context(self, gcode_text: str, metrics: Dict, validation: Dict) -> str:
        """Prepara il contesto per l'AI"""
        return f"""
Metriche: {metrics}
Validazione: {validation}
G-code (prime 1000 righe): {gcode_text[:1000]}
"""
    
    def _format_metrics(self, metrics: Dict) -> str:
        """Formatta le metriche per l'AI"""
        return f"""
- Comandi totali: {metrics.get('total_commands', 0)}
- Movimenti: {metrics.get('movement_commands', 0)}
- Movimenti rapidi (G0): {metrics.get('rapid_moves', 0)}
- Movimenti lineari (G1): {metrics.get('linear_moves', 0)}
- Movimenti circolari (G2/G3): {metrics.get('circular_moves', 0)}
- Tempo stimato: {metrics.get('estimated_time_sec', 0):.2f} secondi
- Distanza totale: {metrics.get('total_distance_mm', 0):.2f} mm
- Feedrate max: {metrics.get('max_feedrate', 0):.2f}
- Feedrate medio: {metrics.get('avg_feedrate', 0):.2f}
- Cambi utensile: {metrics.get('tool_changes', 0)}
- Sistema coordinate: {metrics.get('coordinate_system', 'N/A')}
- Unità: {metrics.get('units', 'N/A')}
"""
    
    def _format_validation(self, validation: Dict) -> str:
        """Formatta la validazione per l'AI"""
        errors = validation.get('errors', [])
        warnings = validation.get('warnings', [])
        safety = validation.get('safety_checks', {})
        
        result = f"""
Validità: {'✓ Valido' if validation.get('is_valid', False) else '✗ Non valido'}
Errori: {len(errors)}
Avvisi: {len(warnings)}
"""
        
        if errors:
            result += f"\nErrori trovati:\n" + "\n".join(f"  - {e}" for e in errors)
        
        if warnings:
            result += f"\nAvvisi:\n" + "\n".join(f"  - {w}" for w in warnings)
        
        result += f"""
Controlli sicurezza:
- Comando home: {'✓' if safety.get('has_home_command') else '✗'}
- Unità impostate: {'✓' if safety.get('has_units_set') else '✗'}
- Sistema coordinate: {'✓' if safety.get('has_coordinate_system') else '✗'}
- Fine programma: {'✓' if safety.get('has_program_end') else '✗'}
- Feedrate definito: {'✓' if safety.get('feedrate_defined') else '✗'}
"""
        
        return result
    
    def _extract_suggestions(self, ai_response: str) -> list:
        """Estrae suggerimenti dalla risposta AI"""
        suggestions = []
        lines = ai_response.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                suggestions.append(line.lstrip('-•* ').strip())
            elif 'suggerimento' in line.lower() or 'suggestion' in line.lower():
                suggestions.append(line)
        
        return suggestions if suggestions else ["Nessun suggerimento specifico"]







