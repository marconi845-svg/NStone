"""Test resolver catalogo prodotti."""
from pathlib import Path

import pytest

from modules import catalog_db


@pytest.fixture(autouse=True)
def clear_cache():
    catalog_db.clear_catalog_cache()
    yield
    catalog_db.clear_catalog_cache()


def test_resolve_catalog_source_prefers_sqlite_when_populated():
    db = catalog_db.get_database_path()
    if catalog_db._count_online_stock(db) == 0:
        pytest.skip("online_stock vuoto nel DB di test")
    source, path = catalog_db.resolve_catalog_source()
    assert source == "sqlite"
    assert path == db


def test_load_catalog_products_has_expected_keys():
    try:
        products = catalog_db.load_catalog_products(use_cache=False)
    except FileNotFoundError:
        pytest.skip("DB catalogo non disponibile (python database/init_db.py)")
    assert len(products) > 0
    first = products[0]
    for key in catalog_db.PRODUCT_KEYS:
        assert key in first


def test_resolve_catalog_source_requires_sqlite(tmp_path):
    empty_db = tmp_path / "empty.db"
    with pytest.raises(FileNotFoundError):
        catalog_db.resolve_catalog_source(db_path=empty_db)


def test_load_quotations_table_has_rows():
    try:
        headers, rows = catalog_db.load_quotations_table(use_cache=False)
    except (FileNotFoundError, ValueError):
        pytest.skip("Preventivi non disponibili nel DB di test")
    assert len(headers) == len(catalog_db.QUOTATION_HEADERS)
    assert len(rows) > 0
    assert len(rows[0]) == len(headers)


def test_filter_products_by_type():
    products = [
        {"Name": "A", "Type": "Marble", "Stock": "5"},
        {"Name": "B", "Type": "Granite", "Stock": "1"},
    ]
    filtered = catalog_db.filter_products(products, type_equals="Marble")
    assert len(filtered) == 1
    assert filtered[0]["Name"] == "A"


def _init_test_db(db_path: Path) -> None:
    conn = catalog_db.sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE online_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            color TEXT NOT NULL,
            origin TEXT NOT NULL,
            finish TEXT NOT NULL,
            thickness REAL NOT NULL,
            dimensions TEXT NOT NULL,
            stock REAL NOT NULL,
            price REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.close()


def test_online_stock_crud(tmp_path):
    db = tmp_path / "stock.db"
    _init_test_db(db)
    sample = {
        "Name": "Test Marble",
        "Type": "Marble",
        "Color": "White",
        "Origin": "Italy",
        "Finish": "Polished",
        "Thickness": "2",
        "Dimensions": "300x200",
        "Stock": "50",
        "Price": "80",
    }
    ins = catalog_db.insert_online_stock_product(sample, db_path=db)
    assert ins["ok"] is True
    pid = ins["id"]

    source, records = catalog_db.load_online_stock_records(db_path=db)
    assert source == "sqlite"
    assert len(records) == 1
    assert records[0]["Name"] == "Test Marble"

    upd = catalog_db.update_online_stock_product(
        pid, {**sample, "Stock": "40"}, db_path=db
    )
    assert upd["ok"] is True
    _, records = catalog_db.load_online_stock_records(db_path=db)
    assert records[0]["Stock"] == "40"

    delete = catalog_db.delete_online_stock_product(pid, db_path=db)
    assert delete["ok"] is True
    _, records = catalog_db.load_online_stock_records(db_path=db)
    assert records == []

def test_insert_requires_name(tmp_path):
    db = tmp_path / "stock.db"
    _init_test_db(db)
    result = catalog_db.insert_online_stock_product({"Name": ""}, db_path=db)
    assert result["ok"] is False


def test_enforce_catalog_injects_price():
    matches = [
        {
            "Name": "Calacatta Gold",
            "Type": "Marble",
            "Finish": "Polished",
            "Thickness": "3",
            "Dimensions": "280x180",
            "Price": "550",
            "Stock": "85",
        }
    ]
    messy = """Buongiorno,

Calacatta Gold | Marble | Polished | sp.3 cm | 280x180

5 mq · 3 cm · Lucidato
280x180 cm

550 €/mq
**EX WORKS**
**Disponibilità: 85 mq, salvo il venduto**

Restiamo in attesa."""
    out = catalog_db.finalize_offerte_reply(
        messy,
        matches,
        customer_message="vorrei 5 mq di Calacatta Gold",
    )
    assert "Calacatta Gold | Marble" not in out
    assert out.splitlines()[0] != "Calacatta Gold | Marble"
    assert out.splitlines()[0] == "Calacatta Gold" or "Buongiorno" in out.splitlines()[0]
    assert "5 mq · 3 cm · Lucidato" in out
    assert "280x180 cm" in out
    assert "550 €/mq" in out
    assert "**EX WORKS**" in out
    assert "**Disponibilità: 85 mq, salvo il venduto**" in out
    assert "Team NStone" in out
