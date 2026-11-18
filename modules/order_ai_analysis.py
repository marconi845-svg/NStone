"""
Analisi ordine on-demand con Gemini (1 chiamata per azione utente, non nel poll IMAP).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

logger = logging.getLogger(__name__)


class OrderAIAnalysisError(Exception):
    def __init__(self, message: str, code: str = "analysis_error"):
        super().__init__(message)
        self.code = code


def analyze_order_email_with_ai(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Estrae campi strutturati da email ordine usando Gemini.

    Args:
        order: dict con almeno email_subject, email_body, client, product, order_id

    Returns:
        dict con materiale, quantita_mq, machine, note, summary
    """
    from llm.gemini_service import GeminiService
    from llm.llm_contexts import build_ordini_extract_prompt, resolve_llm_language
    from core.machine_plc_config import load_config

    lang = resolve_llm_language(load_config())
    service = GeminiService()
    if not service.is_ready:
        from llm.llm_service import get_llm_service

        raise OrderAIAnalysisError(
            get_llm_service().configuration_error_message(),
            code="missing_api_key",
        )

    subject = order.get("email_subject") or order.get("subject") or order.get("product") or ""
    body = order.get("email_body") or order.get("body") or ""
    client = order.get("client") or order.get("client_email") or order.get("from") or ""

    prompt = build_ordini_extract_prompt(client=client, subject=subject, body=body, language=lang)

    response = service.send_message(prompt, business_context="ordini")
    if not response or response.strip().startswith("Errore:"):
        raise OrderAIAnalysisError(response or "Nessuna risposta dal modello LLM", code="llm_error")

    text = response.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OrderAIAnalysisError(
            f"Risposta Gemini non è JSON valido: {exc}",
            code="invalid_json",
        ) from exc

    return {
        "materiale": str(data.get("materiale") or "").strip(),
        "quantita_mq": data.get("quantita_mq"),
        "machine": str(data.get("machine") or "").strip(),
        "note": str(data.get("note") or "").strip(),
        "confidence": float(data.get("confidence", 0.5)),
    }
