"""Test filtro tabella ordini e gate persistenza."""
from modules.orders_database import orders_table_visibility_sql, should_persist_incoming_order


def test_visibility_excludes_preventivo_only():
    sql = orders_table_visibility_sql().lower()
    assert "preventivo" not in sql
    assert "richiesta" not in sql
    assert "ordine" in sql or "quotation_case_id" in sql


def test_should_not_persist_preventivo_thread():
    assert should_persist_incoming_order(
        "Re: Richiesta preventivo marmo Carrara",
        "Vorrei un preventivo per 50 mq",
    ) is False


def test_should_persist_explicit_order():
    assert should_persist_incoming_order(
        "Ordine Botticino",
        "Confermo 100 mq lastre",
    ) is True


def test_should_persist_ns_q_with_conferma():
    assert should_persist_incoming_order(
        "Re: NS-Q-12345678",
        "Confermo l ordine come da offerta",
    ) is True


def test_order_visible_in_table_excludes_job_alerts():
    from modules.orders_database import order_visible_in_orders_table

    assert order_visible_in_orders_table(
        email_subject="4 offerte di lavoro per marmo",
        status="NEW",
    ) is False


def test_should_not_persist_amazon_order_notification():
    assert should_persist_incoming_order(
        "Il tuo ordine Amazon.it",
        "La spedizione è in arrivo",
        "order-update@amazon.it",
    ) is False


def test_order_visible_excludes_amazon():
    from modules.orders_database import order_visible_in_orders_table

    assert order_visible_in_orders_table(
        email_subject="Consegna effettuata: Il tuo ordine Amazon.it #123",
        client_email="order-update@amazon.it",
        status="NEW",
    ) is False


def test_order_visible_in_table_includes_ordine():
    from modules.orders_database import order_visible_in_orders_table

    assert order_visible_in_orders_table(
        email_subject="Ordine Botticino",
        status="NEW",
    ) is True


def test_imap_fully_processed_ordine_without_db_row():
    from modules.orders_database import imap_message_fully_processed

    assert imap_message_fully_processed("nonexistent-msg-id-xyz") is False


def test_backfill_creates_order_from_email_log(tmp_path, monkeypatch):
    import sqlite3
    from modules import orders_database as odb

    db = tmp_path / "test.db"
    monkeypatch.setattr(odb, "get_database_path", lambda: db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE email_logs (
            id INTEGER PRIMARY KEY, sender TEXT, subject TEXT, body TEXT,
            timestamp TEXT, tipo_email TEXT, confidence REAL, order_id TEXT, message_id TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT UNIQUE, email_id INTEGER,
            client TEXT, client_email TEXT, product TEXT, materiale TEXT, quantita REAL,
            machine TEXT, status TEXT, email_subject TEXT, email_body TEXT,
            validation_errors TEXT, quotation_case_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "INSERT INTO email_logs (sender, subject, body, timestamp, tipo_email, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test@example.com", "Ordine marmo", "body", "2026-06-09T10:00:00", "ORDINE", 0.9),
    )
    conn.commit()
    conn.close()

    n = odb.backfill_orders_from_email_logs(limit=10)
    assert n == 1
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
    conn.close()
