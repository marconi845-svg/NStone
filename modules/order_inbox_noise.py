"""Filtro unico: mail che non sono ordini NStone (Amazon, job alert, newsletter)."""
from __future__ import annotations

from email.utils import parseaddr

_NOISE_SENDER_FRAGMENTS = (
    "amazon.",
    "order-update@",
    "shipment-tracking@",
    "donotreply@amazon",
    "newsletter.",
    "push.infojobs",
    "infojobs.",
    "trabajo.org",
    "euspert.com",
    "facile.it",
    "talent.com",
    "indeed.",
    "linkedin.",
    "monster.",
    "glassdoor.",
    "stepstone.",
    "jobalert",
    "no-reply@alerts",
    "valentina@",
    "preventivi@newsletter",
    "offerte@push",
    "leroymerlin",
    "noreply@crm",
)

_NOISE_SUBJECT_BODY_FRAGMENTS = (
    "ordine amazon",
    "amazon.it",
    "amazon.com",
    "consegna effettuata",
    "in consegna oggi",
    "shipment",
    "tracking",
    "offerta di lavoro",
    "offerte di lavoro",
    " offerte per ",
    "nuove offerte per te",
    "nuove offerte",
    "mutui",
    "belle offerte",
    "buyer",
    "candidati oggi",
    "recensiscilo su amazon",
    "soddisfatto le tue aspettative",
    "spedizione amazon",
    "il tuo ordine amazon",
    "tuo ordine amazon",
)


def is_inbox_noise(
    *,
    subject: str = "",
    body: str = "",
    sender: str = "",
) -> bool:
    from_header = str(sender or "")
    _, addr = parseaddr(from_header)
    sender_l = (addr or from_header).lower()
    for frag in _NOISE_SENDER_FRAGMENTS:
        if frag in sender_l:
            return True
    combined = f"{subject or ''} {body or ''}".lower()
    for frag in _NOISE_SUBJECT_BODY_FRAGMENTS:
        if frag in combined:
            return True
    return False
