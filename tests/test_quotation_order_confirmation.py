"""Test conferma ordine su thread preventivo NS-Q."""
from pathlib import Path
from unittest.mock import patch

import pytest

from modules import incoming_requests_db as ird
from modules import quotation_email_db as qdb
from modules.quotation_email_thread import make_initial_subject
from modules.quotation_order_confirmation_pipeline import (
    case_is_already_confirmed,
    client_requests_modification,
    extract_mq_from_text,
    extract_order_fields_from_thread,
    has_outbound_offer,
    is_order_confirmation_intent,
    process_quotation_order_confirmation,
    try_process_quotation_order_confirmation,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "nstonellm.db"
    ird.set_database_path(db)
    ird.ensure_incoming_request_table(db_path=db)
    qdb.ensure_quotation_email_tables(db_path=db)
    yield db
    ird.set_database_path(None)


CASE_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _seed_case(temp_db: Path, *, stato: str = "IN_CONVERSAZIONE") -> dict:
    case = {
        "id": CASE_ID,
        "timestamp": "2026-06-01T10:00:00",
        "nome": "Mario",
        "email": "mario@example.com",
        "messaggio": "Richiesta preventivo Carrara 25 mq",
        "stato": stato,
    }
    ird.insert_incoming_request(case, db_path=temp_db)
    ird.update_incoming_request(
        CASE_ID,
        {"email_inviata": True, "data_invio_email": "2026-06-01T11:00:00"},
        db_path=temp_db,
    )
    qdb.insert_turn(
        case_id=CASE_ID,
        direction="outbound",
        body="Offerta Carrara CD 25 mq a 45 EUR/mq EX WORKS",
        subject=make_initial_subject(CASE_ID, "Mario"),
        message_id="<offer@nstone.local>",
        db_path=temp_db,
    )
    return case


def test_is_order_confirmation_intent():
    ok, conf = is_order_confirmation_intent(
        "Re: preventivo",
        "Confermo l'ordine per 25 mq Carrara come da offerta. Procediamo.",
    )
    assert ok is True
    assert conf >= 0.65

    ok2, _ = is_order_confirmation_intent("Re:", "Quanto costa la spedizione?")
    assert ok2 is False


def test_extract_mq_and_modification():
    assert extract_mq_from_text("Confermo 20 mq di Carrara") == 20.0
    assert client_requests_modification("Confermo solo 15 mq invece di 25") is True


def test_has_outbound_offer_required(temp_db: Path):
    case = _seed_case(temp_db)
    assert has_outbound_offer(CASE_ID) is True
    ird.insert_incoming_request(
        {
            "id": "empty-case-0000-0000-0000-000000000001",
            "timestamp": "2026-06-01T10:00:00",
            "nome": "Luigi",
            "email": "luigi@example.com",
            "messaggio": "Test",
            "stato": "NUOVA",
        },
        db_path=temp_db,
    )
    assert has_outbound_offer("empty-case-0000-0000-0000-000000000001") is False
    assert case["id"] == CASE_ID


def test_try_process_routes_confirmation_not_generic_question(temp_db: Path):
    case = _seed_case(temp_db)
    email_question = {
        "from": "Mario <mario@example.com>",
        "subject": f"Re: {make_initial_subject(CASE_ID, 'Mario')}",
        "body": "Avete anche spessore 3 cm?",
        "message_id": "<q1@client.com>",
        "in_reply_to": "<offer@nstone.local>",
        "references": "<offer@nstone.local>",
    }
    assert try_process_quotation_order_confirmation(email_question, case) is False

    email_confirm = {
        **email_question,
        "body": "Confermo l'ordine per 25 mq Carrara come da vostra offerta.",
        "message_id": "<c1@client.com>",
    }
    with patch(
        "modules.quotation_order_confirmation_pipeline.process_quotation_order_confirmation",
        return_value=True,
    ) as proc:
        assert try_process_quotation_order_confirmation(email_confirm, case) is True
        proc.assert_called_once()


@patch("modules.quotation_auto_pipeline.office_may_auto_email", return_value=True)
@patch("modules.email_service.send_threaded_email")
@patch("modules.order_stock_check.check_material_availability")
@patch("modules.gemini_module.analyze_confirmation_with_stock")
def test_full_confirmation_creates_order_and_updates_case(
    mock_gemini,
    mock_stock,
    mock_send,
    _mock_auto,
    temp_db: Path,
    monkeypatch,
):
    from modules.orders_database import find_order_by_quotation_case_id, init_database

    monkeypatch.setattr(
        "modules.orders_database.get_database_path",
        lambda: temp_db,
    )
    init_database()
    case = _seed_case(temp_db)

    mock_stock.return_value = {
        "availability": "available",
        "material": "Carrara",
        "requested_mq": 25.0,
    }
    mock_gemini.return_value = {
        "status": "confirmed",
        "availability": "available",
        "confidence": 0.9,
        "notes": "Cliente conferma",
        "confirmation_email_text": "Grazie, ordine confermato.",
    }
    mock_send.return_value = {
        "sent": True,
        "message_id": "<conf-out@nstone.local>",
        "error": None,
    }

    email_data = {
        "from": "Mario <mario@example.com>",
        "subject": f"Re: {make_initial_subject(CASE_ID, 'Mario')}",
        "body": "Confermo l'ordine per 25 mq Carrara come da offerta.",
        "message_id": "<conf-in@client.com>",
        "in_reply_to": "<offer@nstone.local>",
        "timestamp": "2026-06-01T12:00:00",
    }

    assert process_quotation_order_confirmation(email_data, case) is True

    order = find_order_by_quotation_case_id(CASE_ID)
    assert order is not None
    assert order.get("status") == "CONFIRMED"
    assert order.get("quotation_case_id") == CASE_ID

    updated = ird.get_incoming_request(CASE_ID, db_path=temp_db)
    assert updated is not None
    assert updated.get("stato") == "ORDINE_CONFERMATO"
    assert updated.get("linked_order_id") == order.get("order_id")
    mock_send.assert_called_once()


def test_case_already_confirmed_skips_duplicate(temp_db: Path):
    case = _seed_case(temp_db, stato="ORDINE_CONFERMATO")
    assert case_is_already_confirmed(case) is True

    email_data = {
        "from": "mario@example.com",
        "subject": "Re: test",
        "body": "Confermo ancora",
        "message_id": "<dup@client.com>",
    }
    assert try_process_quotation_order_confirmation(email_data, case) is True


def test_extract_order_fields_prefers_modified_qty(temp_db: Path):
    _seed_case(temp_db)
    history = [
        {"role": "assistant", "content": "Offerta 25 mq Carrara"},
        {"role": "user", "content": "Chiedo info"},
    ]
    case = ird.get_incoming_request(CASE_ID, db_path=temp_db)
    fields = extract_order_fields_from_thread(
        case,
        {"body": "Confermo solo 18 mq invece di 25"},
        history,
    )
    assert fields.get("quantita") == 18.0
