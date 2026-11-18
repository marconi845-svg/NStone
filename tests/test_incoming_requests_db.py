from pathlib import Path

import pytest

from modules import incoming_requests_db as ird


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "nstonellm.db"
    ird.ensure_incoming_request_table(db_path=db)
    return db


def test_insert_list_delete(temp_db: Path):
    msg = {
        "id": "req-1",
        "timestamp": "2026-01-01T10:00:00",
        "nome": "Mario",
        "email": "m@example.com",
        "messaggio": "Quote please",
        "stato": "NUOVA",
    }
    assert ird.insert_incoming_request(msg, db_path=temp_db)["ok"]
    rows = ird.list_incoming_requests(db_path=temp_db)
    assert len(rows) == 1
    assert rows[0]["email"] == "m@example.com"
    assert ird.delete_incoming_request("req-1", db_path=temp_db)["ok"]
    assert ird.list_incoming_requests(db_path=temp_db) == []
