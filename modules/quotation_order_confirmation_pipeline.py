"""
Conferma ordine su thread preventivo NS-Q: crea ordine, verifica stock, risponde threaded.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from modules.pipeline_keywords import (
    CONFIRMATION_PHRASES,
    MODIFICATION_PHRASES,
    NEGATION_PHRASES,
    confirmation_rule_fallback_match,
)

MQ_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:mq|m\s*²|m2|sqm|sq\s*m|square\s*meters?|metri\s*quadri?)",
    re.IGNORECASE,
)

MACHINE_KEYWORDS = {
    "multifilo": "multifilo",
    "lucidatrice": "lucidatrice",
    "cnc": "cnc",
    "taglio": "multifilo",
    "lucidatura": "lucidatrice",
    "wire saw": "multifilo",
    "polisher": "lucidatrice",
    "polishing": "lucidatrice",
    "cutting": "multifilo",
}


def _normalize_text(*parts: str) -> str:
    return " ".join((p or "").strip() for p in parts if p).lower()


def has_outbound_offer(case_id: str) -> bool:
    from modules.quotation_email_db import list_turns_for_case

    return any(
        t.get("direction") == "outbound" and (t.get("body") or "").strip()
        for t in list_turns_for_case(case_id)
    )


def case_is_already_confirmed(case: Dict[str, Any]) -> bool:
    stato = str(case.get("stato") or "").upper()
    if stato == "ORDINE_CONFERMATO":
        return True
    try:
        from modules.orders_database import find_order_by_quotation_case_id

        order = find_order_by_quotation_case_id(str(case.get("id") or ""))
        if order:
            status = str(order.get("status") or "").upper()
            if status in (
                "CONFIRMED",
                "CONFIRMED_PARTIAL",
                "REJECTED_STOCK",
                "INVIATO",
                "IN PRODUZIONE",
            ):
                return True
    except Exception:
        pass
    return False


def is_order_confirmation_intent(subject: str, body: str) -> Tuple[bool, float]:
    """Rileva intent conferma ordine (regole veloci)."""
    combined = _normalize_text(subject, body)
    if not combined.strip():
        return False, 0.0

    if any(neg in combined for neg in NEGATION_PHRASES):
        return False, 0.0

    score = 0.0
    for phrase in CONFIRMATION_PHRASES:
        if phrase in combined:
            score = max(score, 0.65 if len(phrase) <= 8 else 0.85)

    if score >= 0.65:
        return True, min(0.95, score)

    if confirmation_rule_fallback_match(combined):
        return True, 0.72

    return False, 0.0


def client_requests_modification(body: str) -> bool:
    text = _normalize_text(body)
    return any(m in text for m in MODIFICATION_PHRASES) and bool(MQ_RE.search(text))


def extract_mq_from_text(text: str) -> Optional[float]:
    match = MQ_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _thread_combined_text(history: List[Dict[str, str]], body: str) -> str:
    parts = [body or ""]
    for turn in history:
        parts.append(turn.get("content") or "")
    return "\n".join(parts)


def _detect_machine(text: str) -> str:
    low = text.lower()
    for kw, machine in MACHINE_KEYWORDS.items():
        if kw in low:
            return machine
    return "non_specificata"


def extract_order_fields_from_thread(
    case: Dict[str, Any],
    email_data: Dict[str, Any],
    history: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Estrae materiale, quantità e macchina da thread + catalogo (fase 3)."""
    body = (email_data.get("body") or "").strip()
    combined = _thread_combined_text(history, body)

    materiale = ""
    quantita: Optional[float] = None

    try:
        from modules.catalog_db import find_catalog_matches_for_message

        matches = find_catalog_matches_for_message(combined)
        if matches:
            top = matches[0]
            materiale = (top.get("Name") or top.get("name") or "").strip()
    except Exception as exc:
        logger.debug("Catalog match fallito: %s", exc)

    if not materiale:
        for word in (
            "calacatta", "carrara", "travertino", "statuario", "bardiglio",
            "marmo", "granito", "quarzo", "lastre",
        ):
            if word in combined.lower():
                materiale = word
                break

    if client_requests_modification(body):
        quantita = extract_mq_from_text(body)
    if quantita is None:
        for turn in reversed(history):
            if turn.get("role") == "user":
                quantita = extract_mq_from_text(turn.get("content") or "")
                if quantita is not None:
                    break
    if quantita is None:
        quantita = extract_mq_from_text(combined)

    machine = _detect_machine(combined)

    from modules.quotation_email_thread import case_token, make_initial_subject

    case_id = str(case.get("id") or "")
    nome = str(case.get("nome") or "Cliente")
    subject = make_initial_subject(case_id, nome)

    return {
        "materiale": materiale or "materiale da definire",
        "quantita": quantita,
        "machine": machine,
        "product": f"Ordine da preventivo {case_token(case_id)}",
        "email_subject": subject,
        "email_body": combined[:8000],
    }


