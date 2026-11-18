"""
Catalogo prodotti unificato per pipeline offerte / AI Assistant.

Fonte canonica: data/nstonellm.db → tabella online_stock
(SQL only — init with: python database/init_db.py)
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"

# Chiavi attese da AIAssistant / UI catalogo
PRODUCT_KEYS = (
    "Name",
    "Type",
    "Color",
    "Origin",
    "Finish",
    "Thickness",
    "Dimensions",
    "Stock",
    "Price",
)

_catalog_cache: Optional[List[Dict[str, str]]] = None
_catalog_meta: Optional[Dict[str, Any]] = None


def get_database_path() -> Path:
    return DEFAULT_DB_PATH


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")


def _format_number(value: Any) -> str:
    if value is None or value == "":
        return "0"
    try:
        num = float(value)
        if num == int(num):
            return str(int(num))
        return str(num)
    except (TypeError, ValueError):
        return str(value).strip()


def _sqlite_row_to_product(row: sqlite3.Row) -> Dict[str, str]:
    keys = row.keys()
    price = row["price"] if "price" in keys else 0
    return {
        "Name": (row["name"] or "").strip(),
        "Type": (row["type"] or "").strip(),
        "Color": (row["color"] or "").strip(),
        "Origin": (row["origin"] or "").strip(),
        "Finish": (row["finish"] or "").strip(),
        "Thickness": _format_number(row["thickness"]),
        "Dimensions": (row["dimensions"] or "").strip(),
        "Stock": _format_number(row["stock"]),
        "Price": _format_number(price),
    }


def _sqlite_row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
    record = _sqlite_row_to_product(row)
    record["id"] = int(row["id"])
    return record


def _count_online_stock(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        _configure_connection(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='online_stock'"
        )
        if cur.fetchone()[0] == 0:
            conn.close()
            return 0
        count = conn.execute("SELECT COUNT(*) FROM online_stock").fetchone()[0]
        conn.close()
        return int(count)
    except sqlite3.Error as exc:
        logger.warning("Lettura conteggio online_stock fallita: %s", exc)
        return 0


def _load_from_sqlite(db_path: Path) -> List[Dict[str, str]]:
    conn = sqlite3.connect(str(db_path), timeout=2.0)
    _configure_connection(conn)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT name, type, color, origin, finish, thickness, dimensions, stock, price
            FROM online_stock
            ORDER BY name
            """
        ).fetchall()
        return [_sqlite_row_to_product(r) for r in rows]
    finally:
        conn.close()


def resolve_catalog_source(
    db_path: Optional[Path] = None,
) -> Tuple[str, Path]:
    """Restituisce ('sqlite', path_db) se online_stock ha righe."""
    db_path = db_path or DEFAULT_DB_PATH
    if _count_online_stock(db_path) > 0:
        return "sqlite", db_path
    raise FileNotFoundError(
        "Catalogo prodotti non disponibile. "
        f"DB: {db_path} (tabella online_stock vuota o assente). "
        "Esegui: python database/init_db.py"
    )


