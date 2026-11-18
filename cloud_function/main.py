"""
Google Cloud Function - WhatsApp Webhook
Riceve messaggi da WhatsApp Cloud API e li inoltra a un endpoint Windows configurato.
"""

import json
import os
import logging
from typing import Dict, Any, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.parse
    HAS_REQUESTS = False

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def whatsapp_webhook(request):
    """
    Entry point della Cloud Function per il webhook WhatsApp.
    
    Args:
        request: Oggetto request di Flask (fornito automaticamente da Cloud Functions)
    
    Returns:
        Tuple (response_body, status_code): Sempre ("ok", 200)
    """
    try:
        # Leggi il JSON dalla richiesta
        if not request.is_json:
            logger.warning("[WHATSAPP] Richiesta non JSON, ignorata")
            return "ok", 200
        
        raw_json = request.get_json(silent=True)
        if raw_json is None:
            logger.warning("[WHATSAPP] JSON non valido o vuoto")
            return "ok", 200
        
        # Estrai dati dal payload WhatsApp
        from_number, message_text = extract_whatsapp_data(raw_json)
        
        # Log strutturato
        logger.info(f"[WHATSAPP] from={from_number} message={message_text[:50] if message_text else 'N/A'}")
        
        # Prepara payload per inoltro a Windows
        forward_payload = {
            "from": from_number or "",
            "message": message_text or "",
            "raw": raw_json
        }
        
        # Inoltra a endpoint Windows configurato
        forward_to_windows(forward_payload)
        
    except Exception as e:
        # Gestione errori: logga ma non fallisci mai
        logger.error(f"[WHATSAPP] Errore durante elaborazione: {str(e)}", exc_info=True)
    
    # Restituisci sempre 200 OK
    return "ok", 200


def extract_whatsapp_data(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Estrae numero mittente e testo messaggio dal payload WhatsApp.
    
    Args:
        payload: JSON completo ricevuto da WhatsApp Cloud API
    
    Returns:
        Tuple (from_number, message_text): Entrambi possono essere None
    """
    from_number = None
    message_text = None
    
    try:
        # Struttura tipica WhatsApp Cloud API:
        # {
        #   "entry": [{
        #     "changes": [{
        #       "value": {
        #         "messages": [{
        #           "from": "39347XXXXXXX",
        #           "text": {"body": "testo messaggio"}
        #         }]
        #       }
        #     }]
        #   }]
        # }
        
        # Estrai numero mittente
        if "entry" in payload:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    
                    for msg in messages:
                        # Numero mittente
                        if "from" in msg:
                            from_number = str(msg["from"])
                        
                        # Testo messaggio (se presente)
                        if "text" in msg and "body" in msg["text"]:
                            message_text = str(msg["text"]["body"])
                        
                        # Se trovato un messaggio, esci (primo messaggio valido)
                        if from_number or message_text:
                            break
                    
                    if from_number or message_text:
                        break
                if from_number or message_text:
                    break
        
        # Fallback: cerca direttamente nei campi comuni
        if not from_number:
            from_number = payload.get("from") or payload.get("sender")
        
        if not message_text:
            message_text = payload.get("message") or payload.get("text") or payload.get("body")
            if isinstance(message_text, dict):
                message_text = message_text.get("body") or message_text.get("text")
    
    except (KeyError, TypeError, AttributeError) as e:
        logger.warning(f"[WHATSAPP] Errore estrazione dati: {str(e)}")
    
    return from_number, message_text


def forward_to_windows(payload: Dict[str, Any]) -> None:
    """
    Inoltra il payload all'endpoint Windows configurato.
    
    Args:
        payload: Dizionario con dati da inoltrare
    """
    windows_endpoint = os.environ.get("WINDOWS_ENDPOINT_URL")
    
    if not windows_endpoint:
        logger.warning("[WHATSAPP] WINDOWS_ENDPOINT_URL non configurato, skip inoltro")
        return
    
    try:
        # Converti payload in JSON
        json_data = json.dumps(payload).encode('utf-8')
        
        if HAS_REQUESTS:
            # Usa requests se disponibile
            response = requests.post(
                windows_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            response.raise_for_status()
            logger.info(f"[WHATSAPP] Inoltro riuscito: {response.status_code}")
        else:
            # Usa urllib come fallback
            req = urllib.request.Request(
                windows_endpoint,
                data=json_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                logger.info(f"[WHATSAPP] Inoltro riuscito: {response.status}")
    
    except Exception as e:
        # Log errore ma non bloccare l'esecuzione
        logger.error(f"[WHATSAPP] Errore inoltro a Windows: {str(e)}")

