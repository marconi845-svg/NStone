"""
Generazione PDF conferma d'ordine NStone (allegato email cliente).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_confirmations_pdf_dir() -> Path:
    out = PROJECT_ROOT / "logs" / "order_confirmations"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _safe_pdf_text(value: Any, *, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    # Helvetica core font: evita caratteri problematici
    replacements = {
        "€": " EUR",
        "–": "-",
        "—": "-",
        "’": "'",
        """: '"',
        """: '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text or "-"


def _availability_label(code: Optional[str]) -> str:
    mapping = {
        "available": "Disponibile",
        "partial": "Disponibilita parziale",
        "unavailable": "Non disponibile",
        "unknown": "Da verificare",
    }
    return mapping.get((code or "").lower(), _safe_pdf_text(code))


def _status_label(status: Optional[str]) -> str:
    mapping = {
        "CONFIRMED": "Confermato",
        "CONFIRMED_PARTIAL": "Confermato (parziale)",
        "REJECTED_STOCK": "Non confermato - stock",
        "PENDING_APPROVAL": "In attesa approvazione",
        "NEW": "Nuovo",
    }
    return mapping.get((status or "").upper(), _safe_pdf_text(status))


def _format_qty(qty: Any) -> str:
    if qty is None or qty == "":
        return "-"
    try:
        val = float(qty)
        if val == int(val):
            return f"{int(val)} mq"
        return f"{val:.2f} mq"
    except (TypeError, ValueError):
        return _safe_pdf_text(qty)


def build_confirmation_table_rows(data: Dict[str, Any]) -> List[Tuple[str, str]]:
    rows = [
        ("N. ordine", _safe_pdf_text(data.get("order_id"))),
        ("Data", _safe_pdf_text(data.get("confirmation_date"))),
        ("Cliente", _safe_pdf_text(data.get("client_name"))),
        ("Email", _safe_pdf_text(data.get("client_email"))),
        ("Materiale", _safe_pdf_text(data.get("materiale"))),
        ("Quantita", _format_qty(data.get("quantita"))),
        ("Macchina / reparto", _safe_pdf_text(data.get("machine"), max_len=80)),
        ("Riferimento preventivo", _safe_pdf_text(data.get("quotation_ref"), max_len=100)),
        ("Disponibilita stock", _availability_label(data.get("availability"))),
        ("Stato ordine", _status_label(data.get("status"))),
    ]
    return rows


def generate_order_confirmation_pdf(
    data: Dict[str, Any],
    *,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Crea PDF conferma ordine. Ritorna path file o None se fpdf2 assente / errore.
    """
    order_id = (data.get("order_id") or "ordine").strip()
    safe_id = re.sub(r"[^\w.\-]+", "_", order_id)[:64]
    out_dir = output_dir or get_confirmations_pdf_dir()
    out_path = out_dir / f"conferma_{safe_id}.pdf"

    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError:
        logger.warning("fpdf2 non installato — conferma PDF saltata")
        return None

    confirmation_date = data.get("confirmation_date") or datetime.now().strftime(
        "%d/%m/%Y %H:%M"
    )
    data = {**data, "confirmation_date": confirmation_date}
    rows = build_confirmation_table_rows(data)
    notes = _safe_pdf_text(data.get("notes"), max_len=500)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf = FPDF(format="A4")
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.set_margins(18, 18, 18)
        pdf.add_page()

        w = pdf.epw
        col_label = w * 0.38
        col_value = w - col_label

        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(40, 30, 60)
        pdf.multi_cell(w, 8, "NStone - Conferma d'ordine")
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(80, 80, 90)
        pdf.multi_cell(
            w,
            5,
            _safe_pdf_text(
                "Documento generato automaticamente. Prezzi e condizioni EX WORKS salvo diverso accordo."
            ),
        )
        pdf.ln(6)

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 30, 35)
        pdf.multi_cell(w, 6, "Dati ordine")
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 10)
        line_h = 7
        for label, value in rows:
            pdf.set_fill_color(245, 245, 250)
            pdf.set_text_color(60, 60, 70)
            pdf.cell(col_label, line_h, f"  {label}", border=1, fill=True)
            pdf.set_text_color(20, 20, 25)
            pdf.cell(
                col_value,
                line_h,
                f"  {value}",
                border=1,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(w, 6, "Note")
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(w, 5, notes if notes != "-" else "Nessuna nota aggiuntiva.")

        pdf.ln(8)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 100, 110)
        pdf.multi_cell(w, 5, "Team NStone - Marmo e pietre naturali")

        pdf.output(str(out_path))
        logger.info("PDF conferma ordine creato: %s", out_path)
        return out_path
    except Exception as exc:
        logger.error("Generazione PDF conferma fallita (%s): %s", order_id, exc)
        return None


def build_pdf_data_from_quotation_confirmation(
    *,
    order_id: str,
    case: Dict[str, Any],
    order_fields: Dict[str, Any],
    analysis: Dict[str, Any],
    stock_report: Dict[str, Any],
    db_status: str,
) -> Dict[str, Any]:
    from modules.quotation_email_thread import case_token

    case_id = str(case.get("id") or "")
    return {
        "order_id": order_id,
        "client_name": case.get("nome") or case.get("email") or "",
        "client_email": case.get("email") or "",
        "materiale": order_fields.get("materiale") or "",
        "quantita": order_fields.get("quantita"),
        "machine": order_fields.get("machine") or "",
        "quotation_ref": case_token(case_id) if case_id else "",
        "availability": analysis.get("availability") or stock_report.get("availability"),
        "status": db_status,
        "notes": analysis.get("notes") or stock_report.get("message") or "",
    }


def build_pdf_data_from_order_record(
    order: Dict[str, Any],
    *,
    analysis: Optional[Dict[str, Any]] = None,
    stock_report: Optional[Dict[str, Any]] = None,
    db_status: str = "CONFIRMED",
) -> Dict[str, Any]:
    analysis = analysis or {}
    stock_report = stock_report or {}
    oid = order.get("order_id") or order.get("id") or ""
    qcid = order.get("quotation_case_id") or ""
    qref = ""
    if qcid:
        try:
            from modules.quotation_email_thread import case_token

            qref = case_token(str(qcid))
        except Exception:
            qref = str(qcid)[:8]
    return {
        "order_id": oid,
        "client_name": order.get("client") or "",
        "client_email": order.get("client_email") or order.get("from") or "",
        "materiale": order.get("materiale") or order.get("product") or "",
        "quantita": order.get("quantita"),
        "machine": order.get("machine") or "",
        "quotation_ref": qref,
        "availability": analysis.get("availability") or stock_report.get("availability"),
        "status": db_status,
        "notes": analysis.get("notes") or "",
    }


def pdf_attachment_for_email(pdf_path: Path) -> Dict[str, str]:
    return {
        "path": str(pdf_path),
        "filename": pdf_path.name,
    }
