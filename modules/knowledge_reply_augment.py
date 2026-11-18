"""
Rilevamento domande tecniche / policy e contesto da Retrieval Fabric.
Percorso parallelo alle offerte — non modifica catalog_db né pricing_engine.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from modules.knowledge_retriever import format_context_block, retrieve

TECHNICAL_SIGNAL_KEYWORDS: Tuple[str, ...] = (
    "assorbimento",
    "assorbente",
    "scheda tecnica",
    "scheda tecn",
    "technical sheet",
    "datasheet",
    "en 1469",
    "conformità",
    "conformita",
    "certificat",
    "resistenza",
    "densità",
    "densita",
    "mohs",
    "adatto per",
    "adatto all",
    "suitable for",
    "esterno",
    "outdoor",
    "piscina",
    "pool",
    "umidità",
    "umidita",
    "reso",
    "restitu",
    "reclamo",
    "claim",
    "policy",
    "garanzia",
    "warranty",
    "manutenzione",
    "maintenance",
    "procedura",
    "procedure",
    "manuale",
    "manual",
    "avvio",
    "startup",
    "allarme",
    "alarm",
    "tensione filo",
    "wire tension",
    "lead time",
    "tempi di consegna",
    "spessore non standard",
    "non standard thickness",
)

COMMERCIAL_SIGNAL_KEYWORDS: Tuple[str, ...] = (
    "preventivo",
    "quotation",
    "quote request",
    "request quote",
    "pricing",
    "estimate",
    "offerta commerciale",
    "quanto costa",
    "how much",
    "price per",
    "prezzo al",
    "prezzo per",
    "€/mq",
    "€/m2",
    "eur/mq",
    "euro/mq",
    "vorrei un preventivo",
    "richiedo preventivo",
    "need a quote",
    "send a quote",
    "purchase order",
    "ordine",
    "order",
)

_MQ_PATTERN = re.compile(
    r"\d+[\s,.]?\d*\s*(?:mq|m²|m2|sqm|metri\s*quadr)",
    re.IGNORECASE,
)
_PRICE_PATTERN = re.compile(
    r"(?:€|eur|euro|\$)\s*\d+|\d+\s*(?:€|eur|euro)",
    re.IGNORECASE,
)


def knowledge_config() -> Dict[str, Any]:
    try:
        from core.machine_plc_config import load_config

        raw = load_config().get("knowledge") or {}
        if not isinstance(raw, dict):
            raw = {}
    except Exception:
        raw = {}
    return {
        "technical_reply_enabled": bool(raw.get("technical_reply_enabled", True)),
        "technical_inbound_enabled": bool(raw.get("technical_inbound_enabled", True)),
    }


def _normalize(text: str) -> str:
    return (text or "").lower()


def has_technical_signal(text: str) -> bool:
    low = _normalize(text)
    return any(k in low for k in TECHNICAL_SIGNAL_KEYWORDS)


def has_commercial_signal(text: str) -> bool:
    low = _normalize(text)
    if any(k in low for k in COMMERCIAL_SIGNAL_KEYWORDS):
        return True
    if _MQ_PATTERN.search(text or ""):
        return True
    if _PRICE_PATTERN.search(text or ""):
        return True
    return False


def is_technical_only_message(text: str) -> bool:
    """True se la richiesta sembra solo tecnica/policy (no preventivo/prezzo/mq)."""
    if not knowledge_config().get("technical_reply_enabled", True):
        return False
    combined = (text or "").strip()
    if len(combined) < 12:
        return False
    return has_technical_signal(combined) and not has_commercial_signal(combined)


def build_knowledge_context_for_message(
    text: str,
    *,
    limit: int = 5,
) -> Tuple[str, List[Dict[str, Any]]]:
    hits = retrieve(text, limit=limit)
    return format_context_block(hits), hits
