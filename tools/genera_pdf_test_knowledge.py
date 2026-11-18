#!/usr/bin/env python3
"""Genera PDF di test per Import PDF in Retrieval Fabric."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "knowledge" / "samples"
OUT_PATH = OUT_DIR / "listino_test_nstone.pdf"
FONT_DIR = Path("C:/Windows/Fonts")
FONT = "ArialUni"


def _fonts(pdf: FPDF) -> None:
    pdf.add_font(FONT, "", str(FONT_DIR / "arial.ttf"))
    pdf.add_font(FONT, "B", str(FONT_DIR / "arialbd.ttf"))


def _table_row(pdf: FPDF, cols: list[str], *, header: bool = False) -> None:
    widths = [38, 52, 28, 32, 30]
    pdf.set_font(FONT, "B" if header else "", 9)
    pdf.set_fill_color(42, 42, 58) if header else pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(255, 255, 255) if header else pdf.set_text_color(20, 20, 20)
    for text, w in zip(cols, widths):
        pdf.cell(w, 7, text, border=1, fill=header, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)


def build_pdf() -> FPDF:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    _fonts(pdf)

    pdf.set_font(FONT, "B", 16)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Listino test NStone — Carrara CD", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.set_font(FONT, "", 10)
    pdf.multi_cell(
        0,
        5,
        "Documento di prova per Retrieval Fabric · Import PDF. "
        "Prezzi indicativi EX WORKS magazzino Carrara. Validità pilota 2026.",
    )
    pdf.ln(4)

    pdf.set_font(FONT, "B", 11)
    pdf.cell(0, 7, "Lucido 2 cm", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    _table_row(pdf, ["Codice", "Materiale", "Finitura", "EUR/m2", "Note"], header=True)
    rows = [
        ["CAR-LUC-20", "Carrara CD", "Lucido", "85,00", "Standard"],
        ["CAR-LUC-20-M", "Carrara CD", "Lev. mate", "93,00", "+8 vs lucido"],
        ["CAR-SPA-20", "Carrara CD", "Spazzolato", "88,00", "Antiscivolo"],
        ["CAR-LUC-30", "Carrara CD", "Lucido 3cm", "112,00", "Soglie/top"],
    ]
    for row in rows:
        _table_row(pdf, row)

    pdf.ln(6)
    pdf.set_x(pdf.l_margin)
    pdf.set_font(FONT, "B", 11)
    pdf.cell(0, 7, "Regole commerciali", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font(FONT, "", 10)
    bullets = [
        "Sconto quantità oltre 200 m²: -5% su accordo commerciale.",
        "Resa taglio multifilo: calcolare +8% su mq lordi per Carrara CD.",
        "Tempi consegna EX WORKS: 5-7 gg lavorativi su stock.",
        "Materiali con assorbimento > 0,15%: verificare idoneità esterno.",
    ]
    for line in bullets:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 5, f"  -  {line}")

    pdf.add_page()
    pdf.set_font(FONT, "B", 14)
    pdf.cell(0, 9, "Pagina 2 — Note tecniche", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    pdf.set_font(FONT, "", 10)
    pdf.multi_cell(
        0,
        5,
        "Assorbimento d'acqua Carrara CD: 0,08-0,15% (EN 1469). "
        "Spessore commerciale 2 cm per pavimenti interni; 3 cm per soglie e gradini.",
    )
    pdf.ln(3)
    pdf.set_font(FONT, "B", 10)
    pdf.cell(0, 6, "Query di test suggerite in tab Ask:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(FONT, "", 10)
    queries = [
        "Prezzo Carrara lucido 2 cm EX WORKS",
        "Sconto oltre 200 metri quadri",
        "Assorbimento d'acqua Carrara CD",
    ]
    for q in queries:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 5, f"  ?  {q}")

    return pdf


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf = build_pdf()
    pdf.output(str(OUT_PATH))
    print(f"Creato: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
