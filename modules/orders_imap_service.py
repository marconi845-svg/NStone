"""
Servizio IMAP per la gestione degli ordini via email Gmail
Legge email, classifica ordini e conferme, processa con Gemini, invia conferme
"""
import imaplib
import email
import json
import logging
import re
import threading
from email.utils import parseaddr
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sys

# Aggiungi la root del progetto al path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

try:
    from modules.gemini_module import analyze_order_confirmation
    from modules.email_service import send_order_confirmation_email
    from modules.email_classifier import classify_email
    from modules.orders_database import (
        init_database, save_email_log, save_order,
        validate_order, get_orders_by_status, email_already_logged,
    )
except ImportError as e:
    print(f"Warning: Impossibile importare moduli: {e}")
    analyze_order_confirmation = None
    send_order_confirmation_email = None
    classify_email = None
    init_database = None
    save_email_log = None
    save_order = None
    email_already_logged = None

logger = logging.getLogger(__name__)

_imap_poll_lock = threading.Lock()

# Configurazione Gmail IMAP
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993


def load_gmail_credentials() -> Tuple[str, str]:
    """Carica credenziali Gmail dal config.json canonico."""
    try:
        from core.machine_plc_config import load_config

        gmail_config = load_config().get("gmail") or {}
        if not isinstance(gmail_config, dict):
            gmail_config = {}
        email = (gmail_config.get("email") or "").strip()
        app_password = (gmail_config.get("app_password") or "").strip().replace(" ", "")
        if email and app_password:
            return email, app_password
        logger.warning("Credenziali Gmail non trovate in config.json (sezione gmail)")
    except Exception as e:
        logger.error("Errore nel caricamento credenziali Gmail: %s", e)
    return "", ""


def get_orders_imap_settings() -> Dict:
    """Impostazioni polling ordini da config.json."""
    try:
        from core.machine_plc_config import load_config

        orders_cfg = load_config().get("orders") or {}
        if not isinstance(orders_cfg, dict):
            orders_cfg = {}
    except Exception:
        orders_cfg = {}
    poll = orders_cfg.get("gmail_poll_seconds", 90)
    try:
        poll = max(60, int(poll))
    except (TypeError, ValueError):
        poll = 90
    use_ai = bool(orders_cfg.get("use_ai_on_poll", False))
    imap_mode = str(orders_cfg.get("imap_mode", "poll")).strip().lower()
    if imap_mode not in ("poll", "idle"):
        imap_mode = "poll"
    keywords = orders_cfg.get("subject_keywords")
    if not isinstance(keywords, list) or not keywords:
        keywords = list(DEFAULT_SUBJECT_KEYWORDS)
    max_poll = orders_cfg.get("imap_max_per_poll", 5)
    try:
        max_poll = max(1, min(100, int(max_poll)))
    except (TypeError, ValueError):
        max_poll = 5
    max_llm = orders_cfg.get("imap_max_llm_per_poll", 1)
    try:
        max_llm = max(0, min(10, int(max_llm)))
    except (TypeError, ValueError):
        max_llm = 1
    table_max = orders_cfg.get("orders_table_max_rows", 5)
    try:
        table_max = max(1, min(50, int(table_max)))
    except (TypeError, ValueError):
        table_max = 5
    recent_days = orders_cfg.get("imap_recent_days", 5)
    try:
        recent_days = max(1, min(14, int(recent_days)))
    except (TypeError, ValueError):
        recent_days = 5
    return {
        "gmail_poll_seconds": poll,
        "use_ai_on_poll": use_ai,
        "imap_mode": imap_mode,
        "imap_filter_enabled": bool(orders_cfg.get("imap_filter_enabled", True)),
        "imap_body_keywords": bool(orders_cfg.get("imap_body_keywords", True)),
        "imap_fetch_recent_seen": bool(orders_cfg.get("imap_fetch_recent_seen", False)),
        "imap_recent_days": recent_days,
        "subject_keywords": [str(k).strip() for k in keywords if str(k).strip()],
        "imap_max_per_poll": max_poll,
        "imap_max_llm_per_poll": max_llm,
        "orders_table_max_rows": table_max,
        "confirmation_use_llm_on_poll": bool(
            orders_cfg.get("confirmation_use_llm_on_poll", True)
        ),
        "imap_poll_unseen_only": bool(orders_cfg.get("imap_poll_unseen_only", True)),
        "imap_auto_start": bool(orders_cfg.get("imap_auto_start", True)),
        "show_all_in_table": bool(orders_cfg.get("show_all_in_table", False)),
        "use_ai_on_confirmation": bool(orders_cfg.get("use_ai_on_confirmation", True)),
    }


from modules.pipeline_keywords import (
    DEFAULT_SUBJECT_KEYWORDS,
    ORDER_IMAP_BODY_KEYWORDS as _ORDER_IMAP_BODY_KW,
    ORDER_IMAP_EXTRA_SUBJECT_KEYWORDS as _ORDER_IMAP_EXTRA_KW,
    QUOTATION_IMAP_BODY_KEYWORDS as _QUOTATION_IMAP_BODY_KW,
    QUOTATION_IMAP_SUBJECT_KEYWORDS as _QUOTATION_IMAP_SUBJECT_KW,
    is_confirmation_hint,
)

