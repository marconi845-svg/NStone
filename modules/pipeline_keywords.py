"""
Parole chiave bilingue IT+EN per pipeline Quotations / Orders (ingresso IMAP e regole).
L'uscita LLM segue resolve_llm_language() in llm_contexts — qui solo matching inbound.
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple

# --- Quotations: nuova richiesta inbound ---
QUOTATION_INBOUND_KEYWORDS: Tuple[str, ...] = (
    # IT (esistenti)
    "preventivo",
    "richiesta",
    "offerta",
    # EN
    "quotation",
    "quote request",
    "request quote",
    "quote",
    "pricing",
    "estimate",
)

STONE_CONTEXT_KEYWORDS: Tuple[str, ...] = (
    # IT
    "preventivo",
    "richiesta",
    "marmo",
    "pietra",
    "granito",
    "lastra",
    "nstone",
    "travertino",
    "calacatta",
    # EN
    "marble",
    "granite",
    "stone",
    "slab",
    "slabs",
    "limestone",
    "travertine",
    "quotation",
    "quote",
    "pricing",
    "estimate",
)

# Esclude conferma ordine da nuova richiesta preventivo
CONFIRMATION_BLOCK_KEYWORDS: Tuple[str, ...] = (
    "confermo l'ordine",
    "confermo ordine",
    "conferma ordine",
    "accetto l'ordine",
    "accetto ordine",
    "procediamo con l'ordine",
    "i confirm the order",
    "confirm the order",
    "confirm order",
    "i accept the order",
    "accept the order",
    "accept the quote",
    "accept the offer",
    "proceed with the order",
    "proceed with order",
)

QUOTATION_CONTEXT_KEYWORDS: Tuple[str, ...] = (
    "preventivo",
    "richiesta",
    "quotation",
    "quote",
    "quote request",
    "pricing",
    "estimate",
)

# --- IMAP fetch (Gmail poll) ---
QUOTATION_IMAP_SUBJECT_KEYWORDS: Tuple[str, ...] = (
    "preventivo",
    "richiesta",
    "quotation",
    "quote",
    "NS-Q",
    "NStone",
    "ns-q",
)

QUOTATION_IMAP_BODY_KEYWORDS: Tuple[str, ...] = (
    "preventivo",
    "richiesta",
    "quotation",
    "quote",
    "quote request",
)

ORDER_IMAP_BODY_KEYWORDS: Tuple[str, ...] = (
    "confermo",
    "conferma",
    "accetto",
    "ordine",
    "procedete",
    "confirm",
    "confirmed",
    "accepted",
    "proceed",
    "purchase order",
)

ORDER_IMAP_EXTRA_SUBJECT_KEYWORDS: Tuple[str, ...] = (
    "ordine",
    "order",
    "confermo",
    "conferma",
    "accetto",
    "confirm",
    "purchase order",
)

DEFAULT_SUBJECT_KEYWORDS: Tuple[str, ...] = (
    "ordine",
    "order",
    "purchase order",
    "preventivo",
    "offerta",
    "richiesta",
    "quotation",
    "quote",
    "estimate",
    "confermo",
    "conferma",
    "accetto",
    "confirm",
    "confirmed",
    "accepted",
    "nstone",
    "ns-q",
)

# --- Conferma ordine (regole NS-Q / ordini) ---
CONFIRMATION_PHRASES: Tuple[str, ...] = (
    # IT (esistenti)
    "confermo l'ordine",
    "confermo ordine",
    "conferma ordine",
    "accetto l'ordine",
    "accetto ordine",
    "accetto l'offerta",
    "accetto offerta",
    "procediamo con l'ordine",
    "procediamo con ordine",
    "procediamo",
    "va bene procediamo",
    "ok procediamo",
    "d'accordo",
    "confermo",
    "accetto",
    "va bene",
    "ok per",
    "perfetto procediamo",
    # EN
    "i confirm the order",
    "confirm the order",
    "confirm order",
    "order confirmed",
    "i accept the order",
    "accept the order",
    "i accept the quote",
    "accept the quote",
    "i accept the offer",
    "accept the offer",
    "proceed with the order",
    "proceed with order",
    "please proceed",
    "ok to proceed",
    "go ahead",
    "approved",
    "accepted",
)

NEGATION_PHRASES: Tuple[str, ...] = (
    "non confermo",
    "non accetto",
    "annullo",
    "cancella",
    "rifiuto",
    "non procediamo",
    "non voglio",
    "don't confirm",
    "do not confirm",
    "don't accept",
    "do not accept",
    "cancel order",
    "cancel the order",
    "reject",
    "decline",
)

MODIFICATION_PHRASES: Tuple[str, ...] = (
    "invece",
    "solo ",
    "solamente",
    "modifico",
    "cambio",
    "riduco",
    "aumento",
    "non ",
    "ma ",
    "instead",
    "only ",
    "change to",
    "change ",
    "reduce",
    "but ",
)

CONFIRMATION_HINT_KEYWORDS: Tuple[str, ...] = (
    "confermo",
    "conferma",
    "accetto",
    "procedete",
    "vada per",
    "confirm",
    "confirmed",
    "accepted",
    "accept",
    "proceed",
    "go ahead",
)

ORDER_MARKERS: Tuple[str, ...] = (
    "ordine",
    "order",
    "purchase order",
    "confermo",
    "conferma",
)

QUOTE_MARKERS: Tuple[str, ...] = (
    "preventivo",
    "richiesta",
    "ns-q",
    "nstone",
    "quotation",
    "quote",
    "estimate",
    "pricing",
)

_OFFER_RE = re.compile(r"\boffer\b", re.IGNORECASE)


def combined_lower(*parts: str) -> str:
    return " ".join((p or "").strip() for p in parts if p).strip().lower()


def text_contains_any(text: str, keywords: Iterable[str]) -> bool:
    low = (text or "").lower()
    return any(kw in low for kw in keywords)


def is_confirmation_hint(subject: str, body: str) -> bool:
    combined = combined_lower(subject, body)
    return text_contains_any(combined, CONFIRMATION_HINT_KEYWORDS)


def offer_term_requires_stone_context(combined: str) -> bool:
    """True se compare offerta/offer senza contesto pietra/preventivo."""
    low = combined.lower()
    has_offer = "offerta" in low or bool(_OFFER_RE.search(low))
    if not has_offer:
        return False
    return not text_contains_any(low, STONE_CONTEXT_KEYWORDS)


def confirmation_rule_fallback_match(combined: str) -> bool:
    """Fallback conferm/accett + ordine/offerta (IT) o confirm/accept + order/quote (EN)."""
    low = combined.lower()
    it_hit = ("conferm" in low or "accett" in low) and any(
        x in low for x in ("ordine", "offerta", "preventivo")
    )
    en_hit = ("confirm" in low or "accept" in low) and any(
        x in low for x in ("order", "quote", "quotation", "offer")
    )
    return it_hit or en_hit


def json_fallback_confirmation_status(text: str) -> str | None:
    """confirmed | cancelled | None — dopo JSON decode fallito."""
    low = (text or "").lower()
    if any(
        x in low
        for x in (
            "confermo",
            "conferma",
            "accetto",
            "confirm the order",
            "confirm order",
            "i confirm",
            "accepted",
            "proceed with",
        )
    ):
        return "confirmed"
    if any(
        x in low
        for x in (
            "cancello",
            "annulla",
            "non voglio",
            "cancel order",
            "reject",
            "decline",
        )
    ):
        return "cancelled"
    return None
