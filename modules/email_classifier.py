"""
Modulo per classificazione email (ORDINE / CONFERMA / NON_RILEVANTE)
Usa regole base + Gemini AI per classificazione semantica
"""
import sys
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

# Aggiungi la root del progetto al path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

try:
    from llm.gemini_service import GeminiService
    from llm.llm_contexts import build_ordini_classify_prompt
except ImportError:
    GeminiService = None
    build_ordini_classify_prompt = None


def classify_email_with_rules(subject: str, body: str, sender: str) -> Tuple[str, float]:
    """
    Classifica email usando regole base (veloce, senza AI)
    
    Args:
        subject: Oggetto email
        body: Corpo email
        sender: Mittente email
        
    Returns:
        Tuple (tipo_email, confidence)
        tipo_email: 'ORDINE', 'CONFERMA', 'NON_RILEVANTE'
        confidence: 0.0-1.0
    """
    subject_lower = subject.lower()
    body_lower = body.lower()
    combined = f"{subject_lower} {body_lower}"

    # Intent ordine: obbligatorio almeno una parola (evita newsletter con solo "marmo")
    order_intent_keywords = [
        'ordine', 'order', 'preventivo', 'richiesta ordine', 'purchase order',
        'acquisto', 'purchase', 'request quote', 'quotation',
    ]
    order_material_keywords = [
        'lastre', 'marmo', 'granito', 'quarzo', 'pietra', 'materiale',
        'marble', 'granite', 'stone', 'slab', 'slabs',
        'quantità', 'quantity', ' mq', ' sqm', 'metri quadri', 'square meter', 'dimensioni', 'spessore',
    ]

    # Parole chiave per CONFERMA
    confirmation_keywords = [
        'confermo', 'conferma', 'confirm', 'confirmed', 'accetto', 'accettato', 'accepted',
        'ok', 'procediamo', 'proceed', 'va bene', 'go ahead', 'approvo', 'approvato',
        'd\'accordo', 'approved',
    ]

    intent_score = sum(
        1 for keyword in order_intent_keywords if keyword in combined
    )
    material_score = sum(
        1 for keyword in order_material_keywords if keyword in combined
    )
    confirmation_score = sum(
        1 for keyword in confirmation_keywords if keyword in subject_lower or keyword in body_lower
    )

    # CONFERMA prima di ORDINE: oggetto "Ordine" + corpo "confermo" non deve creare un nuovo ordine.
    if confirmation_score >= 1:
        return ('CONFERMA', min(0.85, 0.55 + confirmation_score * 0.1))

    # ORDINE solo con intento esplicito (+ eventuale contesto materiale)
    if intent_score >= 1 and (intent_score + material_score) >= 2:
        return ('ORDINE', min(0.85, 0.55 + intent_score * 0.1))
    if intent_score >= 1 and (
        'ordine' in subject_lower or 'order' in subject_lower
        or 'preventivo' in subject_lower or 'quotation' in subject_lower or 'quote' in subject_lower
    ):
        try:
            from modules.order_inbox_noise import is_inbox_noise

            if is_inbox_noise(subject=subject, body=body, sender=sender):
                return ('NON_RILEVANTE', 0.9)
        except ImportError:
            pass
        return ('ORDINE', 0.65)
    else:
        return ('NON_RILEVANTE', 0.3)


def classify_email_with_gemini(subject: str, body: str, sender: str) -> Optional[Tuple[str, float]]:
    """
    Classifica email usando Gemini AI (più accurato)
    
    Args:
        subject: Oggetto email
        body: Corpo email
        sender: Mittente email
        
    Returns:
        Tuple (tipo_email, confidence) o None se errore
    """
    if not GeminiService or not build_ordini_classify_prompt:
        return None
    
    try:
        gemini_service = GeminiService()
        
        if not gemini_service.is_ready:
            return None
        
        from core.machine_plc_config import load_config
        from llm.llm_contexts import resolve_llm_language

        lang = resolve_llm_language(load_config())
        prompt = build_ordini_classify_prompt(
            sender=sender, subject=subject, body=body, language=lang
        )

        response = gemini_service.send_message(
            prompt,
            business_context="ordini",
        )
        
        if not response or not response.strip():
            return None
        
        # Pulisci risposta (rimuovi markdown code blocks)
        response_clean = response.strip()
        if response_clean.startswith("```"):
            lines = response_clean.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            response_clean = "\n".join(lines)
        
        # Parse JSON
        try:
            result = json.loads(response_clean)
            
            tipo = result.get("tipo", "NON_RILEVANTE")
            confidence = float(result.get("confidence", 0.5))
            
            # Valida tipo
            if tipo not in ["ORDINE", "CONFERMA", "NON_RILEVANTE"]:
                tipo = "NON_RILEVANTE"
            
            # Valida confidence
            confidence = max(0.0, min(1.0, confidence))
            
            return (tipo, confidence)
            
        except json.JSONDecodeError:
            # Fallback a regole se JSON non valido
            return classify_email_with_rules(subject, body, sender)
            
    except Exception as e:
        print(f"Errore classificazione Gemini: {e}")
        # Fallback a regole
        return classify_email_with_rules(subject, body, sender)


def classify_email(subject: str, body: str, sender: str, use_ai: bool = True) -> Tuple[str, float]:
    """
    Classifica email usando regole base + opzionalmente Gemini AI
    
    Args:
        subject: Oggetto email
        body: Corpo email
        sender: Mittente email
        use_ai: Se True, usa Gemini dopo regole base
        
    Returns:
        Tuple (tipo_email, confidence)
    """
    # Prima prova con regole base (veloce)
    tipo, confidence = classify_email_with_rules(subject, body, sender)
    
    # Se confidence bassa e AI disponibile, usa Gemini
    if use_ai and confidence < 0.6 and GeminiService:
        gemini_result = classify_email_with_gemini(subject, body, sender)
        if gemini_result:
            tipo, confidence = gemini_result
    
    return (tipo, confidence)

