"""
Elaborazione richieste tecniche inbound — percorso parallelo a quotation_auto_pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def elaborate_technical_request(
    request_id: str,
    *,
    send_email: Optional[bool] = None,
    request_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from modules.gemini_module import GeminiReplyError
    from modules.incoming_requests_db import get_incoming_request, update_incoming_request
    from modules.quotation_auto_pipeline import office_may_auto_email
    from modules.technical_reply_module import generate_technical_reply_for_client

    if request_data is None:
        request_data = get_incoming_request(request_id)
    if not request_data:
        return {"ok": False, "error": "request_not_found", "request_id": request_id}

    should_send = send_email if send_email is not None else office_may_auto_email()

    gemini_data = {
        "nome": request_data.get("nome", ""),
        "email": request_data.get("email", ""),
        "messaggio": request_data.get("messaggio", ""),
    }

    try:
        reply_text = generate_technical_reply_for_client(gemini_data)
    except GeminiReplyError as exc:
        update_incoming_request(
            request_id,
            {
                "stato": "ERRORE_TECNICA",
                "errore_email": str(exc)[:300],
            },
        )
        return {
            "ok": False,
            "error": str(exc),
            "code": exc.code,
            "request_id": request_id,
            "kind": "technical",
        }

    if not reply_text:
        update_incoming_request(
            request_id,
            {"stato": "ERRORE_TECNICA", "errore_email": "empty_reply"},
        )
        return {"ok": False, "error": "empty_reply", "request_id": request_id, "kind": "technical"}

    stato_bozza = "BOZZA_TECNICA" if not should_send else "RISPOSTA_TECNICA"
    update_incoming_request(
        request_id,
        {
            "stato": stato_bozza,
            "risposta_gemini": reply_text,
            "data_elaborazione": datetime.now().isoformat(),
        },
    )

    if not should_send:
        logger.info(
            "Richiesta tecnica %s in bozza (autonomia non consente invio auto)",
            request_id,
        )
        return {
            "ok": True,
            "request_id": request_id,
            "reply": reply_text,
            "email_sent": False,
            "auto_blocked": True,
            "kind": "technical",
        }

    client_email = (request_data.get("email") or "").strip()
    if not client_email:
        update_incoming_request(request_id, {"errore_email": "Email cliente mancante"})
        return {
            "ok": True,
            "request_id": request_id,
            "reply": reply_text,
            "email_sent": False,
            "email_error": "Email cliente mancante",
            "kind": "technical",
        }

    from modules.quotation_auto_pipeline import _send_initial_quotation_email

    result = _send_initial_quotation_email(
        request_id=request_id,
        request_data=request_data,
        reply_text=reply_text,
        client_email=client_email,
        client_name=request_data.get("nome", "Cliente"),
    )
    result["kind"] = "technical"
    if result.get("ok") and result.get("email_sent"):
        update_incoming_request(request_id, {"stato": "RISPOSTA_TECNICA"})
    return result
