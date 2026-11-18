"""Solo invio SMTP mail ordine di test."""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.machine_plc_config import load_config
from modules.email_service import reload_gmail_credentials, send_response_email

MARKER = "ORDINE TEST NSTONELLM"


def main() -> int:
    reload_gmail_credentials()
    to_addr = (load_config().get("gmail") or {}).get("email", "").strip()
    if not to_addr:
        print("gmail.email mancante")
        return 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    subject = f"{MARKER} {ts} - lastre marmo"
    body = (
        "Test pipeline ordini.\n"
        "Richiesta ordine lastre marmo Carrara, quantita 12 mq, spessore 2 cm.\n"
    )
    print("SUBJECT:", subject)
    return 0 if send_response_email(to_addr, subject, body) else 1


if __name__ == "__main__":
    raise SystemExit(main())