_SPAM_SENDER_DOMAINS = (
    "indeed.com",
    "linkedin.com",
    "infojobs.net",
    "monster.com",
    "glassdoor.com",
    "stepstone.",
    "jobalert",
    "jobs.",
)
_JOB_OFFER_PHRASES = (
    "offerta di lavoro",
    "offerte di lavoro",
    "job offer",
    "nuova offerta di lavoro",
    "nuove offerte",
    "candidatura",
    "posizione aperta",
    "annuncio di lavoro",
)


def _nested_or_imap(clauses: List[str]) -> str:
    if len(clauses) == 1:
        return clauses[0]
    return f"(OR {clauses[0]} {_nested_or_imap(clauses[1:])})"


def format_imap_filter_summary(settings: Optional[Dict] = None) -> str:
    """Riepilogo leggibile per UI (evita stringa IMAP troncata su «preventivo»)."""
    settings = settings or get_orders_imap_settings()
    days = int(settings.get("imap_recent_days") or 5)
    parts = [
        "ordine",
        "conferma/confermo",
        "preventivo/richiesta",
        "NS-Q/NStone",
    ]
    extra = settings.get("subject_keywords") or []
    for kw in extra[:4]:
        k = str(kw).strip().lower()
        if k and k not in {"ordine", "order", "preventivo", "richiesta", "confermo", "conferma"}:
            parts.append(k)
    return f"UNSEEN: ordine, conferma, preventivo, NS-Q · {days} gg · max {settings.get('imap_max_per_poll', 5)}" + (
        " · thread NS-Q letti" if settings.get("imap_fetch_recent_seen", True) else ""
    )


def get_orders_table_max_rows() -> int:
    """Righe massime in tabella Ordini Ricevuti (default 5)."""
    try:
        return int(get_orders_imap_settings().get("orders_table_max_rows") or 5)
    except (TypeError, ValueError):
        return 5


def _unseen_uid_set(mail: imaplib.IMAP4_SSL) -> set[bytes]:
    """Set UID non letti — una sola SEARCH UNSEEN (no fetch per messaggio, thread-safe)."""
    try:
        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return set()
        return {eid for eid in data[0].split() if eid}
    except Exception as exc:
        logger.warning("IMAP SEARCH UNSEEN fallita: %s", exc)
        return set()


def pick_newest_unseen_uid(
    email_ids: List[bytes],
    unseen_uids: Optional[set[bytes]] = None,
    *,
    mail: Optional[imaplib.IMAP4_SSL] = None,
) -> Optional[bytes]:
    """UID della mail non letta più recente (senza fetch aggiuntivi se unseen_uids noto)."""
    pool = unseen_uids if unseen_uids is not None else (
        _unseen_uid_set(mail) if mail is not None else set()
    )
    if not pool:
        return None
    for eid in email_ids:
        if eid in pool:
            return eid
    return None


def _build_unseen_keyword_criteria(settings: Dict, since: str) -> str:
    unseen_clauses: List[str] = []
    for kw in _QUOTATION_IMAP_SUBJECT_KW:
        unseen_clauses.append(f'SUBJECT "{kw}"')
    if settings.get("imap_body_keywords", True):
        for kw in _QUOTATION_IMAP_BODY_KW:
            unseen_clauses.append(f'TEXT "{kw}"')
        for kw in _ORDER_IMAP_BODY_KW:
            unseen_clauses.append(f'TEXT "{kw}"')
    for kw in _ORDER_IMAP_EXTRA_KW:
        unseen_clauses.append(f'SUBJECT "{kw}"')
    if not unseen_clauses:
        unseen_clauses.append('SUBJECT "ordine"')
    return f"(UNSEEN (SINCE {since} {_nested_or_imap(unseen_clauses)}))"


def build_imap_search_criteria(settings: Optional[Dict] = None) -> str:
    """
    Mai tutta la inbox UNSEEN: solo keyword preventivo/ordini + finestra recente.
    """
    settings = settings or get_orders_imap_settings()
    days = int(settings.get("imap_recent_days") or 7)
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    clauses: List[str] = []

    for kw in _QUOTATION_IMAP_SUBJECT_KW:
        clauses.append(f'(SINCE {since} SUBJECT "{kw}")')
    if settings.get("imap_body_keywords", True):
        for kw in _QUOTATION_IMAP_BODY_KW:
            clauses.append(f'(SINCE {since} TEXT "{kw}")')
        for kw in _ORDER_IMAP_BODY_KW:
            clauses.append(f'(SINCE {since} TEXT "{kw}")')
    for kw in _ORDER_IMAP_EXTRA_KW:
        clauses.append(f'(SINCE {since} SUBJECT "{kw}")')
    for kw in settings.get("subject_keywords", [])[:8]:
        kw = str(kw).strip()
        if kw and kw.lower() not in {k.lower() for k in _QUOTATION_IMAP_SUBJECT_KW}:
            clauses.append(f'(SINCE {since} SUBJECT "{kw}")')

    if not clauses:
        clauses.append(f'(SINCE {since} SUBJECT "preventivo")')
    return _nested_or_imap(clauses)


