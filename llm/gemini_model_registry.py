"""
Registry per la gestione dei modelli Gemini disponibili
Fornisce discovery automatico e fallback intelligente
"""
import os
from typing import Optional, List
from google import genai

# Cache dei modelli disponibili
_available_models: List[str] = []
_model_client: Optional[genai.Client] = None


def initialize_registry(api_key: Optional[str] = None) -> None:
    """
    Inizializza il registry caricando i modelli disponibili
    
    Args:
        api_key: Chiave API di Google Gemini. Se None, cerca nella variabile d'ambiente GEMINI_API_KEY
    """
    global _available_models, _model_client
    
    if _model_client is not None:
        return  # Già inizializzato
    
    api_key = api_key or os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("[GEMINI MODEL REGISTRY] API key non trovata. Il registry non può essere inizializzato.")
        return
    
    try:
        _model_client = genai.Client(api_key=api_key)
        models_list = list(_model_client.models.list())
        _available_models = [m.name for m in models_list]
        
        print("\n" + "="*80)
        print("[GEMINI MODEL REGISTRY] Modelli disponibili:")
        print("="*80)
        for model in _available_models:
            print(f"  - {model}")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"[GEMINI MODEL REGISTRY] Errore durante il caricamento dei modelli: {e}")
        _available_models = []


def list_available_models() -> List[str]:
    """
    Restituisce la lista dei modelli disponibili
    
    Returns:
        Lista dei nomi dei modelli disponibili
    """
    return _available_models.copy()


def get_model(preferred_name: str, api_key: Optional[str] = None) -> str:
    """
    Restituisce il nome del modello da usare, con fallback intelligente
    
    Args:
        preferred_name: Nome del modello preferito (es. "gemini-1.5-flash")
        api_key: Chiave API (opzionale, per inizializzare se necessario)
    
    Returns:
        Nome del modello da usare (es. "models/gemini-1.5-flash-001")
    
    Raises:
        ValueError: Se nessun modello è disponibile
    """
    global _available_models, _model_client
    
    # Inizializza se necessario
    if not _available_models:
        initialize_registry(api_key)
    
    if not _available_models:
        # Fallback: usa il nome preferito anche se non abbiamo la lista
        print(f"[GEMINI MODEL FALLBACK] Nessun modello disponibile nel registry, uso: {preferred_name}")
        return preferred_name
    
    # 1. Match esatto (con o senza prefisso "models/")
    preferred_normalized = preferred_name
    if not preferred_normalized.startswith("models/"):
        preferred_normalized = f"models/{preferred_normalized}"
    
    for model in _available_models:
        if model == preferred_normalized or model == preferred_name:
            return model
    
    # 2. Match per prefisso (es. "gemini-1.5-flash" → "models/gemini-1.5-flash-001")
    preferred_base = preferred_name.replace("models/", "").split("-")
    for model in _available_models:
        model_base = model.replace("models/", "").split("-")
        # Confronta i primi 3 componenti (es. ["gemini", "1", "5", "flash"])
        if len(preferred_base) >= 3 and len(model_base) >= 3:
            if preferred_base[:3] == model_base[:3]:
                if len(preferred_base) >= 4 and len(model_base) >= 4:
                    if preferred_base[3] == model_base[3]:  # Match anche su "flash" o "pro"
                        print(f"[GEMINI MODEL FALLBACK] Requested: {preferred_name} → Using: {model}")
                        return model
                elif len(preferred_base) == 3:  # Preferito ha solo 3 componenti
                    print(f"[GEMINI MODEL FALLBACK] Requested: {preferred_name} → Using: {model}")
                    return model
    
    # 3. Match per versione (es. "gemini-1.5" → qualsiasi "gemini-1.5-*")
    if len(preferred_base) >= 2:
        for model in _available_models:
            model_base = model.replace("models/", "").split("-")
            if len(model_base) >= 2:
                if preferred_base[:2] == model_base[:2]:
                    print(f"[GEMINI MODEL FALLBACK] Requested: {preferred_name} → Using: {model}")
                    return model
    
    # 4. Fallback al primo modello flash disponibile
    for model in _available_models:
        if "flash" in model.lower():
            print(f"[GEMINI MODEL FALLBACK] Requested: {preferred_name} → Using: {model} (first flash model)")
            return model
    
    # 5. Fallback al primo modello pro disponibile
    for model in _available_models:
        if "pro" in model.lower():
            print(f"[GEMINI MODEL FALLBACK] Requested: {preferred_name} → Using: {model} (first pro model)")
            return model
    
    # 6. Fallback al primo modello disponibile
    if _available_models:
        print(f"[GEMINI MODEL FALLBACK] Requested: {preferred_name} → Using: {_available_models[0]} (first available)")
        return _available_models[0]
    
    # 7. Ultimo fallback: usa il nome preferito
    print(f"[GEMINI MODEL FALLBACK] Nessun modello disponibile, uso: {preferred_name}")
    return preferred_name

