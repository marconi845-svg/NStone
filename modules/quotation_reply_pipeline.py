"""
Pipeline risposta cliente su thread email preventivo (Quotations).
"""
from __future__ import annotations

import logging
from datetime import datetime
from email.utils import parseaddr
from typing import Any, Dict, Optional  # Optional used by try_process_quotation_reply

logger = logging.getLogger(__name__)


def _our_gmail_address() -> str:
    try:
        from core.machine_plc_config import load_config

        gmail = load_config().get("gmail") or {}
        if isinstance(gmail, dict):
            return (gmail.get("email") or "").strip().lower()
    except Exception:
        pass
    return ""


def try_process_quotation_reply(
    email_data: Dict[str, Any],
    *,
    use_llm: bool = True,
) -> Optional[str]:
    """
    Se l'email appartiene a un thread preventivo, instrada conferma ordine o follow-up.
    Ritorna kind se gestita: quotation_order_confirmation | quotation_reply.
    """
    from modules.quotation_email_db import turn_exists_by_message_id
    from modules.quotation_email_thread import resolve_quotation_case

    message_id = (email_data.get("message_id") or "").strip()
    if message_id and turn_exists_by_message_id(message_id):
        logger.info("Quotation reply già processata: %s", message_id[:60])
        return "quotation_reply"

    _, addr = parseaddr(email_data.get("from") or "")
    sender = (addr or "").strip().lower()
    our_addr = _our_gmail_address()
    if our_addr and sender == our_addr:
        return None

    case = resolve_quotation_case(email_data)
    if not case:
        return None

    try:
        from modules.quotation_order_confirmation_pipeline import (
            try_process_quotation_order_confirmation,
        )

        if try_process_quotation_order_confirmation(email_data, case, use_llm=use_llm):
            return "quotation_order_confirmation"
    except ImportError as exc:
        logger.debug("Quotation order confirmation non disponibile: %s", exc)

    if process_client_quotation_reply(email_data, case, use_llm=use_llm):
        return "quotation_reply"
    return None


def process_client_quotation_reply(
    email_data: Dict[str, Any],
    case: Optional[Dict[str, Any]] = None,
    *,
    use_llm: bool = True,
) -> bool:
    from modules.email_service import send_threaded_email
    from modules.gemini_module import GeminiReplyError, generate_quotation_thread_reply
    from modules.incoming_requests_db import update_incoming_request
    from modules.quotation_email_thread import (
        build_references_header,
        conversation_for_llm,
        make_reply_subject,
        record_inbound_reply,
        record_outbound_reply,
        resolve_quotation_case,
    )

    if case is None:
        case = resolve_quotation_case(email_data)
    if not case:
        return False

    case_id = case["id"]
    client_email = (case.get("email") or "").strip()
    if not client_email:
        logger.warning("Quotation reply senza email cliente — case %s", case_id)
        return False

    body_in = (email_data.get("body") or "").strip()
    if not body_in:
        logger.info("Quotation reply vuota — skip case %s", case_id)
        return False

    if not use_llm:
        logger.debug("Follow-up preventivo saltato su poll rapido (no LLM) — case %s", case_id)
        return False

    try:
        history = conversation_for_llm(case_id)
        record_inbound_reply(email_data, case_id)

        from modules.knowledge_reply_augment import (
            is_technical_only_message,
            knowledge_config,
        )

        if (
            knowledge_config().get("technical_reply_enabled", True)
            and is_technical_only_message(body_in)
        ):
            from modules.technical_reply_module import generate_technical_thread_reply

            reply_text = generate_technical_thread_reply(case, body_in, history)
        else:
            reply_text = generate_quotation_thread_reply(case, body_in, history)
    except GeminiReplyError as exc:
        logger.error("LLM follow-up preventivo fallito (%s): %s", case_id, exc)
        update_incoming_request(
            case_id,
            {
                "stato": "IN_CONVERSAZIONE",
                "errore_email": str(exc)[:300],
            },
        )
        return True

    if not reply_text:
        return True

    from modules.quotation_auto_pipeline import office_may_auto_email

    if not office_may_auto_email():
        update_incoming_request(
            case_id,
            {
                "stato": "BOZZA_IN_ATTESA",
                "risposta_gemini": reply_text,
                "errore_email": None,
            },
        )
        logger.info(
            "Follow-up preventivo %s in bozza (autonomia non consente invio auto)",
            case_id,
        )
        return True

    in_reply_to = email_data.get("message_id")
    references = build_references_header(case_id, in_reply_to=in_reply_to)
    subject = make_reply_subject(case_id, case.get("nome", "Cliente"))

    send_result = send_threaded_email(
        client_email,
        subject,
        reply_text,
        in_reply_to=in_reply_to,
        references=references or None,
    )

    if send_result.get("sent"):
        record_outbound_reply(
            case_id=case_id,
            body=reply_text,
            subject=subject,
            message_id=send_result.get("message_id") or "",
            in_reply_to=in_reply_to,
            email_references=references,
        )
        update_incoming_request(
            case_id,
            {
                "stato": "IN_CONVERSAZIONE",
                "risposta_gemini": reply_text,
                "email_inviata": True,
                "data_invio_email": datetime.now().isoformat(),
                "errore_email": None,
            },
        )
        logger.info("Quotation thread reply inviata — case %s", case_id)
    else:
        err = send_result.get("error") or "Invio SMTP fallito"
        update_incoming_request(
            case_id,
            {
                "stato": "IN_CONVERSAZIONE",
                "risposta_gemini": reply_text,
                "errore_email": err[:300],
            },
        )
        logger.error("Invio quotation reply fallito (%s): %s", case_id, err)

    return True