def build_imap_search_criteria_list(settings: Optional[Dict] = None) -> List[str]:
    """
    Criteri IMAP: di default solo UNSEEN (no re-poll mail già lette).
    Opzionale recupero thread NS-Q/NStone già letti (dedupe su Message-ID).
    """
    settings = settings or get_orders_imap_settings()
    days = int(settings.get("imap_recent_days") or 7)
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    criteria: List[str] = [_build_unseen_keyword_criteria(settings, since)]

    unseen_only = bool(settings.get("imap_poll_unseen_only", True))
    if not unseen_only:
        legacy = build_imap_search_criteria(settings)
        if legacy not in criteria:
            criteria.append(legacy)

  # Mail già lette: solo thread NS-Q/NStone (mai SUBJECT "ordine" — pesca Amazon/spam)
    if settings.get("imap_fetch_recent_seen", False):
        for crit in (
            f'(SINCE {since} SUBJECT "NS-Q")',
            f'(SINCE {since} SUBJECT "NStone")',
        ):
            if crit not in criteria:
                criteria.append(crit)

    return criteria


def is_commercial_spam_email(email_data: Dict) -> bool:
    """Indeed, job alert, Amazon, newsletter — non preventivi/ordini NStone."""
    from modules.order_inbox_noise import is_inbox_noise

    if is_inbox_noise(
        subject=str(email_data.get("subject") or ""),
        body=str(email_data.get("body") or ""),
        sender=str(email_data.get("from") or ""),
    ):
        return True
    from_header = str(email_data.get("from") or "").lower()
    _, addr = parseaddr(from_header)
    sender = (addr or from_header).lower()
    for dom in _SPAM_SENDER_DOMAINS:
        if dom in sender:
            return True
    combined = f"{email_data.get('subject') or ''} {email_data.get('body') or ''}".lower()
    for phrase in _JOB_OFFER_PHRASES:
        if phrase in combined:
            return True
    return False


def imap_message_already_processed(message_id: str) -> bool:
    """True se Message-ID già processato con successo (ordine/conferma persistiti)."""
    mid = (message_id or "").strip()
    if not mid:
        return False
    try:
        from modules.orders_database import imap_message_fully_processed

        if imap_message_fully_processed(mid):
            return True
    except Exception:
        pass
    try:
        from modules.quotation_email_db import turn_exists_by_message_id

        if turn_exists_by_message_id(mid):
            return True
    except Exception:
        pass
    return False


def _log_imap_email(
    email_data: Dict,
    sender: str,
    subject: str,
    body: str,
    timestamp: str,
    tipo_email: str,
    confidence: float,
    order_id: Optional[str] = None,
) -> None:
    if not save_email_log:
        return
    save_email_log(
        sender,
        subject,
        body,
        timestamp,
        tipo_email,
        confidence,
        order_id=order_id,
        message_id=(email_data.get("message_id") or "").strip() or None,
    )


def make_safe_order_id(sender: str) -> str:
    """ID ordine e nome file JSON sicuri (niente caratteri da header email)."""
    _, addr = parseaddr(sender or "")
    local = ""
    if addr and "@" in addr:
        local = addr.split("@", 1)[0]
    elif addr:
        local = addr
    else:
        raw = sender or "client"
        local = raw.split("@", 1)[0] if "@" in raw else raw[:40]
    safe = re.sub(r"[^\w.\-]+", "_", local).strip("._")[:48] or "client"
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}"


def get_logs_dir() -> Path:
    """
    Restituisce il percorso della cartella logs
    
    Returns:
        Path della cartella logs
    """
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


def get_orders_dir() -> Path:
    """
    Restituisce il percorso della cartella orders
    
    Returns:
        Path della cartella orders
    """
    orders_dir = get_logs_dir() / "orders"
    orders_dir.mkdir(exist_ok=True)
    return orders_dir