def load_catalog_products(
    *,
    use_cache: bool = True,
    db_path: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """Carica tutti i prodotti dal catalogo SQLite (chiavi Name, Type, …)."""
    global _catalog_cache, _catalog_meta

    if use_cache and _catalog_cache is not None:
        return _catalog_cache

    source, path = resolve_catalog_source(db_path=db_path)
    products = _load_from_sqlite(path)

    _catalog_cache = products
    _catalog_meta = {"source": source, "path": str(path), "count": len(products)}
    logger.info(
        "Catalogo caricato: %s prodotti da %s (%s)",
        len(products),
        source,
        path,
    )
    return products


def get_catalog_info() -> Dict[str, Any]:
    """Metadati ultimo caricamento (o risoluzione senza cache piena)."""
    global _catalog_meta
    if _catalog_meta is not None:
        return dict(_catalog_meta)
    try:
        source, path = resolve_catalog_source()
        count = _count_online_stock(path)
        return {"source": source, "path": str(path), "count": count}
    except FileNotFoundError as exc:
        return {"source": None, "path": None, "count": 0, "error": str(exc)}


def clear_catalog_cache() -> None:
    global _catalog_cache, _catalog_meta, _quotations_cache, _quotations_meta
    _catalog_cache = None
    _catalog_meta = None
    _quotations_cache = None
    _quotations_meta = None


# ---------------------------------------------------------------------------
# Preventivi (tabella quotations)
# ---------------------------------------------------------------------------

QUOTATION_HEADERS: Tuple[str, ...] = (
    "CLIENTE",
    "MATERIALE",
    "N° BLOCCO",
    "MISURE (CM)",
    "QUANTITÀ (MQ)",
    "PREZZO/MQ",
    "STATUS",
)


_quotations_cache: Optional[List[List[str]]] = None
_quotations_meta: Optional[Dict[str, Any]] = None


def _count_quotations(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        _configure_connection(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='quotations'"
        )
        if cur.fetchone()[0] == 0:
            conn.close()
            return 0
        count = conn.execute("SELECT COUNT(*) FROM quotations").fetchone()[0]
        conn.close()
        return int(count)
    except sqlite3.Error as exc:
        logger.warning("Lettura conteggio quotations fallita: %s", exc)
        return 0


def _format_quantita_display(quantita_mq: Any) -> str:
    try:
        value = float(quantita_mq)
        return f"{value:.2f} (NET VOLUME)"
    except (TypeError, ValueError):
        return str(quantita_mq or "")


def _format_prezzo_display(prezzo_mq: Any, valid_until: Optional[str]) -> str:
    try:
        prezzo = float(prezzo_mq)
        base = f"{prezzo:g} €/mq"
    except (TypeError, ValueError):
        base = str(prezzo_mq or "")
    if not valid_until:
        return base
    date_str = str(valid_until).strip()
    if len(date_str) >= 10 and date_str[4] == "-":
        try:
            from datetime import datetime

            parsed = datetime.strptime(date_str[:10], "%Y-%m-%d")
            date_str = parsed.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return f"{base} (VALID UNTIL {date_str})"


def _format_block_number(numero_blocco: str) -> str:
    text = (numero_blocco or "").strip()
    if text and not text.startswith("#"):
        return f"# {text}"
    return text


def _sqlite_row_to_quotation_row(row: sqlite3.Row) -> List[str]:
    return [
        (row["cliente"] or "").strip(),
        (row["materiale"] or "").strip(),
        _format_block_number(row["numero_blocco"] or ""),
        (row["misure_cm"] or "").strip(),
        _format_quantita_display(row["quantita_mq"]),
        _format_prezzo_display(row["prezzo_mq"], row["valid_until"]),
        str(row["status"] if row["status"] is not None else "0"),
    ]


def resolve_quotations_source(
    db_path: Optional[Path] = None,
) -> Tuple[str, Path]:
    db_path = db_path or DEFAULT_DB_PATH
    if _count_quotations(db_path) > 0:
        return "sqlite", db_path
    raise FileNotFoundError(
        "Preventivi non disponibili. "
        f"DB: {db_path} (tabella quotations vuota o assente). "
        "Esegui: python database/init_db.py"
    )


def load_quotations_table(
    *,
    use_cache: bool = True,
    db_path: Optional[Path] = None,
) -> Tuple[List[str], List[List[str]]]:
    """Carica preventivi per UI da SQLite. Restituisce (headers, righe)."""
    global _quotations_cache, _quotations_meta

    headers = list(QUOTATION_HEADERS)
    if use_cache and _quotations_cache is not None:
        return headers, _quotations_cache

    source, path = resolve_quotations_source(db_path=db_path)
    rows: List[List[str]] = []

    conn = sqlite3.connect(str(path), timeout=2.0)
    _configure_connection(conn)
    conn.row_factory = sqlite3.Row
    try:
        db_rows = conn.execute(
            """
            SELECT cliente, materiale, numero_blocco, misure_cm,
                   quantita_mq, prezzo_mq, status, valid_until
            FROM quotations
            ORDER BY id
            """
        ).fetchall()
        rows = [_sqlite_row_to_quotation_row(r) for r in db_rows]
    finally:
        conn.close()

    if not rows:
        raise ValueError("Nessun preventivo nel catalogo")

    _quotations_cache = rows
    _quotations_meta = {"source": source, "path": str(path), "count": len(rows)}
    logger.info("Preventivi caricati: %s da %s (%s)", len(rows), source, path)
    return headers, rows


def get_quotations_info() -> Dict[str, Any]:
    global _quotations_meta
    if _quotations_meta is not None:
        return dict(_quotations_meta)
    try:
        source, path = resolve_quotations_source()
        count = _count_quotations(path)
        return {"source": source, "path": str(path), "count": count}
    except (FileNotFoundError, ValueError) as exc:
        return {"source": None, "path": None, "count": 0, "error": str(exc)}


def decrement_online_stock_lines(
    deductions: List[Tuple[int, float]],
) -> Dict[str, Any]:
    """
    Scala stock (mq) sulle righe online_stock per id.
    deductions: [(product_id, mq_to_subtract), ...]
    """
    if not deductions:
        return {"applied": False, "reason": "empty", "lines": []}

    db_path = DEFAULT_DB_PATH
    try:
        source, path = resolve_catalog_source(db_path=db_path)
    except FileNotFoundError as exc:
        return {"applied": False, "reason": str(exc), "lines": []}

    lines_out: List[Dict[str, Any]] = []
    try:
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        cursor = conn.cursor()
        for product_id, mq in deductions:
            if mq <= 0:
                continue
            row = cursor.execute(
                "SELECT id, name, stock FROM online_stock WHERE id = ?",
                (int(product_id),),
            ).fetchone()
            if not row:
                lines_out.append(
                    {"id": product_id, "skipped": True, "reason": "not_found"}
                )
                continue
            old_stock = float(row[2] or 0)
            new_stock = max(0.0, round(old_stock - float(mq), 3))
            cursor.execute(
                "UPDATE online_stock SET stock = ? WHERE id = ?",
                (new_stock, int(product_id)),
            )
            lines_out.append(
                {
                    "id": int(product_id),
                    "name": row[1],
                    "deducted_mq": round(float(mq), 3),
                    "stock_before": old_stock,
                    "stock_after": new_stock,
                }
            )
        conn.commit()
        conn.close()
        clear_catalog_cache()
        total = round(sum(l.get("deducted_mq", 0) for l in lines_out), 3)
        logger.info("Stock scalato: %s mq su %s righe", total, len(lines_out))
        return {"applied": True, "total_deducted_mq": total, "lines": lines_out}
    except sqlite3.Error as exc:
        logger.error("Errore scalo stock: %s", exc)
        return {"applied": False, "reason": str(exc), "lines": lines_out}


class CatalogEditError(Exception):
    """Errore validazione o scrittura catalogo online_stock."""


def is_online_stock_editable(
    db_path: Optional[Path] = None,
) -> bool:
    return _online_stock_table_exists(db_path or DEFAULT_DB_PATH)


def load_online_stock_records(
    *,
    use_cache: bool = False,
    db_path: Optional[Path] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Carica righe catalogo con id (SQLite) per UI di gestione.
    Restituisce (source, records) con chiavi PRODUCT_KEYS + id.
    """
    _ = use_cache
    db_path = db_path or DEFAULT_DB_PATH

    if _online_stock_table_exists(db_path):
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        _configure_connection(conn)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, name, type, color, origin, finish,
                       thickness, dimensions, stock, price
                FROM online_stock
                ORDER BY name
                """
            ).fetchall()
            return "sqlite", [_sqlite_row_to_record(r) for r in rows]
        finally:
            conn.close()

    raise FileNotFoundError(
        "Catalogo prodotti non disponibile. "
        f"DB: {db_path} (tabella online_stock assente). "
        "Esegui: python database/init_db.py"
    )


def _parse_required_text(value: Any, field_label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CatalogEditError(f"{field_label} obbligatorio")
    return text


def _parse_required_float(value: Any, field_label: str) -> float:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        raise CatalogEditError(f"{field_label} obbligatorio")
    try:
        return float(text)
    except ValueError as exc:
        raise CatalogEditError(f"{field_label} non valido: {value}") from exc


def _product_input_to_db_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": _parse_required_text(data.get("Name"), "Nome"),
        "type": _parse_required_text(data.get("Type"), "Tipo"),
        "color": _parse_required_text(data.get("Color"), "Colore"),
        "origin": _parse_required_text(data.get("Origin"), "Origine"),
        "finish": _parse_required_text(data.get("Finish"), "Finitura"),
        "thickness": _parse_required_float(data.get("Thickness"), "Spessore"),
        "dimensions": _parse_required_text(data.get("Dimensions"), "Dimensioni"),
        "stock": _parse_required_float(data.get("Stock"), "Stock"),
        "price": _parse_required_float(data.get("Price"), "Prezzo"),
    }


def _online_stock_table_exists(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        _configure_connection(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='online_stock'"
        ).fetchone()
        conn.close()
        return bool(row and row[0])
    except sqlite3.Error:
        return False


def _resolve_sqlite_path(db_path: Optional[Path] = None) -> Path:
    db_path = db_path or DEFAULT_DB_PATH
    if not _online_stock_table_exists(db_path):
        raise CatalogEditError(
            "Modifica catalogo disponibile solo con SQLite e tabella online_stock. "
            "Esegui: python database/init_db.py"
        )
    return db_path


def insert_online_stock_product(
    data: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Inserisce una riga in online_stock."""
    try:
        fields = _product_input_to_db_fields(data)
        path = _resolve_sqlite_path(db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            cursor = conn.execute(
                """
                INSERT INTO online_stock
                    (name, type, color, origin, finish, thickness, dimensions, stock, price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fields["name"],
                    fields["type"],
                    fields["color"],
                    fields["origin"],
                    fields["finish"],
                    fields["thickness"],
                    fields["dimensions"],
                    fields["stock"],
                    fields["price"],
                ),
            )
            conn.commit()
            new_id = int(cursor.lastrowid)
        finally:
            conn.close()
        clear_catalog_cache()
        logger.info("Inserito prodotto online_stock id=%s name=%s", new_id, fields["name"])
        return {"ok": True, "id": new_id}
    except CatalogEditError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.Error as exc:
        logger.error("Errore insert online_stock: %s", exc)
        return {"ok": False, "error": str(exc)}


def update_online_stock_product(
    product_id: int,
    data: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Aggiorna una riga esistente in online_stock."""
    try:
        pid = int(product_id)
        fields = _product_input_to_db_fields(data)
        path = _resolve_sqlite_path(db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            existing = conn.execute(
                "SELECT id FROM online_stock WHERE id = ?",
                (pid,),
            ).fetchone()
            if not existing:
                raise CatalogEditError(f"Prodotto id={pid} non trovato")
            conn.execute(
                """
                UPDATE online_stock
                SET name = ?, type = ?, color = ?, origin = ?, finish = ?,
                    thickness = ?, dimensions = ?, stock = ?, price = ?
                WHERE id = ?
                """,
                (
                    fields["name"],
                    fields["type"],
                    fields["color"],
                    fields["origin"],
                    fields["finish"],
                    fields["thickness"],
                    fields["dimensions"],
                    fields["stock"],
                    fields["price"],
                    pid,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        clear_catalog_cache()
        logger.info("Aggiornato prodotto online_stock id=%s", pid)
        return {"ok": True, "id": pid}
    except CatalogEditError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.Error as exc:
        logger.error("Errore update online_stock: %s", exc)
        return {"ok": False, "error": str(exc)}


def delete_online_stock_product(
    product_id: int,
    *,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Elimina una riga da online_stock."""
    try:
        pid = int(product_id)
        path = _resolve_sqlite_path(db_path)
        conn = sqlite3.connect(str(path), timeout=5.0)
        _configure_connection(conn)
        try:
            cursor = conn.execute("DELETE FROM online_stock WHERE id = ?", (pid,))
            conn.commit()
            if cursor.rowcount == 0:
                raise CatalogEditError(f"Prodotto id={pid} non trovato")
        finally:
            conn.close()
        clear_catalog_cache()
        logger.info("Eliminato prodotto online_stock id=%s", pid)
        return {"ok": True, "id": pid}
    except CatalogEditError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.Error as exc:
        logger.error("Errore delete online_stock: %s", exc)
        return {"ok": False, "error": str(exc)}


def filter_products(
    products: List[Dict[str, str]],
    *,
    name_contains: Optional[str] = None,
    type_equals: Optional[str] = None,
    min_stock: Optional[float] = None,
) -> List[Dict[str, str]]:
    """Filtri semplici per pipeline offerte."""
    result = products
    if name_contains:
        needle = name_contains.lower()
        result = [p for p in result if needle in p.get("Name", "").lower()]
    if type_equals:
        want = type_equals.lower()
        result = [p for p in result if p.get("Type", "").lower() == want]
    if min_stock is not None:
        filtered = []
        for p in result:
            try:
                if float(p.get("Stock") or 0) >= min_stock:
                    filtered.append(p)
            except ValueError:
                continue
        result = filtered
    return result


def find_catalog_matches_for_message(
    text: str,
    *,
    limit: int = 3,
    min_score: float = 0.35,
) -> List[Dict[str, str]]:
    """Trova prodotti catalogo rilevanti per una richiesta cliente (offerte)."""
    from modules.order_stock_check import _match_score

    query = (text or "").strip()
    if not query:
        return []
    try:
        products = load_catalog_products(use_cache=True)
    except FileNotFoundError:
        return []

    scored: List[Tuple[float, Dict[str, str]]] = []
    for product in products:
        score = _match_score(query, product)
        if score >= min_score:
            scored.append((score, product))
    scored.sort(key=lambda x: (-x[0], x[1].get("Name", "")))

    seen_names: set = set()
    matches: List[Dict[str, str]] = []
    for _score, product in scored:
        name_key = product.get("Name", "").lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        matches.append(product)
        if len(matches) >= limit:
            break
    return matches


def format_catalog_context_for_offerte(
    products: List[Dict[str, str]],
    *,
    language: str = "it",
) -> str:
    """Blocco testo catalogo da iniettare nel prompt offerte."""
    if not products:
        if str(language).lower().startswith("en"):
            return (
                "ONLINE_STOCK CATALOG: no matching product for this request. "
                "Do not quote price or stock; propose internal verification."
            )
        return (
            "CATALOGO ONLINE_STOCK: nessun prodotto corrispondente trovato per questa richiesta. "
            "Non citare prezzi né stock; proponi verifica interna."
        )
    if str(language).lower().startswith("en"):
        lines = [
            "ONLINE_STOCK CATALOG — INTERNAL USE (do not copy these lines into the customer email):"
        ]
        unit = "sqm"
    else:
        lines = [
            "CATALOGO ONLINE_STOCK — USO INTERNO (non copiare queste righe nella email al cliente):"
        ]
        unit = "mq"
    for product in products:
        lines.append(
            f"- {product.get('Name', '')} | {product.get('Type', '')} | "
            f"{product.get('Finish', '')} | thick.{product.get('Thickness', '')} cm | "
            f"{product.get('Dimensions', '')} | stock {product.get('Stock', '')} {unit} | "
            f"{product.get('Price', '')} €/{unit}"
        )
    return "\n".join(lines)


def build_offerte_catalog_fact_line(product: Dict[str, str]) -> str:
    """Blocco offerta deterministico (delegato a llm_contexts)."""
    from llm.llm_contexts import format_offerte_commercial_block

    return format_offerte_commercial_block(product)


def extract_requested_mq(text: str) -> Optional[str]:
    """Estrae mq richiesti dal messaggio cliente (es. '5 mq')."""
    import re

    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:mq|m²|m2|sqm|sq\s*m|square\s*meters?|metri\s*quadri|metro\s*quadro|metros?\s*quadr)",
        (text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).replace(",", ".")


def _is_internal_catalog_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.upper().startswith("CATALOGO ONLINE_STOCK"):
        return True
    if s.startswith("- ") and "|" in s and "sp." in s:
        return True
    if "|" in s and "sp." in s and "€/mq" not in s:
        parts = [p.strip() for p in s.split("|")]
        if len(parts) >= 4 and any("sp." in p for p in parts):
            return True
    return False


def _is_offer_body_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    upper = s.upper()
    if "**EX WORKS**" in upper or upper == "EX WORKS":
        return True
    if s.startswith("**Disponibilità") or "salvo il venduto" in s.lower():
        return True
    if "€/mq" in s or "€/m2" in s.lower():
        return True
    if " · " in s and " cm" in s:
        return True
    if s.endswith(" cm") and any(ch.isdigit() for ch in s):
        return True
    return _is_internal_catalog_line(s)


def strip_internal_catalog_lines(text: str) -> str:
    kept = [ln for ln in (text or "").splitlines() if not _is_internal_catalog_line(ln)]
    return "\n".join(kept).strip()


def _extract_intro_closing(reply: str) -> Tuple[str, str]:
    """Separa saluto/intro dalla chiusura; scarta il corpo offerta generato dal modello."""
    lines = (reply or "").splitlines()
    intro_parts: List[str] = []
    closing_parts: List[str] = []
    mode = "intro"

    for line in lines:
        s = line.strip()
        if mode == "intro" and _is_offer_body_line(s):
            mode = "offer"
            continue
        if mode == "offer":
            if not s:
                continue
            if _is_offer_body_line(s):
                continue
            if "team nstone" in s.lower():
                closing_parts.append(line)
                mode = "closing"
                continue
            mode = "closing"
            closing_parts.append(line)
            continue
        if mode == "closing":
            closing_parts.append(line)
        else:
            intro_parts.append(line)

    intro = "\n".join(intro_parts).strip()
    closing = "\n".join(closing_parts).strip()
    if not closing:
        closing = "Restiamo a disposizione per ogni chiarimento.\n\nTeam NStone"
    elif "team nstone" not in closing.lower():
        closing = f"{closing.rstrip()}\n\nTeam NStone"
    return intro, closing


def build_pricing_context_for_message(
    customer_message: str,
    matches: List[Dict[str, str]],
) -> tuple:
    """
    Calcolo prezzi deterministico + testo per prompt LLM.
    Returns (pricing_context_str, QuotationPricingResult | None).
    """
    try:
        from modules.pricing_engine import (
            calculate_quotation_pricing,
            format_labor_rates_for_prompt,
        )

        pricing = calculate_quotation_pricing(customer_message, matches)
        if not pricing:
            return "", None
        parts = [pricing.to_prompt_context()]
        if pricing.request_type in ("PEZZI", "LAVORATO"):
            labor = format_labor_rates_for_prompt()
            if labor:
                parts.append(labor)
        ctx = "\n\n".join(p for p in parts if p)
        return ctx, pricing
    except Exception as exc:
        logger.debug("Pricing context non disponibile: %s", exc)
        return "", None


def finalize_offerte_reply(
    reply: str,
    matches: List[Dict[str, str]],
    *,
    customer_message: str = "",
    language: str = "it",
) -> str:
    """
    Ricostruisce la risposta: intro LLM + blocco offerta deterministico + chiusura.
    Elimina righe catalogo interne e duplicati del modello.
    """
    import re

    lang = "en" if str(language).lower().startswith("en") else "it"
    default_intro = (
        "Thank you for your inquiry." if lang == "en" else "Grazie per la richiesta."
    )

    if not matches:
        text = strip_internal_catalog_lines(reply)
        text = re.sub(
            r"\[Nome del rappresentante[^\]]*\]",
            "Team NStone",
            text,
            flags=re.IGNORECASE,
        )
        if "team nstone" not in text.lower():
            text = f"{text.rstrip()}\n\nTeam NStone"
        return text.strip()

    intro, closing = _extract_intro_closing(strip_internal_catalog_lines(reply))
    if not intro:
        intro = default_intro

    _, pricing = build_pricing_context_for_message(customer_message, matches)
    if pricing and (pricing.total_ex_works_eur > 0 or pricing.mq_net > 0):
        blocks = [pricing.to_offer_block()]
    else:
        mq = extract_requested_mq(customer_message)
        from llm.llm_contexts import format_offerte_commercial_block

        blocks = [
            format_offerte_commercial_block(
                product,
                quantita_mq=mq if i == 0 else None,
                language=lang,  # type: ignore[arg-type]
            )
            for i, product in enumerate(matches[:3])
        ]
    body = "\n\n".join(blocks)
    return f"{intro.rstrip()}\n\n{body}\n\n{closing.strip()}".strip()


def enforce_offerte_catalog_in_reply(
    reply: str,
    matches: List[Dict[str, str]],
    *,
    customer_message: str = "",
    language: str = "it",
) -> str:
    """Normalizza risposta offerta: blocco commerciale deterministico + firma Team NStone."""
    return finalize_offerte_reply(
        reply,
        matches,
        customer_message=customer_message,
        language=language,
    )
