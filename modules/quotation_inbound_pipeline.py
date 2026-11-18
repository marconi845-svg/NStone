"""
Email in arrivo su Gmail con parole chiave preventivo/richiesta → pipeline Quotations.
"""
from __future__ import annotations

import logging
import re
import uuid
from email.utils import parseaddr
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from modules.pipeline_keywords import (
    CONFIRMATION_BLOCK_KEYWORDS as CONFIRMATION_BLOCK,
    QUOTATION_CONTEXT_KEYWORDS,
    QUOTATION_INBOUND_KEYWORDS as QUOTATION_KEYWORDS,
    STONE_CONTEXT_KEYWORDS,
    offer_term_requires_stone_context,
    text_contains_any,
)

RE_PREFIX_RE = re.compile(r"^(re|fwd|fw)\s*:\s*", re.IGNORECASE)


def _our_gmail_address() -> str:
    try:
        from core.machine_plc_config import load_config

        gmail = load_config().get("gmail") or {}
        if isinstance(gmail, dict):
            return (gmail.get("email") or "").strip().lower()
    except Exception:
        pass
    return ""


def is_inbound_quotation_request(subject: str, body: str) -> bool:
    """Nuova richiesta commerciale (non risposta thread, non conferma ordine, no job spam)."""
    subj = (subject or "").strip()
    if RE_PREFIX_RE.match(subj):
        return False

    combined = f"{subj} {(body or '')}".lower()

    try:
        from modules.orders_imap_service import is_commercial_spam_email

        if is_commercial_spam_email({"subject": subject, "body": body, "from": ""}):
            return False
    except Exception:
        pass

    if not text_contains_any(combined, QUOTATION_KEYWORDS):
        return False

    # "offerta" / "offer" da sola (Indeed, marketing) — serve contesto pietra/preventivo
    if offer_term_requires_stone_context(combined):
        return False

    if text_contains_any(combined, CONFIRMATION_BLOCK):
        return False
    if "ordine" in combined or "order" in combined:
        if not text_contains_any(combined, QUOTATION_CONTEXT_KEYWORDS):
            return False
    return True


def _sender_identity(from_header: str) -> tuple[str, str]:
    name, addr = parseaddr(from_header or "")
    email = (addr or from_header or "").strip()
    display = (name or "").strip()
    if not display and "@" in email:
        display = email.split("@", 1)[0]
    return display or "Cliente", email


def try_process_inbound_quotation_request(email_data: Dict[str, Any]) -> bool:
    """
    Converte email Gmail in incoming_request ed elabora (se autonomia L2+).
  Ritorna True se gestita come richiesta preventivo.
    """
    from modules.quotation_email_db import turn_exists_by_message_id
    from modules.quotation_email_thread import resolve_quotation_case

    if resolve_quotation_case(email_data):
        return False

    subject = email_data.get("subject") or ""
    body = (email_data.get("body") or "").strip()
    if not is_inbound_quotation_request(subject, body):
        return False

    message_id = (email_data.get("message_id") or "").strip()
    if message_id and turn_exists_by_message_id(message_id):
        logger.info("Email preventivo già processata: %s", message_id[:60])
        return True

    from_header = email_data.get("from") or ""
    nome, client_email = _sender_identity(from_header)
    if not client_email:
        return False

    our_addr = _our_gmail_address()
    if our_addr and client_email.lower() == our_addr:
        return False

    return bool(_create_and_elaborate_from_email(
        nome=nome,
        client_email=client_email,
        subject=subject,
        body=body,
        timestamp=email_data.get("timestamp") or "",
        message_id=message_id,
    ))


def _create_and_elaborate_from_email(
    *,
    nome: str,
    client_email: str,
    subject: str,
    body: str,
    timestamp: str,
    message_id: str,
) -> bool:
    from modules.incoming_requests_db import insert_incoming_request
    from modules.quotation_auto_pipeline import (
        elaborate_quotation_request,
        maybe_auto_elaborate_new_request,
        office_may_auto_email,
    )
    from modules.quotation_email_db import insert_turn

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
            "stato": "NUOVA",
        }
    )
    if not ins.get("ok"):
        logger.error("Insert incoming_request da email fallito: %s", ins.get("error"))
        return False

    if message_id:
        insert_turn(
            case_id=request_id,
            direction="inbound",
            body=messaggio,
            subject=subject,
            message_id=message_id,
            source="email_inbound",
        )

    logger.info(
        "Richiesta preventivo da email — case %s da %s",
        request_id,
        client_email,
    )

    if office_may_auto_email():
        result = maybe_auto_elaborate_new_request(request_id)
    else:
        result = elaborate_quotation_request(request_id, send_email=False)

    if not result.get("ok") and not result.get("skipped"):
        logger.warning("Elaborazione email inbound fallita: %s", result.get("error"))
    return True