def save_order_to_json(order_data: Dict) -> bool:
    """
    Salva un ordine in un file JSON
    
    Args:
        order_data: Dizionario con i dati dell'ordine
        
    Returns:
        True se il salvataggio è riuscito, False altrimenti
    """
    try:
        orders_dir = get_orders_dir()
        order_id = order_data.get("id", "unknown")
        order_file = orders_dir / f"order_{order_id}.json"
        
        with open(order_file, 'w', encoding='utf-8') as f:
            json.dump(order_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Ordine {order_id} salvato in {order_file}")
        return True
    except Exception as e:
        logger.error(f"Errore nel salvataggio ordine: {e}")
        return False


def update_last_order_json(order_data: Dict) -> bool:
    """
    Aggiorna il file last_order.json con una versione leggera dell'ordine
    
    Args:
        order_data: Dizionario con i dati dell'ordine
        
    Returns:
        True se l'aggiornamento è riuscito, False altrimenti
    """
    try:
        logs_dir = get_logs_dir()
        last_order_file = logs_dir / "last_order.json"
        
        # Crea versione leggera
        light_order = {
            "id": order_data.get("id", ""),
            "from": order_data.get("from", ""),
            "subject": order_data.get("subject", ""),
            "timestamp": order_data.get("timestamp", ""),
            "status": order_data.get("status", "NEW")
        }
        
        with open(last_order_file, 'w', encoding='utf-8') as f:
            json.dump(light_order, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento last_order.json: {e}")
        return False


def parse_email_message(msg: email.message.Message) -> Optional[Dict]:
    """
    Estrae i dati da un messaggio email
    
    Args:
        msg: Oggetto email.message.Message
        
    Returns:
        Dizionario con i dati dell'email o None in caso di errore
    """
    try:
        # Estrai header
        from_addr = msg.get("From", "")
        subject = msg.get("Subject", "")
        date_str = msg.get("Date", "")
        
        # Estrai body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                body = str(msg.get_payload())
        
        # Converti data
        try:
            date_tuple = email.utils.parsedate_tz(date_str)
            if date_tuple:
                timestamp = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple)).isoformat()
            else:
                timestamp = datetime.now().isoformat()
        except:
            timestamp = datetime.now().isoformat()
        
        message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
        in_reply_to = (msg.get("In-Reply-To") or "").strip()
        references = (msg.get("References") or "").strip()

        return {
            "from": from_addr,
            "subject": subject,
            "body": body,
            "timestamp": timestamp,
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "references": references,
        }
    except Exception as e:
        logger.error(f"Errore nel parsing email: {e}")
        return None


def _sort_email_ids_newest_first(email_ids: List[bytes]) -> List[bytes]:
    """UID IMAP crescenti — le più recenti per ultime."""
    try:
        return sorted(email_ids, key=lambda x: int(x), reverse=True)
    except (TypeError, ValueError):
        return list(reversed(email_ids))


