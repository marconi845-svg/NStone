"""
Pipeline conferma cliente: intent (Gemini) → stock catalogo → email conferma NStone.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from email.utils import parseaddr
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _order_for_gemini(order: Dict[str, Any]) -> Dict[str, Any]:
    oid = order.get("order_id") or order.get("id") or "UNKNOWN"
    return {
        "id": oid,
        "from": order.get("client_email") or order.get("from") or "",
        "subject": order.get("email_subject") or order.get("subject") or order.get("product") or "",
        "body": order.get("email_body") or order.get("body") or "",
        "materiale": order.get("materiale") or "",
        "quantita": order.get("quantita"),
    }


def _extract_qty(order: Dict[str, Any]) -> Optional[float]:
    q = order.get("quantita")
    if q is None:
        return None
    try:
        return float(q)
    except (TypeError, ValueError):
        return None


def _fallback_intake_analysis(
    order: Dict[str, Any],
    stock_report: Dict[str, Any],
    *,
    client_email: str = "",
) -> Dict[str, Any]:
    """Presa in carico ordine ex novo (rule-based, no LLM)."""
    order_id = order.get("order_id") or order.get("id") or "UNKNOWN"
    client = (order.get("client") or client_email.split("@")[0] or "Cliente").strip()
    materiale = (order.get("materiale") or order.get("product") or "materiale richiesto").strip()
    qty = _extract_qty(order)
    qty_line = f"{qty} mq" if qty else "quantità in revisione"
    availability = stock_report.get("availability") or "unknown"
    if availability == "available":
        stock_line = "Il materiale risulta disponibile a magazzino."
    elif availability == "partial":
        stock_line = "Disponibilità parziale: il reparto commerciale vi contatterà."
    elif availability == "unavailable":
        stock_line = "Disponibilità da verificare: vi aggiorneremo a breve."
    else:
        stock_line = "Verificheremo la disponibilità e vi aggiorneremo a breve."

    text = (
        f"Gentile {client},\n\n"
        f"abbiamo ricevuto il Suo ordine #{order_id} "
        f"per {materiale} ({qty_line}).\n"
        f"{stock_line}\n\n"
        "L'ordine è stato preso in carico dal reparto ordini NStone.\n\n"
        "Cordiali saluti,\nTeam NStone"
    )
    return {
        "status": "confirmed",
        "availability": availability,
        "confidence": 0.75,
        "notes": "Presa ordine rule-based (poll senza LLM)",
        "confirmation_email_text": text,
    }


def _fallback_confirmation_analysis(
    order: Dict[str, Any],
    stock_report: Dict[str, Any],
    *,
    client_email: str = "",
) -> Dict[str, Any]:
    """Conferma rule-based (no LLM) — stesso approccio pipeline NS-Q."""
    order_id = order.get("order_id") or order.get("id") or "UNKNOWN"
    client = (order.get("client") or client_email.split("@")[0] or "Cliente").strip()
    materiale = (order.get("materiale") or order.get("product") or "materiale richiesto").strip()
    qty = _extract_qty(order)
    qty_line = f"{qty} mq" if qty else "quantità in revisione"
    availability = stock_report.get("availability") or "unknown"
    if availability == "available":
        stock_line = "Il materiale risulta disponibile a magazzino."
    elif availability == "partial":
        stock_line = "Disponibilità parziale: vi contatteremo per i dettagli."
    elif availability == "unavailable":
        stock_line = "Al momento la disponibilità è limitata; il reparto commerciale vi ricontatterà."
    else:
        stock_line = "Verificheremo la disponibilità e vi aggiorneremo a breve."

    text = (
        f"Gentile {client},\n\n"
        f"abbiamo ricevuto la conferma del Suo ordine #{order_id} "
        f"per {materiale} ({qty_line}).\n"
        f"{stock_line}\n\n"
        "Riepilogo preso in carico dal reparto ordini NStone.\n\n"
        "Cordiali saluti,\nTeam NStone"
    )
    return {
        "status": "confirmed",
        "availability": availability,
        "confidence": 0.75,
        "notes": "Conferma rule-based (poll rapido, senza LLM)",
        "confirmation_email_text": text,
    }


def _order_already_finalized(order: Dict[str, Any]) -> bool:
    status = str(order.get("status") or "").upper()
    return status in {
        "CONFIRMED",
        "CONFIRMED_PARTIAL",
        "REJECTED_STOCK",
        "PENDING_APPROVAL",
        "INVIATO",
        "IN PRODUZIONE",
        "COMPLETATO",
    }


def process_client_confirmation_email(
    email_data: Dict[str, Any],
    *,
    force_send: bool = False,
    use_llm: bool = True,
) -> bool:
    """
    Email classificata CONFERMA: abbina ordine, verifica stock, risponde al cliente.

    Autonomia:
      - L2 + office_auto_email: invio automatico (+ PDF).
      - L1 (o auto-email off): bozza PENDING_APPROVAL, nessun invio.
      - force_send=True: invio manuale da operatore (pulsante UI), ignora gate L1.
    """
    from modules.orders_database import (
        find_order_for_confirmation,
        save_email_log,
        update_order_confirmation_result,
    )
    from modules.order_stock_check import check_material_availability

    try:
        from modules.orders_pipeline_trace import trace_step
    except ImportError:
        def trace_step(*a, **k):  # type: ignore
            pass

    sender = email_data.get("from", "")
    subject = email_data.get("subject", "")
    body = email_data.get("body", "")
    timestamp = email_data.get("timestamp", datetime.now().isoformat())

    _, client_email = parseaddr(sender)
    client_email = client_email or sender

    order = find_order_for_confirmation(client_email, subject, body)
    if not order:
        logger.warning("Conferma senza ordine abbinato: %s — %s", client_email, subject[:80])
        trace_step("DB", "nessun ordine abbinato")
        save_email_log(
            sender, subject, body, timestamp,
            "CONFERMA", 0.5, order_id=None,
            message_id=(email_data.get("message_id") or "").strip() or None,
        )
        return False

    order_id = order.get("order_id") or order.get("id")
    trace_step("DB", f"ordine {order_id} status={order.get('status')}")
    if _order_already_finalized(order) and not force_send:
        logger.info("Ordine %s già finalizzato (%s) — skip conferma", order_id, order.get("status"))
        trace_step("DB", f"ordine già finalizzato ({order.get('status')})")
        return True

    materiale = (order.get("materiale") or order.get("product") or "").strip()
    if not materiale:
        combined = f"{order.get('email_subject', '')} {order.get('email_body', '')}"
        for word in ("marmo", "granito", "quarzo", "lastre", "calacatta", "carrara"):
            if word in combined.lower():
                materiale = word
                break

    stock_report = check_material_availability(materiale, _extract_qty(order))
    trace_step("STOCK", str(stock_report.get("availability", "?")))

    analysis: Optional[Dict[str, Any]] = None
    if use_llm or force_send:
        try:
            from modules.gemini_module import analyze_confirmation_with_stock
        except ImportError:
            analyze_confirmation_with_stock = None

        if analyze_confirmation_with_stock:
            logger.info("Conferma ordine %s — analisi LLM…", order_id)
            trace_step("LLM", "analyze_confirmation_with_stock…")
            analysis = analyze_confirmation_with_stock(
                body, _order_for_gemini(order), stock_report
            )
            trace_step("LLM", "ok" if analysis else "fallito/timeout")

    if not analysis:
        logger.info(
            "Conferma ordine %s — rule-based (%s)",
            order_id,
            "LLM disattivato su poll" if not use_llm and not force_send else "LLM non disponibile",
        )
        trace_step("LLM", "rule-based (no modello)")
        analysis = _fallback_confirmation_analysis(
            order, stock_report, client_email=client_email
        )

    save_email_log(
        sender, subject, body, timestamp,
        "CONFERMA", float(analysis.get("confidence", 0.7)),
        order_id=order_id,
        message_id=(email_data.get("message_id") or "").strip() or None,
    )

    return dispatch_order_acknowledgment(
        order,
        analysis,
        stock_report,
        client_email=client_email,
        materiale=materiale,
        force_send=force_send,
        draft_source="classic_confirmation_draft",
        draft_note_suffix="Bozza conferma (L1 — invio assistito)",
        log_label="Conferma NStone",
    )


def dispatch_order_acknowledgment(
    order: Dict[str, Any],
    analysis: Dict[str, Any],
    stock_report: Dict[str, Any],
    *,
    client_email: str,
    materiale: str = "",
    force_send: bool = False,
    draft_source: str = "classic_confirmation_draft",
    draft_note_suffix: str = "Bozza (L1 — invio assistito)",
    log_label: str = "Ack ordine",
) -> bool:
    """Stock → PDF → email al cliente, con gate autonomia L1/L2."""
    from modules.orders_database import update_order_confirmation_result

    try:
        from modules.orders_pipeline_trace import trace_step
    except ImportError:
        def trace_step(*a, **k):  # type: ignore
            pass

    order_id = order.get("order_id") or order.get("id") or "UNKNOWN"
    status = analysis.get("status", "pending")
    availability = analysis.get("availability") or stock_report.get("availability")
    confirmation_text = (analysis.get("confirmation_email_text") or "").strip()

    if status != "confirmed":
        update_order_confirmation_result(
            order_id,
            status=status.upper() if status else "PENDING",
            notes=analysis.get("notes", ""),
            availability=availability,
            stock_report=stock_report,
        )
        logger.info("%s non inviata (status=%s) ordine %s", log_label, status, order_id)
        return False

    if not confirmation_text:
        logger.warning("Testo email mancante per ordine %s", order_id)
        return False

    if not materiale:
        materiale = (order.get("materiale") or order.get("product") or "").strip()
        if not materiale:
            combined = f"{order.get('email_subject', '')} {order.get('email_body', '')}"
            for word in ("marmo", "granito", "quarzo", "lastre", "calacatta", "carrara"):
                if word in combined.lower():
                    materiale = word
                    break

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
            build_pdf_data_from_order_record,
            generate_order_confirmation_pdf,
            pdf_attachment_for_email,
        )

        pdf_data = build_pdf_data_from_order_record(
            order,
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
        logger.warning("PDF ordine non generato (%s): %s", order_id, exc)

    from modules.quotation_auto_pipeline import office_may_auto_email

    if not force_send and not office_may_auto_email():
        draft_info: Dict[str, Any] = {
            "sent": False,
            "draft": True,
            "to": client_email,
            "body": mail_body,
            "pdf_path": str(pdf_path) if pdf_path else None,
            "timestamp": datetime.now().isoformat(),
            "source": draft_source,
        }
        update_order_confirmation_result(
            order_id,
            status="PENDING_APPROVAL",
            notes=(analysis.get("notes") or "") + f" | {draft_note_suffix}",
            availability=availability,
            stock_report=stock_report,
            confirmation_email=draft_info,
        )
        trace_step("AUTONOMY", "L1 bozza PENDING_APPROVAL")
        logger.info("%s %s in bozza (autonomia L1)", log_label, order_id)
        return True

    from modules.email_service import send_order_confirmation_email

    trace_step("SMTP", f"invio → {client_email}")

    to_email = client_email
    gemini_order = _order_for_gemini(order)
    gemini_order["notes"] = analysis.get("notes", "")
    gemini_order["availability"] = availability

    email_info = send_order_confirmation_email(
        to_email=to_email,
        order_data=gemini_order,
        confirmation_text=mail_body,
        attachments=mail_attachments,
    )
    if email_info and pdf_path:
        email_info["pdf_path"] = str(pdf_path)
    if not email_info or not email_info.get("sent"):
        logger.error("Invio email fallito per %s", order_id)
        return False

    stock_deduction: Dict[str, Any] = {"applied": False}
    if db_status in ("CONFIRMED", "CONFIRMED_PARTIAL"):
        from modules.order_stock_check import apply_stock_deduction_for_order

        stock_deduction = apply_stock_deduction_for_order(
            order_id=order_id,
            materiale=materiale,
            quantita_mq=_extract_qty(order),
            availability=availability,
            stock_report=stock_report,
        )
        if stock_deduction.get("applied"):
            logger.info(
                "Stock scalato per %s: %s mq",
                order_id,
                stock_deduction.get("total_deducted_mq"),
            )
        else:
            logger.warning(
                "Scalo stock non applicato per %s: %s",
                order_id,
                stock_deduction.get("reason"),
            )

    update_order_confirmation_result(
        order_id,
        status=db_status,
        notes=analysis.get("notes", ""),
        availability=availability,
        stock_report=stock_report,
        confirmation_email=email_info,
        stock_deduction=stock_deduction,
    )

    try:
        from modules.orders_imap_service import save_order_to_json, update_last_order_json

        json_data = {
            "id": order_id,
            "from": to_email,
            "subject": gemini_order.get("subject"),
            "body": gemini_order.get("body"),
            "status": db_status.lower(),
            "sent_confirmation_email": email_info,
            "confirmation_timestamp": datetime.now().isoformat(),
        }
        save_order_to_json(json_data)
        update_last_order_json(json_data)
    except Exception:
        pass

    logger.info("%s inviata per %s (availability=%s)", log_label, order_id, availability)
    return True
