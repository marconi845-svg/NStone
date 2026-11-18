"""
Servizio per l'invio email tramite SMTP Gmail
"""
print(">>> MODULO EMAIL GMAIL CARICATO <<<")
import smtplib
import logging
import json
import uuid
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, Dict, Any, List, Union
from datetime import datetime

logger = logging.getLogger(__name__)

# Configurazione Gmail SMTP
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
GMAIL_SMTP_SSL_PORT = 465

def _load_gmail_credentials() -> tuple[str, str]:
    """
    Carica credenziali Gmail da config.json canonico (machine_plc_config).
    """
    try:
        from core.machine_plc_config import load_config, get_config_path

        config = load_config()
        gmail_config = config.get("gmail") if isinstance(config.get("gmail"), dict) else {}
        email = (gmail_config.get("email") or "").strip()
        app_password = (gmail_config.get("app_password") or "").strip()

        if email and app_password:
            logger.info("Credenziali Gmail caricate da %s", get_config_path())
            return email, app_password

        logger.warning(
            "Credenziali Gmail non configurate in %s — "
            "Impostazioni → sezione Invio risposte Gmail (App Password).",
            get_config_path(),
        )
    except Exception as e:
        logger.error("Errore caricamento credenziali Gmail: %s", e)

    return "", ""


def reload_gmail_credentials() -> bool:
    """Ricarica credenziali dopo salvataggio Impostazioni."""
    global GMAIL_EMAIL, GMAIL_APP_PASSWORD
    GMAIL_EMAIL, GMAIL_APP_PASSWORD = _load_gmail_credentials()
    return bool(GMAIL_EMAIL and GMAIL_APP_PASSWORD)

# Carica credenziali all'avvio (non blocca se non configurate)
GMAIL_EMAIL, GMAIL_APP_PASSWORD = _load_gmail_credentials()


def _get_smtp_credentials() -> tuple[str, str]:
    email = GMAIL_EMAIL
    app_password = GMAIL_APP_PASSWORD
    if not email or not app_password:
        reload_gmail_credentials()
        email, app_password = GMAIL_EMAIL, GMAIL_APP_PASSWORD
    return email, app_password


def _smtp_send_starttls(msg: MIMEMultipart, to_email: str) -> bool:
    email, app_password = _get_smtp_credentials()
    if not email or not app_password:
        logger.error("Credenziali Gmail non configurate. Impossibile inviare email.")
        return False

    server = None
    try:
        server = smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT)
        server.set_debuglevel(0)
        server.starttls()
        server.login(email, app_password)
        server.send_message(msg)
        return True
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception as exc:
                logger.warning("Errore chiusura SMTP: %s", exc)


def _attach_files(msg: MIMEMultipart, attachments: Optional[List[Union[str, Dict[str, Any]]]]) -> None:
    """Allega file locali al messaggio MIME (es. PDF conferma ordine)."""
    if not attachments:
        return
    for item in attachments:
        path_str = ""
        filename = ""
        if isinstance(item, dict):
            path_str = str(item.get("path") or "").strip()
            filename = str(item.get("filename") or "").strip()
        else:
            path_str = str(item or "").strip()
        if not path_str:
            continue
        path = Path(path_str)
        if not path.is_file():
            logger.warning("Allegato non trovato, skip: %s", path)
            continue
        fn = filename or path.name
        with open(path, "rb") as handle:
            payload = handle.read()
        part = MIMEBase("application", "pdf")
        part.set_payload(payload)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{fn}"')
        msg.attach(part)
        logger.info("Allegato email: %s", fn)


