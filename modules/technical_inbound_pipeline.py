"""
Email inbound solo tecniche/policy — percorso parallelo a quotation_inbound_pipeline.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)

from modules.quotation_inbound_pipeline import (
    RE_PREFIX_RE,
    _our_gmail_address,
    _sender_identity,
)


def is_inbound_technical_inquiry(subject: str, body: str) -> bool:
    """Nuova email tecnica/policy senza intento preventivo commerciale."""
    from modules.knowledge_reply_augment import (
        is_technical_only_message,
        knowledge_config,
    )
    from modules.quotation_inbound_pipeline import is_inbound_quotation_request

    if not knowledge_config().get("technical_inbound_enabled", True):
        return False

    subj = (subject or "").strip()
    if RE_PREFIX_RE.match(subj):
        return False

    combined = f"{subj} {(body or '')}".strip()
    if not is_technical_only_message(combined):
        return False

    if is_inbound_quotation_request(subject, body):
        return False

    try:
        from modules.orders_imap_service import is_commercial_spam_email

        if is_commercial_spam_email({"subject": subject, "body": body, "from": ""}):
            return False
    except Exception:
        pass

    return True


def try_process_inbound_technical_request(email_data: Dict[str, Any]) -> bool:
    """
    Converte email tecnica in incoming_request ed elabora via technical_auto_pipeline.
    Ritorna True se gestita come richiesta tecnica (non preventivo).
    """
    from modules.quotation_email_db import turn_exists_by_message_id
    from modules.quotation_email_thread import resolve_quotation_case

    if resolve_quotation_case(email_data):
        return False

    subject = email_data.get("subject") or ""
    body = (email_data.get("body") or "").strip()
    if not is_inbound_technical_inquiry(subject, body):
        return False

    message_id = (email_data.get("message_id") or "").strip()
    if message_id and turn_exists_by_message_id(message_id):
        logger.info("Email tecnica già processata: %s", message_id[:60])
        return True

    from_header = email_data.get("from") or ""
    nome, client_email = _sender_identity(from_header)
    if not client_email:
        return False

    our_addr = _our_gmail_address()
    if our_addr and client_email.lower() == our_addr:
        return False

    return bool(_create_and_elaborate_technical_from_email(
        nome=nome,
        client_email=client_email,
        subject=subject,
        body=body,
        timestamp=email_data.get("timestamp") or "",
        message_id=message_id,
    ))


def _create_and_elaborate_technical_from_email(
    *,
    nome: str,
    client_email: str,
    subject: str,
    body: str,
    timestamp: str,
    message_id: str,
) -> bool:
    from modules.incoming_requests_db import insert_incoming_request
    from modules.quotation_auto_pipeline import office_may_auto_email
    from modules.quotation_email_db import insert_turn
    from modules.technical_auto_pipeline import elaborate_technical_request

    request_id = str(uuid.uuid4())
    messaggio = body
    if subject and subject.lower() not in body.lower()[:80]:
        messaggio = f"Oggetto: {subject.strip()}\n\n{body}"

    ins = insert_incoming_request(
        {
            "id": request_id,
            "timestamp": timestamp or None,
            "nome": nome,
            "email": client_email,
            "messaggio": messaggio,
            "stato": "NUOVA_TECNICA",
        }
    )
    if not ins.get("ok"):
        logger.error("Insert incoming_request tecnica fallito: %s", ins.get("error"))
        return False

    if message_id:
        insert_turn(
            case_id=request_id,
            direction="inbound",
            body=messaggio,
            subject=subject,
            message_id=message_id,
            source="email_inbound_technical",
        )

    logger.info(
        "Richiesta tecnica da email — case %s da %s",
        request_id,
        client_email,
    )

    send = True if office_may_auto_email() else False
    result = elaborate_technical_request(request_id, send_email=send)

    if not result.get("ok") and not result.get("skipped"):
        logger.warning("Elaborazione email tecnica fallita: %s", result.get("error"))
    return True
