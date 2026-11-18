"""Tests for sent confirmation orders SQLite helpers."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from modules.orders_database import (
    get_sent_confirmation_fingerprint,
    list_sent_confirmation_orders,
    update_order_confirmation_result,
)


def test_list_sent_confirmation_orders_empty(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(
        "modules.orders_database.get_database_path",
        lambda: db,
    )
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL UNIQUE,
            client TEXT NOT NULL,
            client_email TEXT NOT NULL,
            product TEXT NOT NULL,
            status TEXT NOT NULL,
            validation_errors TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()

    assert list_sent_confirmation_orders() == []
    assert get_sent_confirmation_fingerprint() == "0"


def test_list_sent_confirmation_orders_with_email(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(
        "modules.orders_database.get_database_path",
        lambda: db,
    )
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL UNIQUE,
            client TEXT NOT NULL,
            client_email TEXT NOT NULL,
            product TEXT NOT NULL,
            status TEXT NOT NULL,
            validation_errors TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO orders (order_id, client, client_email, product, status)
        VALUES ('ORD-1', 'Acme', 'buyer@test.com', 'Marble slab', 'CONFIRMED')
        """
    )
    conn.commit()
    conn.close()

    update_order_confirmation_result(
        "ORD-1",
        "CONFIRMED",
        confirmation_email={
            "sent": True,
            "to": "buyer@test.com",
            "subject": "Confirmation",
            "body": "OK",
            "timestamp": "2026-06-03T10:00:00",
        },
    )

    rows = list_sent_confirmation_orders()
    assert len(rows) == 1
    assert rows[0]["order_id"] == "ORD-1"
    assert rows[0]["client"] == "buyer@test.com"
    assert get_sent_confirmation_fingerprint().startswith("1:")
