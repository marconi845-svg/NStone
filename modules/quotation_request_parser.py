"""
Parser richieste preventivo: LASTRE | PEZZI | LAVORATO.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

RequestType = str  # LASTRE | PEZZI | LAVORATO

PIECE_DIM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(?:cm|c\.m\.)?",
    re.IGNORECASE,
)
QTY_PEZZI_RE = re.compile(
    r"(\d+)\s*(?:pezzi?|pz\.?|unità|unita|pieces?|pcs\.?|units?)\b",
    re.IGNORECASE,
)
MQ_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:mq|m²|m2|sqm|sq\s*m|square\s*meters?|metri\s*quadri?)",
    re.IGNORECASE,
)

LAVORATO_KEYWORDS = (
    "top", "cucina", "soglia", "gradino", "davanzale", "lavabo",
    "foro", "lavello", "bordo", "smussat", "lucidat", "levigat",
    "lavorato", "lavorazione", "cnc", "sagomatur", "finito",
    "countertop", "kitchen top", "threshold", "step", "windowsill",
    "sink cutout", "edge", "polished", "fabrication", "honed",
)

LABOR_KEYWORD_MAP = {
    "taglio": "taglio_multifilo",
    "multifilo": "taglio_multifilo",
    "cutting": "taglio_multifilo",
    "wire saw": "taglio_multifilo",
    "lucidatur": "lucidatura",
    "lucido": "lucidatura",
    "polish": "lucidatura",
    "polishing": "lucidatura",
    "honing": "levigatura",
    "levigat": "levigatura",
    "foro": "foro_cnc",
    "lavello": "foro_cnc",
    "sink": "foro_cnc",
    "cnc": "foro_cnc",
    "sagomatur": "foro_cnc",
    "bordo": "bordo_lucidato",
    "smussat": "bordo_lucidato",
    "edge": "bordo_lucidato",
}


@dataclass
class PieceSpec:
    length_cm: float
    height_cm: float
    qty: int = 1


@dataclass
class ParsedQuotationRequest:
    request_type: RequestType
    pieces: List[PieceSpec] = field(default_factory=list)
    requested_mq: Optional[float] = None
    labor_operations: List[str] = field(default_factory=list)
    confidence: float = 0.5


def _to_float(raw: str) -> float:
    return float((raw or "0").replace(",", "."))


def detect_labor_operations(text: str) -> List[str]:
    low = (text or "").lower()
    found: List[str] = []
    for keyword, operation in LABOR_KEYWORD_MAP.items():
        if keyword in low and operation not in found:
            found.append(operation)
    return found


def parse_piece_specs(text: str) -> List[PieceSpec]:
    """Estrae pezzi con dimensioni L×H (cm) e quantità."""
    body = text or ""
    specs: List[PieceSpec] = []

    qty_default = 1
    qty_match = QTY_PEZZI_RE.search(body)
    if qty_match:
        qty_default = max(1, int(qty_match.group(1)))

    for match in PIECE_DIM_RE.finditer(body):
        l_cm = _to_float(match.group(1))
        h_cm = _to_float(match.group(2))
        if l_cm <= 0 or h_cm <= 0:
            continue
        if l_cm > 500 or h_cm > 500:
            continue
        specs.append(PieceSpec(length_cm=l_cm, height_cm=h_cm, qty=qty_default))

    if not specs:
        return []

    if len(specs) == 1 and qty_default > 1:
        specs[0].qty = qty_default

    return specs


def classify_request_type(text: str, *, has_pieces: bool) -> Tuple[RequestType, float]:
    low = (text or "").lower()

    if has_pieces:
        if any(k in low for k in LAVORATO_KEYWORDS):
            return "LAVORATO", 0.85
        return "PEZZI", 0.8

    if any(k in low for k in LAVORATO_KEYWORDS) and PIECE_DIM_RE.search(low):
        return "LAVORATO", 0.75

    if MQ_RE.search(low) or any(
        k in low for k in ("lastre", "lastra", "mq", "metri quadri", "m²")
    ):
        return "LASTRE", 0.7

    if any(k in low for k in ("pezzi", "pz ", "pz.", "unità")):
        return "PEZZI", 0.55

    return "LASTRE", 0.4


def parse_quotation_request(text: str) -> ParsedQuotationRequest:
    """Analizza messaggio cliente per tipo offerta e dimensioni."""
    body = (text or "").strip()
    pieces = parse_piece_specs(body)
    mq_match = MQ_RE.search(body)
    requested_mq = _to_float(mq_match.group(1)) if mq_match else None

    req_type, confidence = classify_request_type(body, has_pieces=bool(pieces))
    labor_ops = detect_labor_operations(body)

    if req_type == "LASTRE" and pieces and not requested_mq:
        req_type = "PEZZI" if not labor_ops else "LAVORATO"
        confidence = max(confidence, 0.75)

    if req_type == "PEZZI" and labor_ops:
        req_type = "LAVORATO"
        confidence = max(confidence, 0.8)

    return ParsedQuotationRequest(
        request_type=req_type,
        pieces=pieces,
        requested_mq=requested_mq,
        labor_operations=labor_ops,
        confidence=confidence,
    )
