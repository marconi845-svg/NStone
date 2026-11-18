"""Test abbinamento ordine per email di conferma."""
import sqlite3

import pytest

from modules.orders_database import (
    find_order_for_confirmation,
    init_database,
    save_order,
)


@pytest.fixture
def orders_db(tmp_path, monkeypatch):
    db = tmp_path / "nstonellm.db"
    monkeypatch.setattr("modules.orders_database.get_database_path", lambda: db)
    init_database()
    return db


def _insert_order(order_id, client_email, status, product, materiale="Carrara", qty=10):
    save_order(
        {
            "order_id": order_id,
            "client_email": client_email,
            "client": "mario",
            "product": product,
            "materiale": materiale,
            "quantita": qty,
            "status": status,
            "subject": product,
            "email_subject": product,
            "email_body": "test",
            "machine": "non_specificata",
        }
    )


def test_prefers_open_order_over_confirmed(orders_db):
    email = "mario@example.com"
    _insert_order("OLD_CONFIRMED", email, "CONFIRMED", "Ordine vecchio")
    _insert_order("NEW_OPEN", email, "NEW", "Ordine nuovo")

    order = find_order_for_confirmation(email, "Re: Ordine", "confermo")
    assert order is not None
    assert order["order_id"] == "NEW_OPEN"


def test_matches_order_id_in_body(orders_db):
    email = "mario@example.com"
    _insert_order("20260609_000826_marconi846", email, "NEW", "Botticino")
    _insert_order("NEW_OPEN", email, "NEW", "Ordine generico")

    order = find_order_for_confirmation(
        email,
        "Conferma",
        "Confermo ordine #20260609_000826_marconi846",
    )
    assert order["order_id"] == "20260609_000826_marconi846"


def test_message_id_dedup(orders_db):
    from modules.orders_database import email_log_exists_for_message_id, save_email_log

    save_email_log(
        "a@b.it", "subj", "body", "2026-01-01T00:00:00",
        "CONFERMA", 0.9, message_id="<abc123@test>",
    )
    assert email_log_exists_for_message_id("<abc123@test>") is True
    assert email_log_exists_for_message_id("<other>") is False
