"""Test generazione PDF conferma ordine."""
from pathlib import Path

import pytest

from modules.order_confirmation_pdf import (
    build_confirmation_table_rows,
    generate_order_confirmation_pdf,
    get_confirmations_pdf_dir,
)


def test_build_confirmation_table_rows():
    rows = build_confirmation_table_rows(
        {
            "order_id": "Q-abc-20260101",
            "confirmation_date": "03/06/2026",
            "client_name": "Mario Rossi",
            "client_email": "mario@example.com",
            "materiale": "Bianco Carrara CD",
            "quantita": 25.0,
            "machine": "multifilo",
            "quotation_ref": "[NS-Q-a1b2c3d4]",
            "availability": "available",
            "status": "CONFIRMED",
        }
    )
    assert any(r[0] == "N. ordine" and "Q-abc" in r[1] for r in rows)
    assert any(r[0] == "Quantita" and "25 mq" in r[1] for r in rows)


def test_generate_order_confirmation_pdf(tmp_path: Path):
    fpdf = pytest.importorskip("fpdf")
    _ = fpdf  # noqa: F841

    out_dir = tmp_path / "pdfs"
    path = generate_order_confirmation_pdf(
        {
            "order_id": "TEST-001",
            "client_name": "Cliente Test",
            "client_email": "test@example.com",
            "materiale": "Calacatta",
            "quantita": 12.5,
            "machine": "lucidatrice",
            "availability": "partial",
            "status": "CONFIRMED_PARTIAL",
            "notes": "Stock parziale",
        },
        output_dir=out_dir,
    )
    assert path is not None
    assert path.is_file()
    assert path.suffix.lower() == ".pdf"
    assert path.stat().st_size > 500


def test_get_confirmations_pdf_dir_creates_folder(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "modules.order_confirmation_pdf.PROJECT_ROOT",
        tmp_path,
    )
    d = get_confirmations_pdf_dir()
    assert d.is_dir()
    assert d.name == "order_confirmations"
