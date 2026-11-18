"""Invia email ordine di test e verifica poll IMAP + salvataggio DB."""
import logging
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from core.machine_plc_config import load_config
from modules.email_service import reload_gmail_credentials, send_response_email
from modules.orders_database import get_database_path, init_database
# check_gmail_orders processa TUTTE le UNSEEN (lento con backlog) — usiamo poll mirato


def main() -> int:
    reload_gmail_credentials()
    cfg = load_config()
    to_addr = (cfg.get("gmail") or {}).get("email", "").strip()
    if not to_addr:
        print("ERRORE: gmail.email mancante in config.json")
        return 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    subject = f"ORDINE TEST NSTONELLM {ts} - lastre marmo"
    body = (
        "Test automatico pipeline ordini NSTONELLM.\n\n"
        "Richiesta ordine:\n"
        "- Materiale: marmo Carrara\n"
        "- Quantita: 12 mq\n"
        "- Spessore: 2 cm\n"
        "- Cliente test: Marco Test\n"
    )

    print(f"Invio SMTP a: {to_addr}")
    print(f"Oggetto: {subject}")
    if not send_response_email(to_addr, subject, body):
        print("ERRORE: invio SMTP fallito")
        return 1

    print("Attesa 12s propagazione Gmail...")
    time.sleep(12)

    init_database()
    import subprocess

    poll = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "test_order_email_poll_one.py")],
        cwd=str(ROOT),
        capture_output=False,
    )
    if poll.returncode != 0:
        print("Poll mirato fallito, exit", poll.returncode)
        return poll.returncode or 3

    db = get_database_path()
    conn = sqlite3.connect(str(db))
    orders = conn.execute(
        """
        SELECT order_id, client_email, status, email_subject
        FROM orders
        WHERE email_subject LIKE ?
        ORDER BY id DESC LIMIT 5
        """,
        (f"%ORDINE TEST NSTONELLM {ts}%",),
    ).fetchall()
    logs = conn.execute(
        """
        SELECT id, tipo_email, subject
        FROM email_logs
        WHERE subject LIKE ?
        ORDER BY id DESC LIMIT 5
        """,
        (f"%ORDINE TEST NSTONELLM {ts}%",),
    ).fetchall()
    conn.close()

    print("email_logs:", logs)
    print("orders:", orders)

    if orders:
        print("OK: ordine salvato in database")
        return 0
    if logs and any(row[1] == "ORDINE" for row in logs):
        print("PARZIALE: classificato ORDINE ma non in tabella orders (vedi log)")
        return 2
    print("FALLITO: nessun record trovato per questa email")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
