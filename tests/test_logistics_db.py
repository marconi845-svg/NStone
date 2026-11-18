"""Test modulo tracking logistico."""
from pathlib import Path

import pytest

from modules.logistics_db import (
    delete_stock_position,
    get_latest_positions,
    init_logistics_tables,
    insert_stock_position,
    list_stock_position_records,
    normalize_block_uid,
    record_location_scan,
    update_stock_position,
)


@pytest.fixture
def logistics_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    init_logistics_tables(db)
    return db


def test_normalize_block_uid():
    assert normalize_block_uid("#12849") == "12849"
    assert normalize_block_uid("  abc ") == "ABC"


def test_record_and_latest_position(logistics_db: Path):
    record_location_scan(
        block_uid="12849",
        lat=45.46,
        lon=9.19,
        materiale="Carrara",
        operator_id="test",
        db_path=logistics_db,
    )
    record_location_scan(
        block_uid="12849",
        lat=45.47,
        lon=9.20,
        materiale="Carrara",
        db_path=logistics_db,
    )
    record_location_scan(
        block_uid="99999",
        lat=45.50,
        lon=9.25,
        db_path=logistics_db,
    )
    positions = get_latest_positions(db_path=logistics_db)
    assert len(positions) == 2
    by_uid = {p["block_uid"]: p for p in positions}
    assert by_uid["12849"]["lat"] == pytest.approx(45.47)
    assert by_uid["99999"]["lat"] == pytest.approx(45.50)


def test_invalid_coordinates(logistics_db: Path):
    with pytest.raises(ValueError):
        record_location_scan(block_uid="1", lat=999, lon=9, db_path=logistics_db)


def test_stock_position_crud(logistics_db: Path):
    ins = insert_stock_position(
        {
            "block_uid": "CRUD01",
            "materiale": "Carrara",
            "lat": 45.1,
            "lon": 9.1,
            "zone_label": "Piazzale A",
        },
        db_path=logistics_db,
    )
    assert ins["ok"] is True
    rows = list_stock_position_records(db_path=logistics_db)
    assert any(r["block_uid"] == "CRUD01" for r in rows)
    upd = update_stock_position(
        "CRUD01",
        {"materiale": "Calacatta", "lat": 45.2, "lon": 9.2},
        db_path=logistics_db,
    )
    assert upd["ok"] is True
    latest = get_latest_positions(block_uid="CRUD01", db_path=logistics_db)
    assert latest[0]["lat"] == pytest.approx(45.2)
    deleted = delete_stock_position("CRUD01", db_path=logistics_db)
    assert deleted["ok"] is True
    rows_after = list_stock_position_records(db_path=logistics_db)
    assert not any(r["block_uid"] == "CRUD01" for r in rows_after)
