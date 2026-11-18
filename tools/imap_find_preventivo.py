"""Diagnostic: find richiesta preventivo emails on Gmail."""
import imaplib
import email
from datetime import datetime, timedelta

from modules.orders_imap_service import load_gmail_credentials, parse_email_message

addr, pw = load_gmail_credentials()
mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
mail.login(addr, pw)
mail.select("INBOX")
since = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
criteria = [
    'SUBJECT "richiesta preventivo"',
    f'SUBJECT "preventivo" SINCE {since}',
    f'TEXT "Botticino" SINCE {since}',
]
for crit in criteria:
    st, data = mail.search(None, crit)
    ids = data[0].split() if st == "OK" and data[0] else []
    print(crit, "->", len(ids))
    for eid in ids[-3:]:
        st2, raw = mail.fetch(eid, "(RFC822 FLAGS)")
        flags = raw[0][0].decode(errors="replace") if raw and raw[0] else ""
        msg = email.message_from_bytes(raw[0][1])
        p = parse_email_message(msg)
        seen = "\\Seen" in flags
        print(" ", "SEEN" if seen else "UNSEEN", "|", p.get("from", "")[:55])
        print("   subj:", (p.get("subject") or "")[:70])
        print("   body:", (p.get("body") or "")[:90].replace("\n", " "))
mail.logout()
