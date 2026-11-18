"""Test percorso parallelo risposte tecniche (Opzione C)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules import incoming_requests_db as ird
from modules import technical_auto_pipeline as tap
from modules.knowledge_reply_augment import (
    has_commercial_signal,
    has_technical_signal,
    is_technical_only_message,
)
from modules.technical_inbound_pipeline import is_inbound_technical_inquiry


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "nstonellm.db"
    ird.set_database_path(db)
    ird.ensure_incoming_request_table(db_path=db)
    yield db
    ird.set_database_path(None)


def test_technical_only_vs_commercial():
    assert has_technical_signal("Qual è l'assorbimento d'acqua del Carrara CD?")
    assert has_commercial_signal("Preventivo Carrara 100 mq lucido")
    assert is_technical_only_message("Qual è l'assorbimento d'acqua del Carrara CD?")
    assert not is_technical_only_message("Preventivo Carrara 100 mq lucido")
    assert not is_technical_only_message("Quanto costa Carrara 2 cm per 50 mq?")


def test_inbound_technical_not_quotation():
    assert is_inbound_technical_inquiry(
        "Assorbimento Carrara",
        "Buongiorno, vorrei sapere l'assorbimento d'acqua del Carrara CD.",
    )
    assert not is_inbound_technical_inquiry(
        "Preventivo Carrara",
        "Vorrei un preventivo per 80 mq Carrara lucido 2 cm",
    )
    assert not is_inbound_technical_inquiry(
        "Re: Offerta",
        "Qual è l'assorbimento d'acqua?",
    )


def test_elaborate_technical_draft_without_send(temp_db: Path, monkeypatch):
    ird.insert_incoming_request(
        {
            "id": "tech-1",
            "timestamp": "2026-06-08T10:00:00",
            "nome": "Luigi",
            "email": "luigi@example.com",
            "messaggio": "Entro quanto posso restituire merce integra?",
            "stato": "NUOVA_TECNICA",
        },
        db_path=temp_db,
    )
    monkeypatch.setattr(
        "modules.technical_reply_module.generate_technical_reply_for_client",
        lambda _data: "Reso entro 14 giorni dal DDT firmato.",
    )
    result = tap.elaborate_technical_request("tech-1", send_email=False)
    assert result["ok"] is True
    assert result["kind"] == "technical"
    assert result["email_sent"] is False
    row = ird.get_incoming_request("tech-1", db_path=temp_db)
    assert row["stato"] == "BOZZA_TECNICA"
    assert "14 giorni" in row["risposta_gemini"]


def test_quotation_pipeline_untouched_for_commercial(temp_db: Path, monkeypatch):
    """Verifica che elaborate_quotation_request non importi il modulo tecnico."""
    from modules import quotation_auto_pipeline as qap

    ird.insert_incoming_request(
        {
            "id": "req-q-1",
            "timestamp": "2026-06-08T10:00:00",
            "nome": "Mario",
            "email": "mario@example.com",
            "messaggio": "Preventivo Carrara 100mq",
            "stato": "NUOVA",
        },
        db_path=temp_db,
    )
    called = {"technical": False, "quotation": False}

    def _tech(_data):
        called["technical"] = True
        return "tech"

    def _quote(_data):
        called["quotation"] = True
        return "Bozza offerta test"

    monkeypatch.setattr(
        "modules.gemini_module.generate_reply_for_client",
        _quote,
    )
    monkeypatch.setattr(
        "modules.technical_reply_module.generate_technical_reply_for_client",
        _tech,
    )
    result = qap.elaborate_quotation_request("req-q-1", send_email=False)
    assert result["ok"] is True
    assert called["quotation"] is True
    assert called["technical"] is False


def test_thread_routes_technical_only(monkeypatch):
    from modules import quotation_reply_pipeline as qrp

    case = {
        "id": "case-1",
        "nome": "Anna",
        "email": "anna@example.com",
        "messaggio": "Preventivo inviato",
    }
    routed = {"technical": False, "quotation": False}

    def _tech(_case, msg, hist):
        routed["technical"] = True
        return "Risposta tecnica"

    def _quote(_case, msg, hist):
        routed["quotation"] = True
        return "Risposta offerta"

    monkeypatch.setattr(
        "modules.technical_reply_module.generate_technical_thread_reply",
        _tech,
    )
    monkeypatch.setattr(
        "modules.gemini_module.generate_quotation_thread_reply",
        _quote,
    )
    monkeypatch.setattr(
        "modules.quotation_email_thread.record_inbound_reply",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "modules.quotation_email_thread.conversation_for_llm",
        lambda _id: [],
    )
    monkeypatch.setattr(
        "modules.quotation_auto_pipeline.office_may_auto_email",
        lambda: False,
    )
    monkeypatch.setattr(
        "modules.incoming_requests_db.update_incoming_request",
        lambda *a, **k: None,
    )

    email_data = {"body": "Qual è l'assorbimento d'acqua del Carrara CD?"}
    ok = qrp.process_client_quotation_reply(email_data, case, use_llm=True)
    assert ok is True
    assert routed["technical"] is True
    assert routed["quotation"] is False
