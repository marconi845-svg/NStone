from pathlib import Path

from fastapi.testclient import TestClient

from fastapi_backend import main


def test_logistics_scan_and_positions(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "nstonellm.db"
    monkeypatch.setattr("modules.logistics_db.get_database_path", lambda: db)

    client = TestClient(main.app)
    payload = {
        "block_uid": "DEMO01",
        "lat": 45.4642,
        "lon": 9.1900,
        "materiale": "Test",
        "operator_id": "pytest",
    }
    r = client.post("/api/logistics/scan", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["block_uid"] == "DEMO01"

    r2 = client.get("/api/logistics/positions")
    assert r2.status_code == 200
    data = r2.json()
    assert data["count"] >= 1
    assert any(p["block_uid"] == "DEMO01" for p in data["positions"])