def process_incoming_email(
    email_data: Dict,
    *,
    use_llm: bool = True,
    use_ai: Optional[bool] = None,
) -> Dict:
    """
    Classifica e instrada: ORDINE (salva), CONFERMA (stock + mail NStone), altro (skip).
    """
    out = {"handled": False, "kind": "skip", "saved": False}
    try:
        if init_database:
            init_database()

        sender = email_data.get("from", "")
        subject = email_data.get("subject", "")
        body = email_data.get("body", "")
        timestamp = email_data.get("timestamp", datetime.now().isoformat())
        message_id = (email_data.get("message_id") or "").strip()

        try:
            from modules.orders_pipeline_trace import begin_email_trace, end_email_trace, trace_step
        except ImportError:
            begin_email_trace = end_email_trace = trace_step = lambda *a, **k: None  # type: ignore

        begin_email_trace(subject)

        if message_id:
            try:
                from modules.orders_database import imap_message_fully_processed

                if imap_message_fully_processed(message_id):
                    out["detail"] = "già processata (message-id)"
                    out["handled"] = True
                    trace_step("SKIP", "message-id già completata")
                    end_email_trace(out["detail"])
                    return out
            except Exception:
                pass

        try:
            from modules.quotation_email_thread import extract_token8

            has_ns_q = bool(
                extract_token8(subject) or extract_token8(body)
            )
        except Exception:
            has_ns_q = False

        if not has_ns_q and is_commercial_spam_email(email_data):
            logger.info("Skip email commerciale/spam: %s", subject[:80])
            trace_step("SKIP", "spam/commerciale")
            end_email_trace("spam")
            return out

        imap_settings = get_orders_imap_settings()
        if use_ai is None:
            use_ai = imap_settings.get("use_ai_on_poll", False)
        use_ai_confirm = bool(imap_settings.get("use_ai_on_confirmation", True))
        trace_step("CONFIG", f"classify_ai={use_ai} confirm={use_ai_confirm} llm={use_llm}")

        # Preventivi / risposte thread PRIMA del filtro duplicati ordini
        try:
            from modules.quotation_reply_pipeline import try_process_quotation_reply

            quotation_kind = try_process_quotation_reply(
                email_data, use_llm=use_llm
            )
            if quotation_kind:
                out["kind"] = quotation_kind
                out["detail"] = quotation_kind
                out["handled"] = True
                out["saved"] = True
                trace_step("NS-Q", quotation_kind)
                if save_email_log:
                    log_tipo = (
                        "CONFERMA_PREVENTIVO"
                        if quotation_kind == "quotation_order_confirmation"
                        else "RISPOSTA_PREVENTIVO"
                    )
                    _log_imap_email(
                        email_data, sender, subject, body, timestamp, log_tipo, 0.9
                    )
                end_email_trace(quotation_kind)
                return out
            trace_step("NS-Q", "nessun thread / non conferma")
        except ImportError as exc:
            logger.debug("Quotation reply pipeline non disponibile: %s", exc)
            trace_step("NS-Q", f"skip import: {exc}")

        try:
            from modules.technical_inbound_pipeline import (
                try_process_inbound_technical_request,
            )

            if try_process_inbound_technical_request(email_data):
                out["kind"] = "technical_inbound"
                out["detail"] = "technical_inbound"
                out["handled"] = True
                out["saved"] = True
                if save_email_log:
                    _log_imap_email(
                        email_data,
                        sender,
                        subject,
                        body,
                        timestamp,
                        "RICHIESTA_TECNICA",
                        0.82,
                    )
                end_email_trace("technical_inbound")
                return out
        except ImportError as exc:
            logger.debug("Technical inbound pipeline non disponibile: %s", exc)

        try:
            from modules.quotation_inbound_pipeline import (
                try_process_inbound_quotation_request,
            )

            if try_process_inbound_quotation_request(email_data):
                out["kind"] = "quotation_inbound"
                out["detail"] = "quotation_inbound"
                out["handled"] = True
                out["saved"] = True
                if save_email_log:
                    _log_imap_email(
                        email_data,
                        sender,
                        subject,
                        body,
                        timestamp,
                        "RICHIESTA_PREVENTIVO",
                        0.85,
                    )
                return out
        except ImportError as exc:
            logger.debug("Quotation inbound pipeline non disponibile: %s", exc)

        if email_already_logged and email_already_logged(sender, subject):
            try:
                from modules.orders_database import logged_ordine_missing_order

                if logged_ordine_missing_order(sender, subject):
                    trace_step("RETRY", "log ORDINE senza riga DB — riprocesso")
                else:
                    confirm_hint = is_confirmation_hint(subject, body)
                    if not confirm_hint:
                        logger.info("Email già registrata, skip: %s", subject[:80])
                        trace_step("SKIP", "duplicato sender+oggetto")
                        end_email_trace("duplicato")
                        return out
                    logger.info(
                        "Email già registrata ma possibile conferma, riprocesso: %s",
                        subject[:80],
                    )
            except ImportError:
                if not is_confirmation_hint(subject, body):
                    logger.info("Email già registrata, skip: %s", subject[:80])
                    trace_step("SKIP", "duplicato sender+oggetto")
                    end_email_trace("duplicato")
                    return out

        if classify_email:
            tipo_email, confidence = classify_email(subject, body, sender, use_ai=use_ai)
        else:
            tipo_email, confidence = "ORDINE", 0.5
        trace_step("CLASSIFY", f"{tipo_email} ({confidence:.2f})")

        if tipo_email == "ORDINE":
            out["kind"] = "order"
            out["handled"] = True
            try:
                from modules.orders_database import should_persist_incoming_order

                if not should_persist_incoming_order(subject, body, sender):
                    out["detail"] = "skip — preventivo/richiesta (Quotations)"
                    trace_step("ORDINE", out["detail"])
                    end_email_trace(out["detail"])
                    return out
            except ImportError:
                pass
            saved, order_id = _process_order_after_classify(
                email_data, tipo_email, confidence, timestamp, use_llm=use_llm
            )
            out["saved"] = saved
            if saved and order_id:
                try:
                    from modules.order_intake_pipeline import process_new_order_intake

                    trace_step("INTAKE", "presa in carico ex novo…")
                    intake_ok = process_new_order_intake(
                        order_id, email_data, use_llm=use_llm
                    )
                    out["detail"] = (
                        "ordine salvato + presa in carico (invio/bozza)"
                        if intake_ok
                        else "ordine salvato (intake incompleto)"
                    )
                except ImportError as exc:
                    out["detail"] = "ordine salvato (pipeline intake assente)"
                    logger.error("order_intake_pipeline non disponibile: %s", exc)
            else:
                out["detail"] = "ordine salvato" if saved else "ordine non salvato"
            trace_step("ORDINE", out["detail"])
            end_email_trace(out["detail"])
            return out

        if tipo_email == "CONFERMA":
            out["kind"] = "confirmation"
            out["handled"] = True
            if not use_ai_confirm:
                logger.info("CONFERMA rilevata ma use_ai_on_confirmation=false, skip")
                out["detail"] = "conferma disabilitata"
                trace_step("CONFERMA", "use_ai_on_confirmation=false")
                _log_imap_email(
                    email_data, sender, subject, body, timestamp, tipo_email, confidence
                )
                end_email_trace(out["detail"])
                return out
            trace_step("CONFERMA", "→ pipeline classica")
            try:
                from modules.order_confirmation_pipeline import (
                    process_client_confirmation_email,
                )
                confirmed = process_client_confirmation_email(
                    email_data, use_llm=use_llm
                )
                if confirmed:
                    out["saved"] = True
                    out["detail"] = "conferma inviata/bozza"
                else:
                    try:
                        from modules.orders_database import should_persist_incoming_order

                        if should_persist_incoming_order(subject, body, sender):
                            trace_step(
                                "CONFERMA",
                                "nessun ordine abbinato → intake ex novo",
                            )
                            saved, order_id = _process_order_after_classify(
                                email_data,
                                "ORDINE",
                                confidence,
                                timestamp,
                                use_llm=use_llm,
                            )
                            if saved and order_id:
                                from modules.order_intake_pipeline import (
                                    process_new_order_intake,
                                )

                                intake_ok = process_new_order_intake(
                                    order_id, email_data, use_llm=use_llm
                                )
                                out["kind"] = "order"
                                out["saved"] = saved
                                out["detail"] = (
                                    "ordine ex novo + presa in carico"
                                    if intake_ok
                                    else "ordine ex novo (intake incompleto)"
                                )
                            else:
                                out["detail"] = "conferma fallita (no ordine)"
                        else:
                            out["detail"] = "conferma fallita"
                    except ImportError:
                        out["detail"] = "conferma fallita"
                trace_step("CONFERMA", out["detail"])
            except ImportError as exc:
                logger.error("Pipeline conferma non disponibile: %s", exc)
                out["detail"] = "pipeline conferma assente"
                trace_step("CONFERMA", "import fallito")
            end_email_trace(out["detail"])
            return out

        out["detail"] = tipo_email.lower()
        trace_step("STOP", f"tipo={tipo_email} — nessuna pipeline")

        if save_email_log:
            _log_imap_email(
                email_data, sender, subject, body, timestamp, tipo_email, confidence
            )
        logger.info("Email %s — nessuna azione", tipo_email)
        end_email_trace(out["detail"])
        return out
    except Exception as e:
        logger.error("Errore process_incoming_email: %s", e)
        try:
            from modules.orders_pipeline_trace import end_email_trace, trace_step
            trace_step("ERROR", str(e)[:100])
            end_email_trace("errore")
        except Exception:
            pass
        return out


