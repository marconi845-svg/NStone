"""
Quotation email threading: subject tokens, case resolution, turn recording.
"""
from __future__ import annotations

import re
import uuid
from email.utils import parseaddr
from typing import Any, Dict, List, Optional

from modules.incoming_requests_db import get_incoming_request, update_incoming_request
from modules.quotation_email_db import (
    find_case_id_by_message_id,
    find_case_id_by_token_prefix,
    find_open_case_for_email,
    get_all_outbound_message_ids,
    insert_turn,
    list_turns_for_case,
)

CASE_TOKEN_RE = re.compile(r"\[NS-Q-([a-f0-9]{8})\]", re.IGNORECASE)
RE_PREFIX_RE = re.compile(r"^(re|fwd|fw)\s*:\s*", re.IGNORECASE)


def case_token(case_id: str) -> str:
    hex8 = case_id.replace("-", "")[:8].lower()
    return f"[NS-Q-{hex8}]"


def make_initial_subject(case_id: str, client_name: str, *, language: Optional[str] = None) -> str:
    name = (client_name or "Cliente").strip()
    if language is None:
        try:
            from llm.llm_contexts import resolve_llm_language
            from core.machine_plc_config import load_config

            language = resolve_llm_language(load_config())
        except Exception:
            language = "it"
    lang = str(language or "it").lower()
    if lang.startswith("en") or "english" in lang:
        return f"NStone quotation — {name} {case_token(case_id)}"
    return f"Risposta alla tua richiesta — NStone ({name}) {case_token(case_id)}"


def make_reply_subject(case_id: str, client_name: str) -> str:
    return f"Re: {make_initial_subject(case_id, client_name)}"


def extract_token8(subject: str) -> Optional[str]:
    match = CASE_TOKEN_RE.search(subject or "")
    return match.group(1).lower() if match else None


def _normalize_msg_id(raw: str) -> str:
    return (raw or "").strip().strip("<>").lower()


def _parse_reference_ids(references: str) -> List[str]:
    if not references:
        return []
    return [_normalize_msg_id(part) for part in references.split() if part.strip()]


def resolve_quotation_case(email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Match inbound email to an incoming_request case.
    Priority: References/In-Reply-To → NS-Q token → sender + open case.
    """
    subject = email_data.get("subject") or ""
    in_reply_to = email_data.get("in_reply_to") or ""
    references = email_data.get("references") or ""

    candidate_ids: List[str] = []
    for raw in [in_reply_to, *_parse_reference_ids(references)]:
        cid = find_case_id_by_message_id(raw)
        if cid:
            candidate_ids.append(cid)

    if candidate_ids:
        case = get_incoming_request(candidate_ids[0])
        if case:
            return case

    token8 = extract_token8(subject)
    if token8:
        cid = find_case_id_by_token_prefix(token8)
        if cid:
            case = get_incoming_request(cid)
            if case:
                return case

    _, addr = parseaddr(email_data.get("from") or "")
    client_email = (addr or email_data.get("from") or "").strip()
    is_reply = bool(RE_PREFIX_RE.match(subject.strip()))
    if is_reply and client_email:
        cid = find_open_case_for_email(client_email)
        if cid:
            return get_incoming_request(cid)

    return None


def build_references_header(case_id: str, in_reply_to: Optional[str] = None) -> str:
    parts: List[str] = []
    for mid in get_all_outbound_message_ids(case_id):
        if mid:
            parts.append(mid if mid.startswith("<") else f"<{mid}>")
    if in_reply_to:
        irt = in_reply_to if in_reply_to.startswith("<") else f"<{in_reply_to}>"
        if irt not in parts:
            parts.append(irt)
    return " ".join(parts)


def conversation_for_llm(case_id: str) -> List[Dict[str, str]]:
    history: List[Dict[str, str]] = []
    for turn in list_turns_for_case(case_id):
        role = "assistant" if turn.get("direction") == "outbound" else "user"
        body = (turn.get("body") or "").strip()
        if body:
            history.append({"role": role, "content": body})
    return history


def record_initial_outbound(
    *,
    case_id: str,
    client_message: str,
    reply_body: str,
    subject: str,
    message_id: str,
) -> None:
    existing = list_turns_for_case(case_id)
    if not any(t.get("direction") == "inbound" for t in existing):
        insert_turn(
            case_id=case_id,
            direction="inbound",
            body=client_message,
            subject="Richiesta web",
            source="web_form",
        )
    insert_turn(
        case_id=case_id,
        direction="outbound",
        body=reply_body,
        subject=subject,
        message_id=message_id,
        source="smtp",
    )


def record_inbound_reply(email_data: Dict[str, Any], case_id: str) -> None:
    insert_turn(
        case_id=case_id,
        direction="inbound",
        body=email_data.get("body") or "",
        subject=email_data.get("subject") or "",
        message_id=email_data.get("message_id"),
        in_reply_to=email_data.get("in_reply_to"),
        email_references=email_data.get("references"),
        source="email",
    )


def record_outbound_reply(
    *,
    case_id: str,
    body: str,
    subject: str,
    message_id: str,
    in_reply_to: Optional[str] = None,
    email_references: Optional[str] = None,
) -> None:
    insert_turn(
        case_id=case_id,
        direction="outbound",
        body=body,
        subject=subject,
        message_id=message_id,
        in_reply_to=in_reply_to,
        email_references=email_references,
        source="smtp",
    )


def new_message_id() -> str:
    return f"<{uuid.uuid4()}@nstone.local>"