def make_quotation_order_id(case_id: str) -> str:
    from modules.quotation_email_thread import extract_token8

    token = extract_token8(case_id) or case_id.replace("-", "")[:8].lower()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"Q-{token}-{ts}"


def _fallback_confirmation_text(
    case: Dict[str, Any],
    order_fields: Dict[str, Any],
    stock_report: Dict[str, Any],
) -> str:
    nome = str(case.get("nome") or "Cliente").strip()
    materiale = order_fields.get("materiale") or "materiale richiesto"
    qty = order_fields.get("quantita")
    qty_line = f"{qty} mq" if qty else "quantità da confermare in sede"
    availability = stock_report.get("availability") or "unknown"
    if availability == "available":
        stock_line = "Il materiale risulta disponibile a magazzino."
    elif availability == "partial":
        stock_line = "Disponibilità parziale: la contatteremo per i dettagli."
    elif availability == "unavailable":
        stock_line = "Al momento la disponibilità è limitata; il reparto commerciale la ricontatterà."
    else:
        stock_line = "Verificheremo la disponibilità e la aggiorneremo a breve."

    return (
        f"Gentile {nome},\n\n"
        f"abbiamo ricevuto la conferma del Suo ordine per {materiale} ({qty_line}).\n"
        f"{stock_line}\n\n"
        "Riepilogo preso in carico dal reparto ordini NStone.\n\n"
        "Cordiali saluti,\nTeam NStone"
    )


def try_process_quotation_order_confirmation(
    email_data: Dict[str, Any],
    case: Dict[str, Any],
    *,
    use_llm: bool = True,
) -> bool:
    """True se gestita come conferma ordine (anche bozza o già confermata)."""
    case_id = str(case.get("id") or "")
    if not case_id:
        return False

    if case_is_already_confirmed(case):
        logger.info("Case %s già confermato — skip", case_id[:8])
        return True

    if not has_outbound_offer(case_id):
        return False

    subject = email_data.get("subject") or ""
    body = (email_data.get("body") or "").strip()
    if not body:
        return False

    is_confirm, confidence = is_order_confirmation_intent(subject, body)
    if not is_confirm:
        return False

    logger.info(
        "Conferma ordine su thread NS-Q — case %s (confidence %.2f)",
        case_id[:8],
        confidence,
    )
    return process_quotation_order_confirmation(email_data, case, use_llm=use_llm)


