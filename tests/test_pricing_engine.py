"""Test motore prezzi da lastra + pezzi/lavorati."""
from pathlib import Path

import pytest

from modules.pricing_config import waste_pct_for_material
from modules.pricing_labor_db import ensure_pricing_labor_table, get_labor_rate
from modules.pricing_engine import calculate_quotation_pricing
from modules.quotation_request_parser import parse_quotation_request


CARRARA = {
    "Name": "Bianco Carrara CD",
    "Type": "Marble",
    "Finish": "Polished",
    "Thickness": "2",
    "Dimensions": "305x152",
    "Stock": "550",
    "Price": "75",
}


def test_waste_pct_marmo():
    assert waste_pct_for_material("Bianco Carrara CD", "Marble") == 8.0
    assert waste_pct_for_material("Granite Black", "Granite") == 5.0


def test_parse_pezzi_request():
    parsed = parse_quotation_request(
        "Richiesta preventivo 12 pezzi 60x240 cm Carrara lucidato"
    )
    assert parsed.request_type in ("PEZZI", "LAVORATO")
    assert len(parsed.pieces) >= 1
    assert parsed.pieces[0].length_cm == 60
    assert parsed.pieces[0].height_cm == 240


def test_lastre_pricing_mq(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "modules.pricing_labor_db.get_database_path",
        lambda: tmp_path / "db.sqlite",
    )
    ensure_pricing_labor_table(db_path=tmp_path / "db.sqlite")

    result = calculate_quotation_pricing(
        "Vorrei 25 mq di Carrara CD 2cm lucido",
        [CARRARA],
    )
    assert result is not None
    assert result.request_type == "LASTRE"
    assert result.mq_net == 25.0
    assert result.total_ex_works_eur == 25.0 * 75.0


def test_pezzi_pricing_from_slab(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "modules.pricing_labor_db.get_database_path",
        lambda: tmp_path / "db.sqlite",
    )
    ensure_pricing_labor_table(db_path=tmp_path / "db.sqlite")

    msg = "Preventivo 10 pezzi 60x240 cm Bianco Carrara CD"
    result = calculate_quotation_pricing(msg, [CARRARA])
    assert result is not None
    assert result.request_type in ("PEZZI", "LAVORATO")
    # 10 × (0.6 × 2.4) = 14.4 mq netti
    assert result.mq_net == pytest.approx(14.4, rel=0.01)
    assert result.mq_with_waste == pytest.approx(14.4 * 1.08, rel=0.01)
    material_line = result.line_items[0]
    assert material_line.subtotal_eur == pytest.approx(
        result.mq_with_waste * 75.0, rel=0.01
    )
    assert result.total_ex_works_eur > material_line.subtotal_eur or result.request_type == "PEZZI"


def test_lavorato_includes_taglio(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "modules.pricing_labor_db.get_database_path",
        lambda: tmp_path / "db.sqlite",
    )
    ensure_pricing_labor_table(db_path=tmp_path / "db.sqlite")

    msg = "Top cucina 2 pezzi 60x240 cm Calacatta lucidato con foro lavello"
    parsed = parse_quotation_request(msg)
    assert parsed.request_type == "LAVORATO"
    assert "foro_cnc" in parsed.labor_operations or "lucidatura" in parsed.labor_operations

    calcite = dict(CARRARA)
    calcite["Name"] = "Calacatta Gold"
    calcite["Price"] = "550"
    result = calculate_quotation_pricing(msg, [calcite], parsed=parsed)
    assert result is not None
    assert len(result.line_items) >= 2
    assert result.total_ex_works_eur > result.line_items[0].subtotal_eur


def test_offer_block_contains_total(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "modules.pricing_labor_db.get_database_path",
        lambda: tmp_path / "db.sqlite",
    )
    ensure_pricing_labor_table(db_path=tmp_path / "db.sqlite")

    result = calculate_quotation_pricing(
        "10 pezzi 100x50 cm Carrara",
        [CARRARA],
    )
    assert result is not None
    block = result.to_offer_block()
    assert "TOTALE EX WORKS" in block
    assert "EX WORKS" in block
    assert "75" in block or "€" in block


def test_labor_rate_seeded(tmp_path: Path):
    db = tmp_path / "labor.db"
    ensure_pricing_labor_table(db_path=db)
    rate = get_labor_rate("taglio_multifilo")
    assert rate is not None
    assert float(rate["rate_eur"]) == 25.0
