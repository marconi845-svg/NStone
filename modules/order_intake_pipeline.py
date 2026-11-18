"""
Pipeline ordine ex novo: dopo salvataggio ORDINE → LLM (opz.) → stock → PDF → email cliente.
"""
from __future__ import annotations

import logging
from email.utils import parseaddr
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def process_new_order_intake(
    order_id: str,
    email_data: Dict[str, Any],
    *,
    use_llm: bool = False,
    force_send: bool = False,
) -> bool:
    """
    Presa in carico automatica ordine appena creato (poll IMAP o UI).

    - use_llm=True (ultima UNSEEN): estrazione campi + testo email via modello
    - use_llm=False: rule-based veloce
    - L2 + office_auto_email: invio SMTP + PDF
    - L1: bozza PENDING_APPROVAL
    """
    from modules.order_confirmation_pipeline import (
        _fallback_intake_analysis,
        _extract_qty,
        _order_already_finalized,
        _order_for_gemini,
        dispatch_order_acknowledgment,
    )
    from modules.order_stock_check import check_material_availability
    from modules.orders_database import get_order_by_order_id, update_order_ai_fields

    try:
        from modules.orders_pipeline_trace import trace_step
    except ImportError:
        def trace_step(*a, **k):  # type: ignore
            pass

    order = get_order_by_order_id(order_id)
    if not order:
        logger.warning("Intake: ordine %s non trovato", order_id)
        trace_step("INTAKE", "ordine non in DB")
        return False

    if _order_already_finalized(order) and not force_send:
        trace_step("INTAKE", f"già finalizzato ({order.get('status')})")
        return True

    sender = email_data.get("from", "")
    body = email_data.get("body", "") or order.get("email_body") or ""
    _, client_email = parseaddr(sender)
    client_email = client_email or order.get("client_email") or sender

    analysis: Optional[Dict[str, Any]] = None

    if use_llm or force_send:
        try:
            from modules.order_ai_analysis import analyze_order_email_with_ai

            trace_step("LLM", "estrazione campi ordine…")
            extracted = analyze_order_email_with_ai(order)
            update_order_ai_fields(order_id, extracted)
            order = get_order_by_order_id(order_id) or order
            if extracted.get("materiale"):
                order["materiale"] = extracted["materiale"]
            if extracted.get("quantita_mq") is not None:
                order["quantita"] = extracted["quantita_mq"]
            if extracted.get("machine"):
                order["machine"] = extracted["machine"]
            trace_step("LLM", "campi ordine ok")
        except Exception as exc:
            logger.warning("Intake LLM estrazione fallita %s: %s", order_id, exc)
            trace_step("LLM", f"estrazione fallita: {str(exc)[:60]}")

    materiale = (order.get("materiale") or order.get("product") or "").strip()
    if not materiale:
        combined = f"{order.get('email_subject', '')} {body}"
        for word in ("marmo", "granito", "quarzo", "lastre", "calacatta", "carrara", "botticino"):
            if word in combined.lower():
                materiale = word
                break

    stock_report = check_material_availability(materiale, _extract_qty(order))
    trace_step("STOCK", str(stock_report.get("availability", "?")))

    if use_llm or force_send:
        try:
            from modules.gemini_module import analyze_confirmation_with_stock

            trace_step("LLM", "testo presa ordine…")
            analysis = analyze_confirmation_with_stock(
                body, _order_for_gemini(order), stock_report
            )
            if analysis and analysis.get("status") == "pending":
                analysis["status"] = "confirmed"
            trace_step("LLM", "ok" if analysis else "testo fallito")
        except Exception as exc:
            logger.warning("Intake LLM testo fallito %s: %s", order_id, exc)
            trace_step("LLM", f"testo fallito: {str(exc)[:60]}")

    if not analysis:
        trace_step("LLM", "rule-based presa ordine")
        analysis = _fallback_intake_analysis(
            order, stock_report, client_email=client_email
        )

    trace_step("INTAKE", "→ PDF/email")
    return dispatch_order_acknowledgment(
        order,
        analysis,
        stock_report,
        client_email=client_email,
        materiale=materiale,
        force_send=force_send,
        draft_source="order_intake_draft",
        draft_note_suffix="Bozza presa ordine (L1 — invio assistito)",
        log_label="Presa ordine NStone",
    )
