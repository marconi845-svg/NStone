"""
Motore prezzi NStone: materiale da lastra (€/mq catalogo) + lavorazioni + scarto.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from modules.pricing_config import load_pricing_config, waste_pct_for_material
from modules.pricing_labor_db import get_labor_rate, list_labor_rates
from modules.quotation_request_parser import ParsedQuotationRequest, parse_quotation_request

logger = logging.getLogger(__name__)


@dataclass
class PricingLineItem:
    label: str
    quantity: float
    unit: str
    unit_price_eur: float
    subtotal_eur: float


@dataclass
class QuotationPricingResult:
    request_type: str
    material_name: str
    price_mq_eur: float
    mq_net: float
    mq_with_waste: float
    waste_pct: float
    line_items: List[PricingLineItem] = field(default_factory=list)
    total_ex_works_eur: float = 0.0
    warnings: List[str] = field(default_factory=list)
    piece_summary: str = ""
    catalog_product: Dict[str, str] = field(default_factory=dict)

    def to_prompt_context(self) -> str:
        if not self.line_items:
            return ""
        lines = [
            "CALCOLO PREZZI (da listino lastra — NON modificare importi):",
            f"Tipo richiesta: {self.request_type}",
            f"Materiale lastra: {self.material_name} @ {self.price_mq_eur:g} €/mq",
        ]
        if self.request_type != "LASTRE":
            lines.append(
                f"Superficie: {self.mq_net:.2f} mq netti → "
                f"{self.mq_with_waste:.2f} mq (scarto {self.waste_pct:g}%)"
            )
            if self.piece_summary:
                lines.append(f"Pezzi: {self.piece_summary}")
        for item in self.line_items:
            lines.append(
                f"- {item.label}: {item.quantity:g} {item.unit} × "
                f"{item.unit_price_eur:g} € = {item.subtotal_eur:,.2f} €".replace(",", "X").replace("X", ",")
            )
        lines.append(f"TOTALE EX WORKS: {self.total_ex_works_eur:,.2f} €".replace(",", "X").replace("X", ","))
        if self.warnings:
            lines.append("Note: " + "; ".join(self.warnings))
        return "\n".join(lines)

    def to_offer_block(self) -> str:
        from llm.llm_contexts import format_offerte_commercial_block, format_offerte_pricing_block

        if self.request_type == "LASTRE" and self.catalog_product and self.mq_net > 0:
            return format_offerte_commercial_block(
                self.catalog_product,
                quantita_mq=f"{self.mq_net:g}",
            )
        return format_offerte_pricing_block(self)


def _piece_area_mq(length_cm: float, height_cm: float) -> float:
    return (length_cm * height_cm) / 10_000.0


def _round_eur(value: float) -> float:
    return round(value, 2)


def _apply_labor_charge(
    operation: str,
    *,
    mq: float,
    n_pezzi: int,
    ml_bordo: float = 0.0,
) -> Optional[PricingLineItem]:
    rate = get_labor_rate(operation)
    if not rate:
        return None

    unit = (rate.get("unit") or "").lower()
    price = float(rate.get("rate_eur") or 0)
    min_ch = float(rate.get("min_charge_eur") or 0)
    label = rate.get("label") or operation

    qty = 0.0
    unit_label = unit
    if unit == "per_mq":
        qty = mq
        unit_label = "mq"
    elif unit == "per_pezzo":
        qty = float(max(1, n_pezzi))
        unit_label = "pz"
    elif unit == "per_ml":
        qty = ml_bordo if ml_bordo > 0 else max(1.0, (mq ** 0.5) * 4)
        unit_label = "ml"
    else:
        return None

    subtotal = max(_round_eur(qty * price), _round_eur(min_ch) if min_ch > 0 else 0.0)
    if min_ch > 0 and qty * price < min_ch:
        subtotal = _round_eur(min_ch)

    return PricingLineItem(
        label=label,
        quantity=round(qty, 3),
        unit=unit_label,
        unit_price_eur=price,
        subtotal_eur=subtotal,
    )


def calculate_quotation_pricing(
    customer_message: str,
    catalog_products: List[Dict[str, str]],
    *,
    parsed: Optional[ParsedQuotationRequest] = None,
) -> Optional[QuotationPricingResult]:
    """
    Calcola preventivo da prezzo lastra catalogo.
    Ritorna None se manca prodotto o prezzo in catalogo.
    """
    if not catalog_products:
        return None

    product = catalog_products[0]
    material_name = (product.get("Name") or "").strip()
    try:
        price_mq = float(product.get("Price") or 0)
    except (TypeError, ValueError):
        price_mq = 0.0

    if price_mq <= 0:
        return None

    parsed = parsed or parse_quotation_request(customer_message)
    mtype = (product.get("Type") or "").strip()
    waste_pct = waste_pct_for_material(material_name, mtype)
    warnings: List[str] = []

    thickness = (product.get("Thickness") or "").strip()
    finish = (product.get("Finish") or "").strip()
    dimensions = (product.get("Dimensions") or "").strip()

    # --- LASTRE: mq diretti ---
    if parsed.request_type == "LASTRE":
        mq = parsed.requested_mq
        if mq is None or mq <= 0:
            try:
                mq = float(product.get("Stock") or 0)
            except (TypeError, ValueError):
                mq = None
        if mq is None or mq <= 0:
            warnings.append("Quantità mq non indicata — indicare mq richiesti")
            return QuotationPricingResult(
                request_type="LASTRE",
                material_name=material_name,
                price_mq_eur=price_mq,
                mq_net=0.0,
                mq_with_waste=0.0,
                waste_pct=waste_pct,
                warnings=warnings,
            )

        material_sub = _round_eur(mq * price_mq)
        items = [
            PricingLineItem(
                label=f"Materiale {material_name}",
                quantity=round(mq, 3),
                unit="mq",
                unit_price_eur=price_mq,
                subtotal_eur=material_sub,
            )
        ]
        total = material_sub
        return QuotationPricingResult(
            request_type="LASTRE",
            material_name=material_name,
            price_mq_eur=price_mq,
            mq_net=mq,
            mq_with_waste=mq,
            waste_pct=0.0,
            line_items=items,
            total_ex_works_eur=total,
            warnings=warnings,
            piece_summary=f"{mq:g} mq · {thickness} cm · {finish} · {dimensions}",
            catalog_product=dict(product),
        )

    # --- PEZZI / LAVORATO ---
    if not parsed.pieces:
        warnings.append("Misure pezzi non rilevate — chiedere L×H cm e quantità")
        return None

    mq_net = 0.0
    n_pezzi_total = 0
    piece_parts: List[str] = []
    for spec in parsed.pieces:
        area = _piece_area_mq(spec.length_cm, spec.height_cm)
        mq_net += area * spec.qty
        n_pezzi_total += spec.qty
        piece_parts.append(
            f"{spec.qty} pz {spec.length_cm:g}×{spec.height_cm:g} cm"
        )

    mq_with_waste = _round_eur(mq_net * (1.0 + waste_pct / 100.0))
    material_sub = _round_eur(mq_with_waste * price_mq)

    items: List[PricingLineItem] = [
        PricingLineItem(
            label=f"Materiale {material_name} (da lastra)",
            quantity=mq_with_waste,
            unit="mq",
            unit_price_eur=price_mq,
            subtotal_eur=material_sub,
        )
    ]

    ops = list(parsed.labor_operations)
    if parsed.request_type == "LAVORATO" and "taglio_multifilo" not in ops:
        ops.insert(0, "taglio_multifilo")
    if parsed.request_type == "LAVORATO" and any(
        o in ops for o in ("lucidatura", "levigatura")
    ) is False and any(k in customer_message.lower() for k in ("lucid", "levig", "finito")):
        ops.append("lucidatura")

    perimeter_ml = 0.0
    for spec in parsed.pieces:
        perimeter_ml += 2 * (spec.length_cm + spec.height_cm) / 100.0 * spec.qty

    for op in ops:
        labor_item = _apply_labor_charge(
            op,
            mq=mq_net,
            n_pezzi=n_pezzi_total,
            ml_bordo=perimeter_ml,
        )
        if labor_item:
            items.append(labor_item)

    total = _round_eur(sum(i.subtotal_eur for i in items))

    return QuotationPricingResult(
        request_type=parsed.request_type,
        material_name=material_name,
        price_mq_eur=price_mq,
        mq_net=_round_eur(mq_net),
        mq_with_waste=mq_with_waste,
        waste_pct=waste_pct,
        line_items=items,
        total_ex_works_eur=total,
        warnings=warnings,
        piece_summary=" + ".join(piece_parts) + f" · {thickness} cm · {finish}",
        catalog_product=dict(product),
    )


def format_labor_rates_for_prompt() -> str:
    """Elenco tariffe lavorazione per contesto LLM."""
    rates = list_labor_rates()
    if not rates:
        return ""
    lines = ["TARIFFE LAVORAZIONE (uso interno):"]
    for r in rates:
        lines.append(
            f"- {r.get('label')}: {r.get('rate_eur')} €/{r.get('unit', '').replace('per_', '')}"
        )
    return "\n".join(lines)