def send_threaded_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    message_id: Optional[str] = None,
    attachments: Optional[List[Union[str, Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Invia email con header di threading RFC (Message-ID, In-Reply-To, References)."""
    email, app_password = _get_smtp_credentials()
    if not email or not app_password:
        return {
            "sent": False,
            "error": "Credenziali Gmail non configurate",
            "to": to_email,
            "subject": subject,
            "body": body,
            "message_id": message_id,
        }

    mid = message_id or f"<{uuid.uuid4()}@nstone.local>"
    if not mid.startswith("<"):
        mid = f"<{mid}>"

    msg = MIMEMultipart()
    msg["From"] = email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Message-ID"] = mid
    if in_reply_to:
        irt = in_reply_to if in_reply_to.startswith("<") else f"<{in_reply_to}>"
        msg["In-Reply-To"] = irt
    if references:
        msg["References"] = references
    msg.attach(MIMEText(body, "plain", "utf-8"))
    _attach_files(msg, attachments)

    attachment_names = []
    if attachments:
        for item in attachments:
            if isinstance(item, dict):
                attachment_names.append(item.get("filename") or Path(str(item.get("path") or "")).name)
            else:
                attachment_names.append(Path(str(item)).name)

    try:
        logger.info("Invio email threaded a %s — oggetto: %s", to_email, subject[:80])
        sent = _smtp_send_starttls(msg, to_email)
        return {
            "sent": sent,
            "to": to_email,
            "subject": subject,
            "body": body,
            "message_id": mid,
            "timestamp": datetime.now().isoformat(),
            "error": None if sent else "Invio SMTP fallito",
            "attachments": attachment_names,
        }
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("Errore autenticazione SMTP: %s", exc)
        return {
            "sent": False,
            "to": to_email,
            "subject": subject,
            "body": body,
            "message_id": mid,
            "error": str(exc),
        }
    except Exception as exc:
        logger.error("Errore invio threaded: %s", exc)
        return {
            "sent": False,
            "to": to_email,
            "subject": subject,
            "body": body,
            "message_id": mid,
            "error": str(exc),
        }


def send_response_email(to_email: str, subject: str, body: str) -> bool:
    """
    Invia un'email tramite SMTP Gmail
    
    Args:
        to_email: Indirizzo email del destinatario
        subject: Oggetto dell'email
        body: Corpo dell'email (testo semplice)
        
    Returns:
        True se l'invio è riuscito, False altrimenti
    """
    try:
        logger.info("Tentativo invio email a %s", to_email)
        msg = MIMEMultipart()
        email, _ = _get_smtp_credentials()
        if not email:
            logger.error("Credenziali Gmail non configurate.")
            return False
        msg["From"] = email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        return _smtp_send_starttls(msg, to_email)
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Errore di autenticazione: {e}")
        logger.error(f"Possibili cause:")
        logger.error(f"  - App Password errata o non configurata")
        logger.error(f"  - Verifica 2-Step non abilitata per questo account Google")
        logger.error(f"  - Email mittente errata: {email}")
        logger.error(f"  - App Password scaduta o revocata")
        logger.error(f"  - Per generare una nuova App Password: https://myaccount.google.com/apppasswords")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return False
        
    except smtplib.SMTPServerDisconnected as e:
        logger.error(f"Errore di connessione: Server SMTP disconnesso - {e}")
        logger.error(f"Possibili cause:")
        logger.error(f"  - Problemi di rete")
        logger.error(f"  - Server SMTP non raggiungibile: {GMAIL_SMTP_HOST}:{GMAIL_SMTP_PORT}")
        logger.error(f"  - Timeout di connessione")
        logger.error(f"  - Firewall o proxy che blocca la connessione")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return False
        
    except smtplib.SMTPException as e:
        logger.error(f"Errore SMTP: {e}")
        logger.error(f"Tipo di errore SMTP non specifico")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return False
        
    except Exception as e:
        logger.error(f"Errore generico: {e}")
        logger.error(f"Errore inaspettato durante l'invio email")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return False


def send_order_confirmation_email(
    to_email: str,
    order_data: Dict,
    confirmation_text: str = "",
    *,
    attachments: Optional[List[Union[str, Dict[str, Any]]]] = None,
) -> Optional[Dict]:
    """
    Invia un'email di conferma ordine tramite SMTP Gmail (SSL)
    
    Args:
        to_email: Indirizzo email del destinatario
        order_data: Dizionario con i dati dell'ordine:
            - id: ID dell'ordine
            - from: Email del cliente
            - subject: Oggetto dell'ordine originale
            - body: Corpo dell'ordine originale
            - timestamp: Timestamp dell'ordine
            - status: Stato dell'ordine
        confirmation_text: Testo della conferma generato da Gemini. Se vuoto, usa template di fallback
        
    Returns:
        Dizionario con informazioni sull'email inviata:
        {
            "sent": True/False,
            "timestamp": "...",
            "subject": "...",
            "body": "...",
            "to": to_email
        }
        Oppure None in caso di errore critico
    """
    server = None
    try:
        # Carica credenziali
        email, app_password = _load_gmail_credentials()
        
        # Estrai dati ordine
        order_id = order_data.get("id", "UNKNOWN")
        client_name = order_data.get("from", "").split("@")[0]  # Nome dal dominio email
        product = order_data.get("subject", "Prodotto non specificato")
        notes = order_data.get("notes", "")
        
        # Costruisci subject
        subject = f"Conferma Ordine #{order_id}"
        
        # Costruisci body
        if confirmation_text and confirmation_text.strip():
            body = confirmation_text
        else:
            # Template di fallback
            body = f"""Ciao {client_name},

ti confermo che il tuo ordine #{order_id} è stato registrato correttamente.

Dettagli:
- Prodotto: {product}
- Note: {notes}

Procediamo come concordato.

Cordiali saluti,
NStone"""
        
        logger.info(f"Tentativo invio email di conferma ordine #{order_id} a {to_email} da {email}")
        
        # Crea il messaggio MIME
        msg = MIMEMultipart()
        msg['From'] = email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Aggiungi il corpo del messaggio
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        _attach_files(msg, attachments)

        attachment_names = []
        if attachments:
            for item in attachments:
                if isinstance(item, dict):
                    attachment_names.append(item.get("filename") or Path(str(item.get("path") or "")).name)
                else:
                    attachment_names.append(Path(str(item)).name)
        
        logger.info(f"Connessione a {GMAIL_SMTP_HOST}:{GMAIL_SMTP_SSL_PORT} (SSL)...")
        
        # Connetti al server SMTP con SSL
        server = smtplib.SMTP_SSL(GMAIL_SMTP_HOST, GMAIL_SMTP_SSL_PORT)
        server.set_debuglevel(0)
        
        logger.info("Login SMTP in corso...")
        server.login(email, app_password)
        logger.info("Login completato con successo")
        
        logger.info(f"Invio email di conferma ordine a {to_email}...")
        server.send_message(msg)
        logger.info("Invio email completato")
        
        # Costruisci il dizionario di risposta
        timestamp = datetime.now().isoformat()
        result = {
            "sent": True,
            "timestamp": timestamp,
            "subject": subject,
            "body": body,
            "to": to_email,
            "attachments": attachment_names,
        }
        
        return result
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Errore di autenticazione: {e}")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return {
            "sent": False,
            "timestamp": datetime.now().isoformat(),
            "subject": subject if 'subject' in locals() else "",
            "body": body if 'body' in locals() else "",
            "to": to_email,
            "error": str(e)
        }
        
    except smtplib.SMTPServerDisconnected as e:
        logger.error(f"Errore di connessione: Server SMTP disconnesso - {e}")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return {
            "sent": False,
            "timestamp": datetime.now().isoformat(),
            "subject": subject if 'subject' in locals() else "",
            "body": body if 'body' in locals() else "",
            "to": to_email,
            "error": str(e)
        }
        
    except smtplib.SMTPException as e:
        logger.error(f"Errore SMTP: {e}")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return {
            "sent": False,
            "timestamp": datetime.now().isoformat(),
            "subject": subject if 'subject' in locals() else "",
            "body": body if 'body' in locals() else "",
            "to": to_email,
            "error": str(e)
        }
        
    except Exception as e:
        logger.error(f"Errore generico: {e}")
        import traceback
        logger.error(f"Traceback completo:\n{traceback.format_exc()}")
        return {
            "sent": False,
            "timestamp": datetime.now().isoformat(),
            "subject": subject if 'subject' in locals() else "",
            "body": body if 'body' in locals() else "",
            "to": to_email,
            "error": str(e)
        }
        
    finally:
        # Assicura che la connessione SMTP venga sempre chiusa correttamente
        if server is not None:
            try:
                logger.info("Chiusura connessione SMTP...")
                server.quit()
                logger.info("Connessione SMTP chiusa correttamente")
            except Exception as e:
                logger.warning(f"Errore durante la chiusura della connessione SMTP: {e}")
