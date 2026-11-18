from pathlib import Path

from fastapi.testclient import TestClient

from fastapi_backend import main


def _set_test_storage(tmp_path: Path) -> Path:
    import modules.incoming_requests_db as ird

    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    db_path = test_data_dir / "nstonellm.db"
    ird.set_database_path(db_path)
    ird.ensure_incoming_request_table(db_path=db_path)
    main.DATA_DIR = test_data_dir
    main.MESSAGES_FILE = test_data_dir / "messages.json"
    return db_path


def test_health_check(tmp_path: Path) -> None:
    _set_test_storage(tmp_path)
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert "timestamp" in payload


def test_receive_form_and_get_messages(tmp_path: Path) -> None:
    _set_test_storage(tmp_path)
    client = TestClient(main.app)

    response = client.post(
        "/api/form",
        data={
            "nome": "Mario Rossi",
            "email": "mario@example.com",
            "messaggio": "Richiedo preventivo",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    list_response = client.get("/api/messages")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["success"] is True
    assert list_body["total"] == 1
    assert list_body["messages"][0]["email"] == "mario@example.com"


def test_delete_request_flow(tmp_path: Path) -> None:
    _set_test_storage(tmp_path)
    client = TestClient(main.app)

    create = client.post(
        "/api/form",
        data={
            "nome": "Cliente",
            "email": "cliente@example.com",
            "messaggio": "Test delete",
        },
    )
    assert create.status_code == 200
    request_id = create.json()["id"]

    delete = client.delete("/api/delete_request", params={"request_id": request_id})
    assert delete.status_code == 200
    assert delete.json()["success"] is True

    get_deleted = client.get("/api/get_request", params={"request_id": request_id})
    assert get_deleted.status_code == 404


def test_elabora_returns_503_when_gemini_missing(tmp_path: Path) -> None:
    _set_test_storage(tmp_path)
    client = TestClient(main.app)
    original = main.generate_reply_for_client
    main.generate_reply_for_client = None
    try:
        response = client.post("/api/elabora", params={"request_id": "fake-id"})
        assert response.status_code == 503
    finally:
        main.generate_reply_for_client = original


def test_elabora_returns_503_when_llm_not_ready(tmp_path: Path, monkeypatch) -> None:
    db_path = _set_test_storage(tmp_path)
    import modules.incoming_requests_db as ird

    ird.insert_incoming_request(
        {
            "id": "rid-1",
            "timestamp": "2026-01-01",
            "nome": "Test",
            "email": "a@b.it",
            "messaggio": "prezzo carrara",
            "stato": "NUOVA",
        },
        db_path=db_path,
    )

    from modules.gemini_module import GeminiReplyError

    def _fail_llm(_data):
        raise GeminiReplyError("Ollama non disponibile (test).", code="missing_api_key")

    monkeypatch.setattr("modules.gemini_module.generate_reply_for_client", _fail_llm)

    client = TestClient(main.app)
    response = client.post("/api/elabora", params={"request_id": "rid-1"})
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]
