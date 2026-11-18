"""
Modulo Gemini per generazione risposte a richieste clienti e analisi conferme ordine
"""
import sys
import json
from pathlib import Path
from typing import Dict, Optional

# Aggiungi la root del progetto al path per importare gemini_service
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from llm.gemini_service import GeminiService
from llm.llm_service import get_llm_service, load_llm_config
from llm.llm_contexts import (
    build_offerte_client_reply_prompt,
    build_offerte_thread_reply_prompt,
    build_ordini_confirmation_prompt,
    build_ordini_stock_confirmation_prompt,
    resolve_llm_language,
)
from core.machine_plc_config import load_config


class GeminiReplyError(Exception):
    """Errore configurazione o chiamata LLM (messaggio leggibile per UI/API)."""

    def __init__(self, message: str, code: str = "gemini_error"):
        super().__init__(message)
        self.code = code


def generate_reply_for_client(request_data: Dict) -> Optional[str]:
    """
    Genera una risposta professionale per una richiesta cliente usando Gemini
    
    Args:
        request_data: Dizionario con chiavi:
            - nome: Nome del cliente
            - email: Email del cliente
            - messaggio: Messaggio/richiesta del cliente
            
    Returns:
        Testo della risposta generata da Gemini, o None in caso di errore
    """
    try:
        gemini_service = GeminiService()
        if not gemini_service.is_ready:
            llm = get_llm_service()
            raise GeminiReplyError(
                llm.configuration_error_message(),
                code="missing_api_key",
            )

        # Estrai i dati della richiesta
        nome = request_data.get("nome", "Cliente")
        email = request_data.get("email", "")
        messaggio = request_data.get("messaggio", "")

        from modules.catalog_db import (
            build_pricing_context_for_message,
            enforce_offerte_catalog_in_reply,
            find_catalog_matches_for_message,
            format_catalog_context_for_offerte,
        )

        matches = find_catalog_matches_for_message(messaggio)
        lang = resolve_llm_language(load_config())
        catalog_context = format_catalog_context_for_offerte(matches, language=lang)
        pricing_context, _pricing = build_pricing_context_for_message(messaggio, matches)

        prompt = build_offerte_client_reply_prompt(
            nome=nome,
            email=email,
            messaggio=messaggio,
            catalog_context=catalog_context,
            pricing_context=pricing_context,
            language=lang,
        )

        response = gemini_service.send_message(
            prompt,
            business_context="offerte",
        )

        provider = load_llm_config().get("provider", "ollama")
        if not response or not isinstance(response, str) or not response.strip():
            raise GeminiReplyError(
                f"Nessuna risposta ricevuta dal modello ({provider}).",
                code="empty_response",
            )

        text = enforce_offerte_catalog_in_reply(
            response.strip(),
            matches,
            customer_message=messaggio,
            language=lang,
        )
        if text.startswith("Errore:"):
            raise GeminiReplyError(text, code="gemini_api_error")

        return text

    except GeminiReplyError:
        raise
    except Exception as e:
        print(f"Errore nella generazione risposta Gemini: {e}")
        import traceback
        traceback.print_exc()
        raise GeminiReplyError(
            f"Errore interno durante la generazione della risposta: {e}",
            code="internal_error",
        ) from e


def generate_quotation_thread_reply(
    case: Dict,
    new_message: str,
    history: list,
) -> Optional[str]:
    """Genera risposta di follow-up in un thread email preventivo."""
    try:
        gemini_service = GeminiService()
        if not gemini_service.is_ready:
            llm = get_llm_service()
            raise GeminiReplyError(
                llm.configuration_error_message(),
                code="missing_api_key",
            )

        nome = case.get("nome", "Cliente")
        email = case.get("email", "")
        messaggio_iniziale = case.get("messaggio", "")

        from modules.catalog_db import (
            build_pricing_context_for_message,
            enforce_offerte_catalog_in_reply,
            find_catalog_matches_for_message,
            format_catalog_context_for_offerte,
        )

        combined = f"{messaggio_iniziale}\n{new_message}"
        lang = resolve_llm_language(load_config())
        matches = find_catalog_matches_for_message(combined)
        catalog_context = format_catalog_context_for_offerte(matches, language=lang)
        pricing_context, _pricing = build_pricing_context_for_message(combined, matches)

        history_lines = []
        for turn in history:
            role = "NStone" if turn.get("role") == "assistant" else "Cliente"
            content = (turn.get("content") or "").strip()
            if content:
                history_lines.append(f"{role}: {content}")

        prompt = build_offerte_thread_reply_prompt(
            nome=nome,
            email=email,
            messaggio_iniziale=messaggio_iniziale,
            history="\n".join(history_lines),
            nuovo_messaggio=new_message,
            catalog_context=catalog_context,
            pricing_context=pricing_context,
            language=lang,
        )

        response = gemini_service.send_message(
            prompt,
            business_context="offerte",
        )
        if not response or not str(response).strip():
            raise GeminiReplyError(
                "Nessuna risposta dal modello per il follow-up preventivo.",
                code="empty_response",
            )
        return enforce_offerte_catalog_in_reply(
            str(response).strip(),
            matches,
            customer_message=combined,
            language=lang,
        )
    except GeminiReplyError:
        raise
    except Exception as exc:
        raise GeminiReplyError(
            f"Errore follow-up preventivo: {exc}",
            code="internal_error",
        ) from exc


