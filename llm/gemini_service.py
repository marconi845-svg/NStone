"""
Servizio LLM: delega il testo a llm_service (Ollama locale o Gemini cloud).
Gemini SDK resta per analyze_session (visione immagini).
"""
import os
import json
import traceback
import mimetypes
from pathlib import Path
from google import genai
from typing import List, Dict, Optional
from llm.gemini_model_registry import get_model, initialize_registry
from llm.llm_service import get_llm_service, load_llm_config

# Prova a caricare variabili da .env se disponibile
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv non installato, usa solo variabili d'ambiente

class GeminiService:
    def __init__(self, api_key: Optional[str] = None):
        """
        Inizializza il servizio Gemini
        
        Args:
            api_key: Chiave API di Google Gemini. Se None, cerca nella variabile d'ambiente GEMINI_API_KEY
        """
        # Ordine di priorità: argomento -> variabile d'ambiente -> config.json (stesso percorso di settings_window.py)
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or self._load_api_key_from_config()
        self._llm = get_llm_service()
        self.is_beta_mode = not self.is_ready
        
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            # Inizializza il registry dei modelli
            initialize_registry(self.api_key)
        else:
            self.client = None

    def _load_api_key_from_config(self) -> Optional[str]:
        """Carica l'API key da config.json se presente"""
        try:
            # Stesso percorso di settings_window.py: config.json nella dir del modulo
            config_path = Path(__file__).resolve().parents[1] / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("api_key")
        except Exception as e:
            print(f"Errore nel caricamento dell'API key da config.json: {e}")
        return None

    @property
    def is_ready(self) -> bool:
        """True se il provider LLM configurato (Ollama o Gemini) è utilizzabile."""
        self._llm._config = load_llm_config()
        self._llm.provider = self._llm._config.get("provider", "ollama")
        return self._llm.is_configured()
    
    def send_message(
        self,
        prompt: str,
        history: List[Dict[str, str]] = None,
        system_instruction: str = "",
        fast: bool = False,
        request_kind: str = "production",
        business_context: Optional[str] = None,
    ) -> str:
        """
        Invia un messaggio al modello LLM configurato (Ollama o Gemini).
        """
        self.api_key = self._load_api_key_from_config()
        self._llm = get_llm_service()
        return self._llm.send_message(
            prompt,
            history,
            system_instruction,
            fast=fast,
            request_kind=request_kind,  # type: ignore[arg-type]
            business_context=business_context,  # type: ignore[arg-type]
        )
    
    def analyze_session(self, session_dir: Path) -> Optional[Dict]:
        """
        Analizza una sessione di foto usando direttamente l'SDK Gemini.
        
        Args:
            session_dir: Path della cartella sessione contenente request.json e le foto
            
        Returns:
            Dizionario con session_id e analysis, o None in caso di errore
        """
        try:
            # Verifica che l'API key sia configurata
            self.api_key = self._load_api_key_from_config()
            if not self.api_key:
                print("Errore: API Key Gemini non configurata")
                return None
            
            # Ricrea il client se necessario
            if not self.client or self.api_key != getattr(self, '_last_api_key', None):
                self.client = genai.Client(api_key=self.api_key)
                self._last_api_key = self.api_key
                initialize_registry(self.api_key)
            
            # Leggi il file request.json dalla sessione
            request_file = session_dir / "request.json"
            if not request_file.exists():
                print(f"File request.json non trovato in {session_dir}")
                return None
            
            with open(request_file, 'r', encoding='utf-8') as f:
                request_data = json.load(f)
            
            session_id = request_data.get("session_id", "unknown")
            photo_filenames = request_data.get("photos", [])
            
            if not photo_filenames:
                print("Nessuna foto trovata nella sessione")
                return None
            
            # Carica le immagini dalla sessione
            image_parts = []
            for photo_filename in photo_filenames:
                photo_path = session_dir / photo_filename
                if not photo_path.exists():
                    print(f"Foto non trovata: {photo_path}")
                    continue
                
                try:
                    # Carica il file come FileData per Gemini
                    mime, _ = mimetypes.guess_type(photo_path)
                    uploaded_file = self.client.files.upload(
                        file=open(photo_path, "rb"),
                        mime_type=mime
                    )
                    image_parts.append({
                        "file_data": {
                            "file_uri": uploaded_file.uri,
                            "mime_type": uploaded_file.mime_type
                        }
                    })
                except Exception as e:
                    print(f"Errore nel caricamento della foto {photo_filename}: {e}")
                    # Fallback: prova a leggere come base64 se upload fallisce
                    try:
                        import base64
                        with open(photo_path, 'rb') as img_file:
                            img_data = base64.b64encode(img_file.read()).decode('utf-8')
                            # Determina MIME type dall'estensione
                            ext = photo_path.suffix.lower()
                            mime_type = {
                                '.jpg': 'image/jpeg',
                                '.jpeg': 'image/jpeg',
                                '.png': 'image/png',
                                '.gif': 'image/gif',
                                '.bmp': 'image/bmp'
                            }.get(ext, 'image/jpeg')
                            
                            image_parts.append({
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": img_data
                                }
                            })
                    except Exception as e2:
                        print(f"Errore anche nel fallback base64: {e2}")
                        continue
            
            if not image_parts:
                print("Nessuna immagine valida caricata")
                return None
            
            # Costruisci il prompt per l'analisi
            photos_str = ", ".join(photo_filenames)
            prompt = f"""
Sei un sistema di ispezione qualità per lastre di marmo.

Analizza le seguenti foto: {photos_str}.

RISPONDI ESCLUSIVAMENTE con un JSON valido con questa struttura:

{{
  "material_identity": "string",
  "grade": "1ST | 2ND | COMMERCIAL",
  "confidence": 0-100,
  "description": "string",
  "defects": [
    "string"
  ],
  "granulometry": "string",
  "color": "string",
  "classification": "1ST | 2ND | COMMERCIAL"
}}

Tutti i campi devono essere valorizzati.
Se non ci sono difetti visibili, imposta "defects": ["Nessun difetto visibile rilevato"].

NON AGGIUNGERE testo fuori dal JSON.
"""
            
            # Prepara il contenuto con immagini e prompt
            contents = [{
                "role": "user",
                "parts": image_parts + [{"text": prompt}]
            }]
            
            # Ottieni il modello (usa gemini-2.5-flash o fallback)
            model_name = get_model("models/gemini-2.5-flash", self.api_key) or get_model("gemini-1.5-flash", self.api_key)
            
            if not model_name:
                print("Errore: Nessun modello Gemini disponibile")
                return None
            
            # Esegui la chiamata al modello
            print(f"Chiamata a Gemini con modello {model_name} per analisi sessione {session_id}")
            response = self.client.models.generate_content(
                model=model_name,
                contents=contents
            )
            
            # Parsa il JSON dalla risposta
            raw = response.text.strip()
            print("=== RAW GEMINI RESPONSE ===")
            print(raw)
            
            if not raw:
                raise ValueError("Gemini ha restituito una risposta vuota. Probabile errore nell'upload o nel prompt.")
            
            if raw.startswith("```"):
                raw = raw.strip("`")
                raw = raw.replace("json", "", 1).strip()
            
            analysis = json.loads(raw)
            
            print("=== JSON ANALYSIS OUTPUT ===")
            print(analysis)
            
            # Ritorna il dizionario con session_id e analysis
            return {
                "session_id": session_id,
                "analysis": analysis
            }
                
        except Exception as e:
            print(f"Errore in analyze_session: {e}")
            traceback.print_exc()
            return None
    
    def _get_demo_response(self, prompt: str, system_instruction: str) -> str:
        """Genera una risposta demo per la modalità beta"""
        prompt_lower = prompt.lower()
        
        # Risposte demo basate sul contesto
        if "quotation" in prompt_lower or "preventivo" in prompt_lower or "prezzo" in prompt_lower:
            return """Ecco una quotazione indicativa per materiali in pietra naturale:

• Carrara Marble (Bianco Carrara): €45-65/m²
• Calacatta Gold: €120-180/m²
• Travertine: €35-55/m²
• Granite: €40-70/m²

I prezzi variano in base a:
- Spessore (2cm standard, 3cm premium)
- Finitura (polished, honed, brushed)
- Quantità ordinata
- Trasporto e installazione

Vuoi una quotazione dettagliata per un progetto specifico?"""
        
        elif "order" in prompt_lower or "ordine" in prompt_lower or "status" in prompt_lower:
            return """Stato Ordini - Aggiornamento:

📦 Ordine #1234 - Calacatta Gold
   Status: In produzione
   Robot assegnato: R-07
   Tempo stimato: 5-7 giorni lavorativi
   Prossimo step: Taglio lastre

📦 Ordine #1235 - Carrara Venatino
   Status: In lavorazione
   Robot assegnato: R-12
   Tempo stimato: 3-5 giorni lavorativi
   Prossimo step: Lucidatura

Vuoi maggiori dettagli su un ordine specifico?"""
        
        elif "production" in prompt_lower or "produzione" in prompt_lower or "lavorazione" in prompt_lower:
            return """Stato Produzione - Linea Attiva:

⚙️ Linea 1: Taglio lastre
   Materiale: Carrara White Classic
   Progresso: 65% completato
   Tempo rimanente: ~2 ore

⚙️ Linea 2: Lucidatura
   Materiale: Calacatta Borghini
   Progresso: 40% completato
   Tempo rimanente: ~4 ore

⚙️ Linea 3: Trattamento resina
   Materiale: Travertine
   Status: In attesa
   Inizio previsto: Domani 08:00

Tutte le linee operano normalmente."""
        
        elif "document" in prompt_lower or "documento" in prompt_lower or "certificato" in prompt_lower:
            return """Documenti Disponibili:

📄 Certificati di Sicurezza:
   - Certificato CE per Carrara Marble
   - Certificato ISO 14001
   - Certificato di Qualità UNI EN 1469

📄 Schede Tecniche:
   - Scheda tecnica Bianco Carrara CD
   - Scheda tecnica Calacatta Gold
   - Scheda tecnica Travertine

📄 Documenti di Spedizione:
   - DDT #2024-001 (Ordine #1234)
   - DDT #2024-002 (Ordine #1235)
   - Fattura #2024-045

Quale documento vuoi visualizzare?"""
        
        elif "shipment" in prompt_lower or "spedizione" in prompt_lower or "collection" in prompt_lower:
            return """Stato Spedizioni - Logistica:

🚚 Camion #T-001
   Destinazione: Milano, Italia
   Carico: Ordine #1234
   Status: In transito
   ETA: Domani 14:00

🚚 Camion #T-002
   Destinazione: Roma, Italia
   Carico: Ordine #1235
   Status: In preparazione
   Partenza prevista: Domani 08:00

🚚 Camion #T-003
   Destinazione: Torino, Italia
   Carico: Ordine #1236
   Status: In carico
   Partenza prevista: Oggi 16:00

Tutti i trasporti sono in orario."""
        
        else:
            return f"""Grazie per la tua richiesta: "{prompt}"

In modalità beta, questa è una risposta demo. Per utilizzare le funzionalità complete con AI, configura la chiave API Gemini.

Il sistema è progettato per gestire:
• Gestione inventario pietre naturali
• Preventivi e quotazioni
• Tracciamento ordini
• Monitoraggio produzione
• Gestione documenti
• Coordinamento logistica

Come posso aiutarti oggi?"""


if __name__ == "__main__":
    """Test del servizio Gemini"""
    print("=" * 60)
    print("NSTONELLM - Test Gemini Service")
    print("=" * 60)
    print()
    
    # Inizializza il servizio
    service = GeminiService()
    
    if not service.api_key:
        print("[WARNING] API Key non configurata.")
        print("Il servizio funzionerà in modalità beta (risposte demo).")
        print("Per usare Gemini AI, configura GEMINI_API_KEY o aggiungi 'api_key' in config.json")
        print()
    
    print("[OK] Gemini Service inizializzato")
    print()
    print("Test invio messaggio...")
    print("-" * 60)
    
    # Test con una domanda semplice
    test_message = "Ciao, come funziona il sistema NSTONELLM?"
    print(f"Domanda: {test_message}")
    print()
    
    try:
        response = service.send_message(test_message)
        print("Risposta:")
        print(response)
        print()
        print("=" * 60)
        print("[OK] Test completato con successo!")
    except Exception as e:
        print(f"[ERRORE] Errore durante il test: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)

