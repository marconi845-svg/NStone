"""Poll IMAP solo per l'ultima mail di test ORDINE TEST NSTONELLM (evita backlog UNSEEN)."""
import email
import imaplib
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from modules.orders_imap_service import (
    GMAIL_IMAP_HOST,
    GMAIL_IMAP_PORT,
    load_gmail_credentials,
    parse_email_message,
    process_order_email,
)
from modules.orders_database import init_database
import sqlite3
from modules.orders_database import get_database_path

MARKER = "ORDINE TEST NSTONELLM"


def main() -> int:
    init_database()
    email_addr, app_password = load_gmail_credentials()
    if not email_addr or not app_password:
        print("Credenziali Gmail mancanti")
        return 1

    mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
    mail.login(email_addr, app_password)
    mail.select("INBOX")

    # Cerca per oggetto (anche già letta, per verifica post-invio)
    status, data = mail.search(None, f'(SUBJECT "{MARKER}")')
    if status != "OK" or not data[0]:
        print("Nessuna mail trovata con marker test")
        mail.logout()
        return 2

    ids = data[0].split()
    target = ids[-1]
    print(f"Processo UID {target.decode()} ({len(ids)} match totali)")

    status, msg_data = mail.fetch(target, "(RFC822)")
    if status != "OK":
        print("Fetch fallito")
        mail.logout()
        return 3

    msg = email.message_from_bytes(msg_data[0][1])
    email_data = parse_email_message(msg)
    if not email_data:
        print("Parse fallito")
        mail.logout()
        return 4

    print("From:", email_data.get("from"))
    print("Subject:", email_data.get("subject"))
    ok = process_order_email(email_data)
    print("process_order_email:", ok)

    try:
        mail.store(target, "+FLAGS", "\\Seen")
    except Exception:
        pass
    mail.logout()

    subj = email_data.get("subject", "")
    conn = sqlite3.connect(str(get_database_path()))
    logs = conn.execute(
        "SELECT id, tipo_email, subject FROM email_logs WHERE subject = ? ORDER BY id DESC LIMIT 1",
        (subj,),
    ).fetchall()
    orders = conn.execute(
        "SELECT order_id, status FROM orders WHERE email_subject = ? ORDER BY id DESC LIMIT 1",
        (subj,),
    ).fetchall()
    conn.close()
    print("email_log:", logs)
    print("order:", orders)
    return 0 if orders else (2 if logs else 3)


if __name__ == "__main__":
    raise SystemExit(main())
