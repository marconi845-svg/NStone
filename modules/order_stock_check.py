"""
Verifica disponibilità materiale sul catalogo online_stock (SQLite / CSV).
Scalo magazzino dopo conferma ordine.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _match_score(query: str, product: Dict[str, str]) -> float:
    q = _normalize(query)
    if not q:
        return 0.0
    fields = [
        product.get("Name", ""),
        product.get("Type", ""),
        product.get("Color", ""),
        f"{product.get('Name', '')} {product.get('Color', '')}",
    ]
    best = 0.0
    for field in fields:
        f = _normalize(field)
        if not f:
            continue
        if q in f or f in q:
            best = max(best, 0.92)
            continue
        q_tokens = set(re.findall(r"\w+", q))
        f_tokens = set(re.findall(r"\w+", f))
        if not q_tokens:
            continue
        overlap = len(q_tokens & f_tokens) / len(q_tokens)
        best = max(best, overlap)
    return best


def _parse_stock(value: str) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _load_sqlite_catalog_rows() -> List[Dict[str, Any]]:
    """Righe catalogo con id (solo SQLite)."""
    try:
        from modules.catalog_db import resolve_catalog_source, _configure_connection

        source, path = resolve_catalog_source()
        if source != "sqlite":
            return []
        conn = sqlite3.connect(str(path), timeout=2.0)
        _configure_connection(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, type, color, origin, finish, stock
            FROM online_stock
            ORDER BY name
            """
        ).fetchall()
        conn.close()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "Name": r["name"] or "",
                    "Type": r["type"] or "",
                    "Color": r["color"] or "",
                    "Stock": _format_stock_val(r["stock"]),
                }
            )
        return out
    except Exception as exc:
        logger.warning("Caricamento righe stock SQLite: %s", exc)
        return []


def _format_stock_val(value: Any) -> str:
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return "0"


def _ranked_matches(
    materiale: str,
    min_match_score: float = 0.35,
) -> List[Tuple[float, float, Dict[str, Any]]]:
    """(score, stock_mq, product_dict con id se SQLite)."""
    products = _load_sqlite_catalog_rows()
    if not products:
        try:
            from modules.catalog_db import load_catalog_products

            products = [
                {**p, "id": None} for p in load_catalog_products(use_cache=True)
            ]
        except Exception:
            return []

    scored: List[Tuple[float, float, Dict[str, Any]]] = []
    for product in products:
        score = _match_score(materiale, product)
        if score >= min_match_score:
            stock = _parse_stock(product.get("Stock", "0"))
            scored.append((score, stock, product))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return scored


def check_material_availability(
    materiale: str,
    quantita_mq: Optional[float] = None,
    *,
    min_match_score: float = 0.35,
) -> Dict[str, Any]:
    """
    Cerca il materiale nel catalogo e valuta disponibilità.

    Returns:
        availability: available | partial | unavailable | unknown
        materiale_richiesto, quantita_richiesta_mq, stock_totale_mq,
        matched_products (top 5), message (testo per Gemini)
    """
    materiale = (materiale or "").strip()
    result: Dict[str, Any] = {
        "availability": "unknown",
        "materiale_richiesto": materiale,
        "quantita_richiesta_mq": quantita_mq,
        "stock_totale_mq": 0.0,
        "matched_products": [],
        "message": "",
    }
    if not materiale:
        result["message"] = "Materiale non specificato nell'ordine."
        return result

    scored = _ranked_matches(materiale, min_match_score)
    if not scored:
        result["availability"] = "unavailable"
        result["message"] = (
            f"Nessuna lastra in catalogo corrisponde a «{materiale}»."
        )
        return result

    top = scored[:5]
    result["matched_products"] = [
        {
            "id": p.get("id"),
            "name": p.get("Name"),
            "stock_mq": s,
            "score": round(sc, 2),
            "type": p.get("Type"),
            "color": p.get("Color"),
        }
        for sc, s, p in top
    ]
    result["catalog_source"] = "sqlite" if scored and scored[0][2].get("id") else "csv_or_none"
    stock_total = sum(s for _, s, _ in scored[:10])
    result["stock_totale_mq"] = round(stock_total, 2)

    if quantita_mq is None or quantita_mq <= 0:
        if stock_total > 0:
            result["availability"] = "available"
            result["message"] = (
                f"Trovato in stock (~{stock_total} mq) per «{materiale}»; "
                "quantità ordine non specificata."
            )
        else:
            result["availability"] = "unavailable"
            result["message"] = f"Prodotto simile trovato ma stock a zero."
        return result

    if stock_total >= quantita_mq:
        result["availability"] = "available"
        result["message"] = (
            f"Disponibile: stock ~{stock_total} mq, richiesti {quantita_mq} mq."
        )
    elif stock_total > 0:
        result["availability"] = "partial"
        result["message"] = (
            f"Disponibilità parziale: stock ~{stock_total} mq, "
            f"richiesti {quantita_mq} mq."
        )
    else:
        result["availability"] = "unavailable"
        result["message"] = (
            f"Non disponibile: stock 0 mq, richiesti {quantita_mq} mq."
        )
    return result


def plan_stock_deduction(
    materiale: str,
    quantita_mq: float,
    availability: str,
    stock_report: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Tuple[int, float]], float]:
    """
    Piano addebito mq per riga catalogo (greedy sulle migliori match).
    Returns: ([(product_id, mq), ...], total_planned_mq)
    """
    if availability not in ("available", "partial") or quantita_mq <= 0:
        return [], 0.0

    scored = _ranked_matches(materiale)
    if not scored:
        return [], 0.0

    cap = quantita_mq
    if availability == "partial":
        total_stock = sum(s for _, s, _ in scored[:10])
        cap = min(quantita_mq, total_stock)

    remaining = cap
    plan: List[Tuple[int, float]] = []
    for _score, stock, product in scored:
        if remaining <= 1e-6:
            break
        pid = product.get("id")
        if pid is None:
            continue
        take = min(remaining, stock)
        if take > 1e-6:
            plan.append((int(pid), round(take, 3)))
            remaining -= take

    planned = round(cap - remaining, 3)
    return plan, planned


def apply_stock_deduction_for_order(
    order_id: str,
    materiale: str,
    quantita_mq: Optional[float],
    availability: str,
    stock_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Scala online_stock dopo conferma ordine. Idempotente per order_id.
    """
    from modules.orders_database import get_order_confirmation_meta

    meta = get_order_confirmation_meta(order_id)
    if meta.get("stock_deducted"):
        logger.info("Stock già scalato per ordine %s, skip", order_id)
        return meta.get("stock_deduction") or {"applied": False, "reason": "already_deducted"}

    if availability not in ("available", "partial"):
        return {"applied": False, "reason": f"availability_{availability}"}

    if quantita_mq is None or quantita_mq <= 0:
        return {"applied": False, "reason": "quantita_non_specificata"}

    plan, planned = plan_stock_deduction(
        materiale, float(quantita_mq), availability, stock_report
    )
    if not plan:
        return {
            "applied": False,
            "reason": "no_sqlite_rows",
            "planned_mq": planned,
        }

    from modules.catalog_db import decrement_online_stock_lines

    result = decrement_online_stock_lines(plan)
    result["order_id"] = order_id
    result["planned_mq"] = planned
    return result