def _process_order_after_classify(
    email_data: Dict,
    tipo_email: str,
    confidence: float,
    timestamp: str,
    *,
    use_llm: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Salva ordine dopo classificazione ORDINE (senza riclassificare)."""
    sender = email_data.get("from", "")
    subject = email_data.get("subject", "")
    body = email_data.get("body", "")

    message_id = (email_data.get("message_id") or "").strip()
    if message_id:
        try:
            from modules.orders_database import imap_message_fully_processed

            if imap_message_fully_processed(message_id):
                logger.info("Ordine skip: message-id già completato")
                return False, None
        except Exception:
            pass

    if email_already_logged and email_already_logged(sender, subject):
        try:
            from modules.orders_database import logged_ordine_missing_order

            if not logged_ordine_missing_order(sender, subject):
                logger.info("Ordine skip: email già registrata %s", subject[:60])
                return False, None
        except ImportError:
            logger.info("Ordine skip: email già registrata %s", subject[:60])
            return False, None

    try:
        from modules.orders_database import should_persist_incoming_order

        if not should_persist_incoming_order(subject, body, sender):
            logger.info("Ordine skip: intent preventivo/richiesta — %s", subject[:60])
            return False, None
    except ImportError:
        pass

    email_log_id = None
    if save_email_log:
        email_log_id = save_email_log(
            sender=sender,
            subject=subject,
            body=body,
            timestamp=timestamp,
            tipo_email=tipo_email,
            confidence=confidence,
            message_id=(email_data.get("message_id") or "").strip() or None,
        )

    _, client_email = parseaddr(sender)
    client_email = client_email or sender
    order_id = make_safe_order_id(sender)
    order_data = {
        "order_id": order_id,
        "from": sender,
        "client": client_email.split("@")[0] if "@" in client_email else client_email[:80],
        "client_email": client_email,
        "subject": subject,
        "body": body,
        "product": subject,
        "timestamp": timestamp,
        "created_at": timestamp,
        "status": "NEW",
    }
    if save_order:
        order_db_id = save_order(order_data, email_log_id=email_log_id)
        if order_db_id:
            if email_log_id:
                try:
                    from modules.orders_database import get_database_path
                    import sqlite3 as _sqlite3

                    conn = _sqlite3.connect(str(get_database_path()))
                    conn.execute(
                        "UPDATE email_logs SET order_id = ? WHERE id = ?",
                        (order_id, email_log_id),
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
            json_order_data = {
                "id": order_id,
                "from": sender,
                "subject": subject,
                "body": body,
                "timestamp": timestamp,
                "status": "NEW",
                "sent_confirmation_email": None,
            }
            save_order_to_json(json_order_data)
            update_last_order_json(json_order_data)
            logger.info("Ordine %s salvato (DB ID: %s)", order_id, order_db_id)
            return True, order_id
    json_order_data = {
        "id": order_id,
        "from": sender,
        "subject": subject,
        "body": body,
        "timestamp": timestamp,
        "status": "NEW",
        "sent_confirmation_email": None,
    }
    if save_order_to_json(json_order_data):
        update_last_order_json(json_order_data)
        return True, order_id
    return False, None


def process_order_email(email_data: Dict) -> bool:
    """
    Processa un'email come nuovo ordine e la salva nel database
    
    Args:
        email_data: Dizionario con i dati dell'email
        
    Returns:
        True se il processing è riuscito, False altrimenti
    """
    result = process_incoming_email(email_data)
    return result.get("kind") == "order" and result.get("saved", False)


def process_confirmation_email(email_data: Dict, order_data: Dict) -> bool:
    """
    Processa una risposta del cliente come conferma ordine
    
    Args:
        email_data: Dizionario con i dati dell'email di risposta
        order_data: Dizionario con i dati dell'ordine originale
        
    Returns:
        True se il processing è riuscito, False altrimenti
    """
    try:
        if not analyze_order_confirmation:
            logger.error("Modulo analyze_order_confirmation non disponibile")
            return False
        
        # Analizza la risposta con Gemini
        email_body = email_data.get("body", "")
        result = analyze_order_confirmation(email_body, order_data)
        
        if not result:
            logger.warning("Analisi Gemini non ha restituito risultati")
            return False
        
        status = result.get("status", "pending")
        
        # Se l'ordine è confermato, processa la conferma
        if status == "confirmed":
            # Aggiorna lo stato dell'ordine
            order_data["status"] = "confirmed"
            order_data["notes"] = result.get("notes", "")
            order_data["confirmation_timestamp"] = datetime.now().isoformat()
            
            # Ottieni il testo della conferma
            confirmation_text = result.get("confirmation_email_text", "")
            
            # Invia email di conferma
            if send_order_confirmation_email:
                email_info = send_order_confirmation_email(
                    to_email=order_data.get("from", ""),
                    order_data=order_data,
                    confirmation_text=confirmation_text
                )
                
                if email_info:
                    # Salva informazioni email inviata
                    order_data["sent_confirmation_email"] = email_info
                else:
                    logger.error("Invio email di conferma fallito")
                    order_data["sent_confirmation_email"] = {
                        "sent": False,
                        "timestamp": datetime.now().isoformat(),
                        "error": "Invio fallito"
                    }
            else:
                logger.error("Modulo send_order_confirmation_email non disponibile")
            
            # Salva ordine aggiornato
            if save_order_to_json(order_data):
                update_last_order_json(order_data)
                logger.info(f"Ordine {order_data.get('id')} confermato e email inviata")
                return True
            else:
                return False
        else:
            logger.info(f"Ordine {order_data.get('id')} non confermato (status: {status})")
            return False
            
    except Exception as e:
        logger.error(f"Errore nel processing conferma ordine: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_gmail_orders() -> Dict:
    """
    Controlla la casella Gmail IMAP per nuovi ordini e conferme
    
    Returns:
        Dizionario con lo stato dell'operazione:
        {
            "status": "OK" | "ERROR",
            "last_check": "...",
            "last_email_from": "...",
            "last_email_subject": "...",
            "error_message": "..."
        }
    """
    result = {
        "status": "OK",
        "last_check": datetime.now().isoformat(),
        "last_email_from": "",
        "last_email_subject": "",
        "error_message": "",
        "emails_fetched": 0,
        "emails_processed": 0,
        "orders_saved": 0,
        "confirmations_sent": 0,
        "quotation_replies": 0,
        "quotation_inbound": 0,
        "skipped": False,
    }

    if not _imap_poll_lock.acquire(blocking=False):
        logger.info("Poll IMAP già in corso — skip")
        result["skipped"] = True
        return result

    mail = None
    try:
        # Carica credenziali
        email_addr, app_password = load_gmail_credentials()
        
        if not email_addr or not app_password:
            result["status"] = "ERROR"
            result["error_message"] = "Credenziali Gmail non configurate in config.json"
        else:
            logger.info(f"Connessione a {GMAIL_IMAP_HOST}:{GMAIL_IMAP_PORT}...")
            mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
            logger.info("Login IMAP in corso...")
            mail.login(email_addr, app_password)
            mail.select("INBOX")

            imap_settings = get_orders_imap_settings()
            criteria_list = build_imap_search_criteria_list(imap_settings)
            email_ids: List[bytes] = []
            seen_ids: set[bytes] = set()
            unseen_uid_set: set[bytes] = set()
            for search_criteria in criteria_list:
                logger.info("Ricerca IMAP: %s", search_criteria)
                status, messages = mail.search(None, search_criteria)
                if status != "OK":
                    logger.warning("Ricerca IMAP fallita (%s): %s", search_criteria, status)
                    continue
                is_unseen_crit = "UNSEEN" in (search_criteria or "").upper()
                for eid in messages[0].split():
                    if eid and eid not in seen_ids:
                        seen_ids.add(eid)
                        email_ids.append(eid)
                        if is_unseen_crit:
                            unseen_uid_set.add(eid)

            if not email_ids:
                logger.info("Nessuna nuova email trovata (criteri: %s)", len(criteria_list))
            result["imap_search"] = " | ".join(criteria_list)
            result["imap_filter_summary"] = format_imap_filter_summary(imap_settings)

            max_per_poll = imap_settings.get("imap_max_per_poll", 20)
            if len(email_ids) > max_per_poll:
                logger.info(
                    "Limitate %s email (di %s) per ciclo — priorità alle più recenti",
                    max_per_poll,
                    len(email_ids),
                )
            email_ids = _sort_email_ids_newest_first(email_ids)[:max_per_poll]

            llm_on_poll = bool(imap_settings.get("confirmation_use_llm_on_poll", True))
            use_ai_poll = bool(imap_settings.get("use_ai_on_poll", False))
            llm_target_uid = pick_newest_unseen_uid(email_ids, unseen_uid_set)
            # Se la mail ex-novo è già letta in Gmail, UNSEEN è vuoto: fallback sulla più recente del batch
            llm_fallback_uid: Optional[bytes] = None
            if llm_on_poll and llm_target_uid is None and email_ids:
                llm_fallback_uid = email_ids[0]
            pipeline_events: List[str] = []

            logger.info(
                "Elaborazione %s email (LLM poll=%s, smart UID=%s, fallback UID=%s)",
                len(email_ids),
                "on" if llm_on_poll else "off",
                llm_target_uid.decode() if llm_target_uid else "—",
                llm_fallback_uid.decode() if llm_fallback_uid else "—",
            )
            result["emails_fetched"] = len(email_ids)
            result["poll_interval_seconds"] = imap_settings.get("gmail_poll_seconds", 300)
            result["use_ai_on_poll"] = imap_settings.get("use_ai_on_poll", False)
            result["confirmation_use_llm_on_poll"] = llm_on_poll
            result["imap_mode"] = imap_settings.get("imap_mode", "poll")

            for email_id in email_ids:
                try:
                    status, msg_data = mail.fetch(email_id, "(RFC822)")
                    if status != "OK":
                        continue

                    msg = email.message_from_bytes(msg_data[0][1])
                    email_data = parse_email_message(msg)
                    if not email_data:
                        continue

                    mid = email_data.get("message_id") or ""
                    if imap_message_already_processed(mid):
                        subj_short = (email_data.get("subject") or "").replace("\r", " ").replace("\n", " ")[:50]
                        evt = f"{subj_short} → già processata (skip)"
                        pipeline_events.append(evt)
                        try:
                            from ui.common.gmail_imap_poll_log import append_pipeline_event
                            append_pipeline_event(evt)
                        except Exception:
                            pass
                        continue

                    subj_short = (email_data.get("subject") or "").replace("\r", " ").replace("\n", " ")[:50]
                    result["last_email_from"] = email_data.get("from", "")
                    result["last_email_subject"] = email_data.get("subject", "")

                    smart_unseen = llm_target_uid is not None and email_id == llm_target_uid
                    smart_fallback = (
                        llm_fallback_uid is not None and email_id == llm_fallback_uid
                    )
                    use_llm = llm_on_poll and (smart_unseen or smart_fallback)
                    use_ai = use_ai_poll and (smart_unseen or smart_fallback)
                    result["emails_processed"] += 1
                    handled = process_incoming_email(
                        email_data, use_llm=use_llm, use_ai=use_ai
                    )
                    kind = handled.get("kind") or "skip"
                    detail = handled.get("detail") or kind
                    if use_llm or use_ai:
                        tag = "LLM unseen" if smart_unseen else "LLM fallback"
                        detail = f"{detail} [{tag}]"

                    evt = f"{subj_short} → {detail}"
                    pipeline_events.append(evt)
                    logger.info("Pipeline: %s", evt)

                    if kind == "order" and handled.get("saved"):
                        result["orders_saved"] += 1
                    if kind in ("confirmation", "quotation_order_confirmation") and handled.get("saved"):
                        result["confirmations_sent"] = result.get("confirmations_sent", 0) + 1
                    if kind == "quotation_reply" and handled.get("handled"):
                        result["quotation_replies"] = result.get("quotation_replies", 0) + 1
                    if kind == "quotation_inbound" and handled.get("handled"):
                        result["quotation_inbound"] = result.get("quotation_inbound", 0) + 1

                    try:
                        from ui.common.gmail_imap_poll_log import append_pipeline_event

                        append_pipeline_event(evt)
                    except Exception:
                        pass

                    try:
                        mail.store(email_id, "+FLAGS", "\\Seen")
                    except Exception as mark_err:
                        logger.warning("Impossibile marcare email come letta: %s", mark_err)

                except Exception as e:
                    logger.error(f"Errore nel processing email {email_id}: {e}")
                    continue

            result["pipeline_events"] = pipeline_events[-12:]

            logger.info("Controllo Gmail completato con successo")
        
    except imaplib.IMAP4.error as e:
        result["status"] = "ERROR"
        result["error_message"] = f"Errore IMAP: {str(e)}"
        logger.error(f"Errore IMAP: {e}")
    except Exception as e:
        result["status"] = "ERROR"
        result["error_message"] = f"Errore generico: {str(e)}"
        logger.error(f"Errore generico: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _imap_poll_lock.release()
        if mail:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
    
    # Salva stato in file JSON
    try:
        logs_dir = get_logs_dir()
        status_file = logs_dir / "gmail_orders_status.json"
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Errore nel salvataggio stato: {e}")

    try:
        from modules.quotation_auto_pipeline import process_pending_nuova_requests

        auto_out = process_pending_nuova_requests(limit=2)
        result["quotations_auto_processed"] = int(auto_out.get("processed") or 0)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Quotation auto dopo IMAP: %s", exc)

    return result


if __name__ == "__main__":
    # Test del servizio
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    result = check_gmail_orders()
    print(f"Risultato: {result}")

