from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules import incoming_requests_db as ird
from modules import quotation_auto_pipeline as qap
from core.autonomy_policy import PolicyResult


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "nstonellm.db"
    ird.set_database_path(db)
    ird.ensure_incoming_request_table(db_path=db)
    yield db
    ird.set_database_path(None)


def _insert_nuova(db: Path, rid: str = "req-auto-1") -> str:
    ird.insert_incoming_request(
        {
            "id": rid,
            "timestamp": "2026-06-08T10:00:00",
            "nome": "Mario",
            "email": "mario@example.com",
            "messaggio": "Preventivo Carrara 100mq",
            "stato": "NUOVA",
        },
        db_path=db,
    )
    return rid


def test_office_may_auto_email_uses_policy(monkeypatch):
    policy = MagicMock()
    policy.allow.return_value = PolicyResult(True, "ok")
    monkeypatch.setattr("core.autonomy_policy.get_policy", lambda: policy)
    assert qap.office_may_auto_email() is True
    policy.allow.return_value = PolicyResult(False, "blocked")
    assert qap.office_may_auto_email() is False


def test_process_pending_skipped_when_autonomy_low(temp_db: Path, monkeypatch):
    _insert_nuova(temp_db)
    monkeypatch.setattr(qap, "office_may_auto_email", lambda: False)
    out = qap.process_pending_nuova_requests()
    assert out.get("processed") == 0
    row = ird.get_incoming_request("req-auto-1", db_path=temp_db)
    assert row["stato"] == "NUOVA"


def test_elaborate_draft_without_send(temp_db: Path, monkeypatch):
    rid = _insert_nuova(temp_db)
    monkeypatch.setattr(
        "modules.gemini_module.generate_reply_for_client",
        lambda _data: "Bozza offerta test",
    )
    result = qap.elaborate_quotation_request(rid, send_email=False)
    assert result["ok"] is True
    assert result["email_sent"] is False
    row = ird.get_incoming_request(rid, db_path=temp_db)
    assert row["stato"] == "BOZZA_IN_ATTESA"
    assert "Bozza" in row["risposta_gemini"]