def analyze_order_confirmation(email_body: str, order_data: Dict) -> Optional[Dict]:
    """
    Analizza una risposta del cliente per determinare se conferma l'ordine usando Gemini
    
    Args:
        email_body: Corpo dell'email del cliente
        order_data: Dizionario con i dati dell'ordine originale:
            - id: ID dell'ordine
            - from: Email del cliente
            - subject: Oggetto dell'ordine
            - body: Corpo dell'ordine originale
            - timestamp: Timestamp dell'ordine
            
    Returns:
        Dizionario con il risultato dell'analisi:
        {
            "status": "confirmed" | "pending" | "cancelled",
            "notes": "Note aggiuntive",
            "confirmation_email_text": "Testo per la mail di conferma (opzionale)"
        }
        Oppure None in caso di errore
    """
    try:
        # Inizializza il servizio Gemini
        gemini_service = GeminiService()
        
        if not gemini_service.is_ready:
            return None
        
        # Estrai i dati dell'ordine
        order_id = order_data.get("id", "UNKNOWN")
        client_email = order_data.get("from", "")
        original_subject = order_data.get("subject", "")
        original_body = order_data.get("body", "")
        
        lang = resolve_llm_language(load_config())
        prompt = build_ordini_confirmation_prompt(
            order_id=order_id,
            client_email=client_email,
            original_subject=original_subject,
            original_body=original_body,
            email_body=email_body,
            language=lang,
        )

        response = gemini_service.send_message(
            prompt,
            business_context="ordini",
        )
        
        if not response or not isinstance(response, str) or not response.strip():
            return None
        
        # Pulisci la risposta (rimuovi markdown code blocks se presenti)
        response_clean = response.strip()
        if response_clean.startswith("```"):
            # Rimuovi code block markers
            lines = response_clean.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            response_clean = "\n".join(lines)
        
        # Prova a parsare come JSON
        try:
            result = json.loads(response_clean)
            
            # Valida la struttura
            if not isinstance(result, dict):
                return None
            
            status = result.get("status", "pending")
            if status not in ["confirmed", "pending", "cancelled"]:
                status = "pending"
            
            return {
                "status": status,
                "notes": result.get("notes", ""),
                "confirmation_email_text": result.get("confirmation_email_text", "")
            }
        except json.JSONDecodeError:
            from modules.pipeline_keywords import json_fallback_confirmation_status

            response_lower = response_clean.lower()
            fb = json_fallback_confirmation_status(response_lower)
            if fb == "confirmed":
                return {
                    "status": "confirmed",
                    "notes": "Confirmation detected in text",
                    "confirmation_email_text": ""
                }
            if fb == "cancelled":
                return {
                    "status": "cancelled",
                    "notes": "Cancellation detected in text",
                    "confirmation_email_text": ""
                }
            if "confermo" in response_lower or "conferma" in response_lower or "accetto" in response_lower:
                return {
                    "status": "confirmed",
                    "notes": "Conferma rilevata dal testo",
                    "confirmation_email_text": ""
                }
            elif "cancello" in response_lower or "annulla" in response_lower or "non voglio" in response_lower:
                return {
                    "status": "cancelled",
                    "notes": "Cancellazione rilevata dal testo",
                    "confirmation_email_text": ""
                }
            else:
                return {
                    "status": "pending",
                    "notes": "Stato non determinato",
                    "confirmation_email_text": ""
                }
            
    except Exception as e:
        print(f"Errore nell'analisi conferma ordine Gemini: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_confirmation_with_stock(
    email_body: str,
    order_data: Dict,
    stock_report: Dict,
) -> Optional[Dict]:
    """
    Analizza conferma cliente e genera email NStone con esito disponibilità magazzino.

    Returns:
        status: confirmed | pending | cancelled
        availability: available | partial | unavailable | unknown
        confirmation_email_text: corpo mail da inviare (se confirmed)
        notes, confidence
    """
    try:
        gemini_service = GeminiService()
        if not gemini_service.is_ready:
            return None

        order_id = order_data.get("id", "UNKNOWN")

        lang = resolve_llm_language(load_config())
        prompt = build_ordini_stock_confirmation_prompt(
            order_id=order_id,
            order_data=order_data,
            email_body=email_body,
            stock_report=stock_report,
            language=lang,
        )

        response = gemini_service.send_message(
            prompt,
            business_context="ordini",
        )
        if not response or not str(response).strip():
            return None

        response_clean = response.strip()
        if response_clean.startswith("```"):
            lines = [
                line for line in response_clean.split("\n")
                if not line.strip().startswith("```")
            ]
            response_clean = "\n".join(lines)

        result = json.loads(response_clean)
        if not isinstance(result, dict):
            return None

        status = result.get("status", "pending")
        if status not in ("confirmed", "pending", "cancelled"):
            status = "pending"

        availability = result.get("availability") or stock_report.get("availability", "unknown")

        return {
            "status": status,
            "availability": availability,
            "confidence": float(result.get("confidence", 0.7)),
            "notes": result.get("notes", ""),
            "confirmation_email_text": result.get("confirmation_email_text", ""),
        }
    except Exception as e:
        print(f"Errore analyze_confirmation_with_stock: {e}")
        import traceback
        traceback.print_exc()
        return None


