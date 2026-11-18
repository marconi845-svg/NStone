from pathlib import Path

import pytest

from modules import incoming_requests_db as ird
from modules import quotation_email_db as qdb
from modules.quotation_email_thread import (
    case_token,
    extract_token8,
    make_initial_subject,
    resolve_quotation_case,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "nstonellm.db"
    ird.set_database_path(db)
    ird.ensure_incoming_request_table(db_path=db)
    qdb.ensure_quotation_email_tables(db_path=db)
    yield db
    ird.set_database_path(None)


def test_case_token_and_subject():
    case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert case_token(case_id) == "[NS-Q-a1b2c3d4]"
    subject = make_initial_subject(case_id, "Mario")
    assert "[NS-Q-a1b2c3d4]" in subject
    assert extract_token8(subject) == "a1b2c3d4"


def test_resolve_by_token_and_message_id(temp_db: Path):
    case_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    ird.insert_incoming_request(
        {
            "id": case_id,
            "timestamp": "2026-01-01T10:00:00",
            "nome": "Mario",
            "email": "mario@example.com",
            "messaggio": "Vorrei Carrara 100mq",
            "stato": "OFFERTA_INVIATA",
        },
        db_path=temp_db,
    )
    ird.update_incoming_request(
        case_id,
        {"email_inviata": True, "data_invio_email": "2026-01-01T11:00:00"},
        db_path=temp_db,
    )

    outbound_mid = "<outbound-test@nstone.local>"
    qdb.insert_turn(
        case_id=case_id,
        direction="outbound",
        body="Offerta inviata",
        subject=make_initial_subject(case_id, "Mario"),
        message_id=outbound_mid,
        db_path=temp_db,
    )

    by_token = resolve_quotation_case(
        {
            "from": "Mario <mario@example.com>",
            "subject": f"Re: {make_initial_subject(case_id, 'Mario')}",
            "body": "Ok per 80mq, disponibile?",
            "message_id": "<client-reply@example.com>",
            "in_reply_to": "",
            "references": "",
        }
    )
    assert by_token is not None
    assert by_token["id"] == case_id

    by_ref = resolve_quotation_case(
        {
            "from": "mario@example.com",
            "subject": "Re: altro oggetto",
            "body": "Seguito",
            "message_id": "<client2@example.com>",
            "in_reply_to": outbound_mid,
            "references": outbound_mid,
        }
    )
    assert by_ref is not None
    assert by_ref["id"] == case_id


def test_turn_dedup_message_id(temp_db: Path):
    mid = "<dup@example.com>"
    qdb.insert_turn(
        case_id="case-1",
        direction="inbound",
        body="x",
        message_id=mid,
        db_path=temp_db,
    )
    assert qdb.turn_exists_by_message_id(mid, db_path=temp_db)