def process_quotation_order_confirmation(
    email_data: Dict[str, Any],
    case: Dict[str, Any],
    *,
    use_llm: bool = True,
) -> bool:
    from modules.email_service import send_threaded_email
    from modules.incoming_requests_db import update_incoming_request
    from modules.order_stock_check import (
        apply_stock_deduction_for_order,
        check_material_availability,
    )
    from modules.orders_database import (
        find_order_by_quotation_case_id,
        save_email_log,
        save_order,
        update_order_confirmation_result,
    )
    from modules.orders_imap_service import save_order_to_json, update_last_order_json
    from modules.quotation_auto_pipeline import office_may_auto_email
    from modules.quotation_email_thread import (
        build_references_header,
        conversation_for_llm,
        make_reply_subject,
        record_inbound_reply,
        record_outbound_reply,
    )

    case_id = str(case.get("id") or "")
    client_email = (case.get("email") or "").strip()
    if not client_email:
        return False

    body_in = (email_data.get("body") or "").strip()
    record_inbound_reply(email_data, case_id)
    history = conversation_for_llm(case_id)
    order_fields = extract_order_fields_from_thread(case, email_data, history)

    existing = find_order_by_quotation_case_id(case_id)
    if existing:
        order_id = str(existing.get("order_id") or "")
    else:
        order_id = make_quotation_order_id(case_id)
        _, addr = parseaddr(email_data.get("from") or "")
        sender = addr or client_email
        timestamp = email_data.get("timestamp", datetime.now().isoformat())
        order_data = {
            "order_id": order_id,
            "from": sender,
            "client": client_email.split("@")[0] if "@" in client_email else client_email[:80],
            "client_email": client_email,
            "subject": order_fields["email_subject"],
            "body": order_fields["email_body"],
            "product": order_fields["product"],
            "materiale": order_fields["materiale"],
            "quantita": order_fields.get("quantita"),
            "machine": order_fields.get("machine") or "non_specificata",
            "timestamp": timestamp,
            "created_at": timestamp,
            "status": "NEW",
            "quotation_case_id": case_id,
        }
        save_order(order_data)
        json_order = {
            "id": order_id,
            "from": client_email,
            "subject": order_fields["email_subject"],
            "body": order_fields["email_body"],
            "timestamp": timestamp,
            "status": "NEW",
            "quotation_case_id": case_id,
            "sent_confirmation_email": None,
        }
        save_order_to_json(json_order)
        update_last_order_json(json_order)

    materiale = order_fields.get("materiale") or ""
    quantita = order_fields.get("quantita")
    stock_report = check_material_availability(materiale, quantita)

    gemini_order = {
        "id": order_id,
        "from": client_email,
        "subject": order_fields["email_subject"],
        "body": order_fields["email_body"],
        "materiale": materiale,
        "quantita": quantita,
        "machine": order_fields.get("machine"),
        "quotation_case_id": case_id,
    }

    analysis: Optional[Dict[str, Any]] = None
    if use_llm:
        try:
            from modules.gemini_module import analyze_confirmation_with_stock

            analysis = analyze_confirmation_with_stock(body_in, gemini_order, stock_report)
        except Exception as exc:
            logger.debug("Gemini conferma stock non disponibile: %s", exc)

    if not analysis:
        analysis = {
            "status": "confirmed",
            "availability": stock_report.get("availability", "unknown"),
            "confidence": 0.6,
            "notes": "Conferma da thread preventivo (analisi rule-based)",
            "confirmation_email_text": _fallback_confirmation_text(
                case, order_fields, stock_report
            ),
        }

    sender = email_data.get("from", "")
    subject = email_data.get("subject", "")
    timestamp = email_data.get("timestamp", datetime.now().isoformat())
    save_email_log(
        sender,
        subject,
        body_in,
        timestamp,
        "CONFERMA_PREVENTIVO",
        float(analysis.get("confidence", 0.7)),
        order_id=order_id,
    )

    status = analysis.get("status", "pending")
    if status != "confirmed":
        update_incoming_request(
            case_id,
            {
                "stato": "IN_CONVERSAZIONE",
                "errore_email": None,
            },
        )
        update_order_confirmation_result(
            order_id,
            status=(status or "PENDING").upper(),
            notes=analysis.get("notes", ""),
            availability=analysis.get("availability"),
            stock_report=stock_report,
        )
        return True

    confirmation_text = (analysis.get("confirmation_email_text") or "").strip()
    if not confirmation_text:
        confirmation_text = _fallback_confirmation_text(case, order_fields, stock_report)

    if not office_may_auto_email():
        update_incoming_request(
            case_id,
            {
                "stato": "BOZZA_IN_ATTESA",
                "risposta_gemini": confirmation_text,
                "linked_order_id": order_id,
                "errore_email": None,
            },
        )
        update_order_confirmation_result(
            order_id,
            status="PENDING_APPROVAL",
            notes=analysis.get("notes", "") + " | Bozza conferma ordine da thread",
            availability=analysis.get("availability"),
            stock_report=stock_report,
        )
        logger.info("Conferma ordine %s in bozza (autonomia)", order_id)
        return True

    in_reply_to = email_data.get("message_id")
    references = build_references_header(case_id, in_reply_to=in_reply_to)
    reply_subject = make_reply_subject(case_id, case.get("nome", "Cliente"))

    availability = analysis.get("availability") or stock_report.get("availability")
    db_status = "CONFIRMED"
    if availability == "unavailable":
        db_status = "REJECTED_STOCK"
    elif availability == "partial":
        db_status = "CONFIRMED_PARTIAL"

    pdf_path = None
    mail_attachments = None
    mail_body = confirmation_text
    try:
        from modules.order_confirmation_pdf import (
            build_pdf_data_from_quotation_confirmation,
            generate_order_confirmation_pdf,
            pdf_attachment_for_email,
        )

        pdf_data = build_pdf_data_from_quotation_confirmation(
            order_id=order_id,
            case=case,
            order_fields=order_fields,
            analysis=analysis,
            stock_report=stock_report,
            db_status=db_status,
        )
        pdf_path = generate_order_confirmation_pdf(pdf_data)
        if pdf_path:
            mail_attachments = [pdf_attachment_for_email(pdf_path)]
            mail_body = (
                f"{confirmation_text.strip()}\n\n"
                "In allegato la conferma d'ordine formale (PDF)."
            )
    except Exception as exc:
        logger.warning("PDF conferma ordine non generato (%s): %s", order_id, exc)

    send_result = send_threaded_email(
        client_email,
        reply_subject,
        mail_body,
        in_reply_to=in_reply_to,
        references=references or None,
        attachments=mail_attachments,
    )

    stock_deduction: Dict[str, Any] = {"applied": False}
    if db_status in ("CONFIRMED", "CONFIRMED_PARTIAL"):
        stock_deduction = apply_stock_deduction_for_order(
            order_id=order_id,
            materiale=materiale,
            quantita_mq=quantita,
            availability=availability,
            stock_report=stock_report,
        )

    email_info = {
        "sent": bool(send_result.get("sent")),
        "to": client_email,
        "subject": reply_subject,
        "body": mail_body,
        "message_id": send_result.get("message_id"),
        "timestamp": datetime.now().isoformat(),
        "error": send_result.get("error"),
        "source": "quotation_thread_confirmation",
        "pdf_path": str(pdf_path) if pdf_path else None,
        "attachments": send_result.get("attachments") or [],
    }

    update_order_confirmation_result(
        order_id,
        status=db_status,
        notes=analysis.get("notes", ""),
        availability=availability,
        stock_report=stock_report,
        confirmation_email=email_info,
        stock_deduction=stock_deduction,
    )

    if send_result.get("sent"):
        record_outbound_reply(
            case_id=case_id,
            body=mail_body,
            subject=reply_subject,
            message_id=send_result.get("message_id") or "",
            in_reply_to=in_reply_to,
            email_references=references,
        )
        update_incoming_request(
            case_id,
            {
                "stato": "ORDINE_CONFERMATO",
                "risposta_gemini": confirmation_text,
                "linked_order_id": order_id,
                "email_inviata": True,
                "data_invio_email": datetime.now().isoformat(),
                "errore_email": None,
            },
        )
        logger.info("Ordine confermato su thread NS-Q — %s / case %s", order_id, case_id[:8])
    else:
        err = send_result.get("error") or "Invio SMTP fallito"
        update_incoming_request(
            case_id,
            {
                "stato": "ORDINE_CONFERMATO",
                "linked_order_id": order_id,
                "risposta_gemini": confirmation_text,
                "errore_email": err[:300],
            },
        )
        logger.error("Conferma ordine invio fallito %s: %s", order_id, err)

    try:
        json_order = {
            "id": order_id,
            "from": client_email,
            "subject": order_fields["email_subject"],
            "body": order_fields["email_body"],
            "status": db_status.lower(),
            "quotation_case_id": case_id,
            "sent_confirmation_email": email_info,
            "confirmation_timestamp": datetime.now().isoformat(),
        }
        save_order_to_json(json_order)
        update_last_order_json(json_order)
    except Exception:
        pass

    return True
