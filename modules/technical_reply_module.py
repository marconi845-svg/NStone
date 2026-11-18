"""
Risposte tecniche cliente via Retrieval Fabric + LLM.
Percorso parallelo — NON usa build_offerte_* né enforce_offerte_catalog_in_reply.
"""
from __future__ import annotations

import traceback
from typing import Dict, List, Optional

from llm.gemini_service import GeminiService
from llm.llm_contexts import (
    build_technical_client_reply_prompt,
    build_technical_thread_reply_prompt,
    resolve_llm_language,
)
from llm.llm_service import get_llm_service, load_llm_config
from core.machine_plc_config import load_config
from modules.gemini_module import GeminiReplyError
from modules.knowledge_reply_augment import build_knowledge_context_for_message


def generate_technical_reply_for_client(request_data: Dict) -> Optional[str]:
    """Risposta a nuova email solo tecnica/policy (no blocco offerta)."""
    try:
        gemini_service = GeminiService()
        if not gemini_service.is_ready:
            llm = get_llm_service()
            raise GeminiReplyError(
                llm.configuration_error_message(),
                code="missing_api_key",
            )

        nome = request_data.get("nome", "Cliente")
        email = request_data.get("email", "")
        messaggio = request_data.get("messaggio", "")

        knowledge_context, hits = build_knowledge_context_for_message(messaggio)
        lang = resolve_llm_language(load_config())
        prompt = build_technical_client_reply_prompt(
            nome=nome,
            email=email,
            messaggio=messaggio,
            knowledge_context=knowledge_context,
            language=lang,
        )

        response = gemini_service.send_message(prompt, business_context="offerte")
        if not response or not str(response).strip():
            provider = load_llm_config().get("provider", "ollama")
            raise GeminiReplyError(
                f"Nessuna risposta ricevuta dal modello ({provider}).",
                code="empty_response",
            )

        text = str(response).strip()
        if text.startswith("Errore:"):
            raise GeminiReplyError(text, code="llm_error")

        _log_technical_reply(messaggio, hits, text)
        return text

    except GeminiReplyError:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise GeminiReplyError(
            f"Errore risposta tecnica: {exc}",
            code="internal_error",
        ) from exc


def generate_technical_thread_reply(
    case: Dict,
    new_message: str,
    history: List[Dict],
) -> Optional[str]:
    """Follow-up tecnico in thread esistente — senza formato offerta."""
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

        combined = f"{messaggio_iniziale}\n{new_message}"
        knowledge_context, hits = build_knowledge_context_for_message(combined)
        lang = resolve_llm_language(load_config())

        history_lines = []
        for turn in history:
            role = "NStone" if turn.get("role") == "assistant" else "Cliente"
            content = (turn.get("content") or "").strip()
            if content:
                history_lines.append(f"{role}: {content}")

        prompt = build_technical_thread_reply_prompt(
            nome=nome,
            email=email,
            messaggio_iniziale=messaggio_iniziale,
            history="\n".join(history_lines),
            nuovo_messaggio=new_message,
            knowledge_context=knowledge_context,
            language=lang,
        )

        response = gemini_service.send_message(prompt, business_context="offerte")
        if not response or not str(response).strip():
            raise GeminiReplyError(
                "Nessuna risposta dal modello per il follow-up tecnico.",
                code="empty_response",
            )

        text = str(response).strip()
        _log_technical_reply(new_message, hits, text, context_key="thread")
        return text

    except GeminiReplyError:
        raise
    except Exception as exc:
        raise GeminiReplyError(
            f"Errore follow-up tecnico: {exc}",
            code="internal_error",
        ) from exc


def _log_technical_reply(
    question: str,
    hits: List[Dict],
    answer: str,
    *,
    context_key: str = "inbound",
) -> None:
    try:
        from modules.knowledge_audit_db import log_retrieval

        log_retrieval(
            question=question,
            context_key=context_key,
            hits=hits or [],
            answer_preview=answer,
            module="technical_reply",
        )
    except Exception:
        pass
