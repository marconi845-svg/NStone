"""
Elaborazione automatica richieste preventivo (Quotations) — gated da Agents Command Center.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_processing: set[str] = set()


def office_may_auto_email() -> bool:
    """True se policy consente invio email cliente senza approvazione GUI."""
    try:
        from core.autonomy_policy import Action, ActionContext, get_policy

        result = get_policy().allow(
            Action.SEND_CLIENT_EMAIL,
            ActionContext(agent_id="office"),
        )
        return bool(result.allowed)
    except Exception as exc:
        logger.warning("Policy autonomia non disponibile: %s", exc)
        return False


def list_pending_nuova_requests(*, limit: int = 5) -> List[Dict[str, Any]]:
    from modules.incoming_requests_db import ensure_incoming_request_table, get_database_path
    import sqlite3

    path = ensure_incoming_request_table()
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, nome, email, messaggio, stato
            FROM incoming_request
            WHERE upper(stato) IN ('NUOVA', 'NEW')
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _claim_request(request_id: str) -> bool:
    from datetime import datetime, timezone

    from modules.incoming_requests_db import ensure_incoming_request_table
    import sqlite3

    path = ensure_incoming_request_table()
    conn = sqlite3.connect(str(path), timeout=5.0)
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cur = conn.execute(
            """
            UPDATE incoming_request
            SET stato = 'IN_ELABORAZIONE', updated_at = ?
            WHERE id = ? AND upper(stato) IN ('NUOVA', 'NEW')
            """,
            (now, request_id),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def elaborate_quotation_request(
    request_id: str,
    *,
    send_email: Optional[bool] = None,
    request_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Genera risposta LLM e opzionalmente invia email threaded.

    send_email:
      - True  → invia sempre (click manuale da GUI)
      - False → solo bozza
      - None  → invia solo se office_may_auto_email()
    """
    from modules.gemini_module import GeminiReplyError, generate_reply_for_client
    from modules.incoming_requests_db import get_incoming_request, update_incoming_request

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
        reply_text = generate_reply_for_client(gemini_data)
    except GeminiReplyError as exc:
        update_incoming_request(
            request_id,
            {
                "stato": "ERRORE",
                "errore_email": str(exc)[:300],
            },
        )
        return {
            "ok": False,
            "error": str(exc),
            "code": exc.code,
            "request_id": request_id,
        }

    if not reply_text:
        update_incoming_request(request_id, {"stato": "ERRORE", "errore_email": "empty_reply"})
        return {"ok": False, "error": "empty_reply", "request_id": request_id}

    stato_bozza = "BOZZA_IN_ATTESA" if not should_send else "ELABORATA"
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
            "Preventivo %s elaborato in bozza (autonomia non consente invio auto)",
            request_id,
        )
        return {
            "ok": True,
            "request_id": request_id,
            "reply": reply_text,
            "email_sent": False,
            "auto_blocked": True,
        }

    client_email = (request_data.get("email") or "").strip()
    client_name = request_data.get("nome", "Cliente")
    if not client_email:
        update_incoming_request(
            request_id,
            {"errore_email": "Email cliente mancante"},
        )
        return {
            "ok": True,
            "request_id": request_id,
            "reply": reply_text,
            "email_sent": False,
            "email_error": "Email cliente mancante",
        }

    return _send_initial_quotation_email(
        request_id=request_id,
        request_data=request_data,
        reply_text=reply_text,
        client_email=client_email,
        client_name=client_name,
    )


def _send_initial_quotation_email(
    *,
    request_id: str,
    request_data: Dict[str, Any],
    reply_text: str,
    client_email: str,
    client_name: str,
) -> Dict[str, Any]:
    from modules.email_service import send_response_email, send_threaded_email
    from modules.incoming_requests_db import update_incoming_request
    from modules.quotation_email_thread import make_initial_subject, record_initial_outbound

    email_sent = False
    email_error = ""
    outbound_message_id = None

    if make_initial_subject:
        subject = make_initial_subject(request_id, client_name)
    else:
        subject = f"Risposta alla tua richiesta — NStone ({client_name})"

    try:
        if send_threaded_email is not None:
            send_result = send_threaded_email(client_email, subject, reply_text)
            email_sent = bool(send_result.get("sent"))
            outbound_message_id = send_result.get("message_id")
            if not email_sent:
                email_error = send_result.get("error") or "Invio SMTP fallito"
        elif send_response_email is not None:
            email_sent = bool(send_response_email(client_email, subject, reply_text))
            if not email_sent:
                email_error = "Invio SMTP fallito"
        else:
            email_error = "Modulo email non disponibile"
    except Exception as exc:
        email_error = str(exc)

    if email_sent and record_initial_outbound and outbound_message_id:
        record_initial_outbound(
            case_id=request_id,
            client_message=request_data.get("messaggio", ""),
            reply_body=reply_text,
            subject=subject,
            message_id=outbound_message_id,
        )

    update_fields: Dict[str, Any] = {
        "email_inviata": email_sent,
        "data_invio_email": datetime.now().isoformat() if email_sent else None,
        "errore_email": email_error or None,
    }
    if email_sent:
        update_fields["stato"] = "OFFERTA_INVIATA"
    update_incoming_request(request_id, update_fields)

    return {
        "ok": True,
        "request_id": request_id,
        "reply": reply_text,
        "email_sent": email_sent,
        "email_error": email_error or None,
        "message_id": outbound_message_id,
    }


def maybe_auto_elaborate_new_request(request_id: str) -> Dict[str, Any]:
    """Elabora una richiesta appena arrivata se autonomia L≥2 + office_auto_email."""
    if not office_may_auto_email():
        return {"ok": False, "skipped": True, "reason": "autonomy"}

    with _lock:
        if request_id in _processing:
            return {"ok": False, "skipped": True, "reason": "in_progress"}
        if not _claim_request(request_id):
            return {"ok": False, "skipped": True, "reason": "not_nuova"}
        _processing.add(request_id)

    try:
        logger.info("Auto-elaborazione preventivo %s (autonomia alta)", request_id)
        return elaborate_quotation_request(request_id, send_email=True)
    finally:
        with _lock:
            _processing.discard(request_id)


def process_pending_nuova_requests(*, limit: int = 3) -> Dict[str, Any]:
    """Processa richieste NUOVA in coda (desktop poll / post-IMAP)."""
    if not office_may_auto_email():
        return {"processed": 0, "skipped": "autonomy"}

    results = []
    for row in list_pending_nuova_requests(limit=limit):
        rid = row.get("id")
        if not rid:
            continue
        results.append(maybe_auto_elaborate_new_request(rid))
    done = sum(1 for r in results if r.get("ok") and not r.get("skipped"))
    return {"processed": done, "results": results}
