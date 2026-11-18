"""
Modulo per gestione database ordini e fatture
Gestisce inserimento, validazione e query su SQLite
"""
import sqlite3
import json
import logging
from email.utils import parseaddr
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def orders_table_visibility_sql() -> str:
    """
    Clausola SQL: in GUI solo ordini veri, non ogni mail preventivo/richiesta della casella.
    Disattivabile con config orders.show_all_in_table = true.
    """
    try:
        from core.machine_plc_config import load_config

        orders_cfg = load_config().get("orders") or {}
        if isinstance(orders_cfg, dict) and orders_cfg.get("show_all_in_table"):
            return ""
    except Exception:
        pass
    return """
        AND LOWER(COALESCE(client_email, '')) NOT LIKE '%amazon%'
        AND LOWER(COALESCE(email_subject, '')) NOT LIKE '%amazon%'
        AND LOWER(COALESCE(email_subject, '')) NOT LIKE '%offerta di lavoro%'
        AND LOWER(COALESCE(email_subject, '')) NOT LIKE '%offerte di lavoro%'
        AND LOWER(COALESCE(email_subject, '')) NOT LIKE '%consegna effettuata%'
        AND LOWER(COALESCE(email_subject, '')) NOT LIKE '%in consegna oggi%'
        AND (
            COALESCE(quotation_case_id, '') != ''
            OR LOWER(COALESCE(email_subject, '')) LIKE '%ordine%'
            OR LOWER(COALESCE(email_subject, '')) LIKE '%order%'
            OR LOWER(COALESCE(product, '')) LIKE '%ordine%'
            OR LOWER(COALESCE(product, '')) LIKE '%order%'
            OR UPPER(COALESCE(status, '')) IN (
                'CONFIRMED', 'CONFIRMED_PARTIAL', 'REJECTED_STOCK',
                'INVIATO', 'IN PRODUZIONE', 'COMPLETATO', 'PENDING_APPROVAL'
            )
        )
    """

_CONFIRMED_GUI_STATUSES = frozenset({
    "CONFIRMED", "CONFIRMED_PARTIAL", "REJECTED_STOCK",
    "INVIATO", "IN PRODUZIONE", "COMPLETATO", "PENDING_APPROVAL",
})


def orders_show_all_in_table() -> bool:
    try:
        from core.machine_plc_config import load_config

        orders_cfg = load_config().get("orders") or {}
        return bool(isinstance(orders_cfg, dict) and orders_cfg.get("show_all_in_table"))
    except Exception:
        return False


def order_visible_in_orders_table(
    *,
    email_subject: str = "",
    product: str = "",
    status: str = "",
    quotation_case_id: str = "",
    client_email: str = "",
    email_body: str = "",
) -> bool:
    """Stessa logica di orders_table_visibility_sql(), per filtri Python (es. JSON fallback)."""
    if orders_show_all_in_table():
        return True
    try:
        from modules.order_inbox_noise import is_inbox_noise

        if is_inbox_noise(
            subject=email_subject,
            body=email_body,
            sender=client_email,
        ):
            return False
    except ImportError:
        pass
    if (quotation_case_id or "").strip():
        return True
    subj = (email_subject or "").lower()
    prod = (product or "").lower()
    if "ordine" in subj or "order" in subj:
        return True
    if "ordine" in prod or "order" in prod:
        return True
    return (status or "").upper() in _CONFIRMED_GUI_STATUSES


def delete_orders_not_visible_in_table() -> int:
    """Elimina righe orders che non devono comparire in GUI (poll IMAP errati)."""
    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT order_id, email_subject, email_body, client_email, product, status, "
            "quotation_case_id FROM orders"
        )
        junk_ids: List[str] = []
        for row in cursor.fetchall():
            if order_visible_in_orders_table(
                email_subject=str(row["email_subject"] or ""),
                product=str(row["product"] or ""),
                status=str(row["status"] or ""),
                quotation_case_id=str(row["quotation_case_id"] or ""),
                client_email=str(row["client_email"] or ""),
                email_body=str(row["email_body"] or ""),
            ):
                continue
            junk_ids.append(row["order_id"])
        conn.close()
        deleted = delete_orders(junk_ids)
        if deleted:
            logger.info("Eliminati %s ordini spazzatura dalla tabella orders", deleted)
        return deleted
    except Exception as e:
        logger.error("Errore purge ordini spazzatura: %s", e)
        return 0


def get_database_path() -> Path:
    """
    Restituisce il percorso del database ordini
    Usa nstonellm.db per unificare con il resto del sistema
    
    Returns:
        Path del database
    """
    # Usa lo stesso database del sistema principale
    db_path = Path(__file__).parent.parent / "data" / "nstonellm.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _table_exists(cursor: sqlite3.Cursor, name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    )
    return cursor.fetchone() is not None


def migrate_orders_table(cursor: sqlite3.Cursor) -> None:
    """
    Porta la tabella orders (schema CSV legacy) allo schema esteso email/IMAP.
    CREATE TABLE IF NOT EXISTS non aggiunge colonne mancanti.
    """
    if not _table_exists(cursor, "orders"):
        return

    cursor.execute("PRAGMA table_info(orders)")
    cols = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in (
        ("email_id", "INTEGER"),
        ("client_email", "TEXT"),
        ("materiale", "TEXT"),
        ("quantita", "REAL"),
        ("email_subject", "TEXT"),
        ("email_body", "TEXT"),
        ("validation_errors", "TEXT"),
        ("quotation_case_id", "TEXT"),
    ):
        if col_name not in cols:
            cursor.execute(f"ALTER TABLE orders ADD COLUMN {col_name} {col_type}")

    cursor.execute("PRAGMA table_info(orders)")
    cols_after = {row[1] for row in cursor.fetchall()}
    if "client_email" in cols_after and "client" in cols_after:
        cursor.execute(
            """
            UPDATE orders
            SET client_email = client
            WHERE (client_email IS NULL OR client_email = '')
              AND client IS NOT NULL AND client != ''
            """
        )


def _ensure_email_logs_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT,
            timestamp TIMESTAMP NOT NULL,
            tipo_email TEXT NOT NULL,
            confidence REAL,
            processed BOOLEAN DEFAULT 0,
            order_id TEXT,
            message_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    migrate_email_logs_table(cursor)


def migrate_email_logs_table(cursor: sqlite3.Cursor) -> None:
    if not _table_exists(cursor, "email_logs"):
        return
    cursor.execute("PRAGMA table_info(email_logs)")
    cols = {row[1] for row in cursor.fetchall()}
    if "message_id" not in cols:
        cursor.execute("ALTER TABLE email_logs ADD COLUMN message_id TEXT")
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_logs_message_id ON email_logs(message_id)"
        )
    except sqlite3.OperationalError:
        pass


def _ensure_orders_table(cursor: sqlite3.Cursor) -> None:
    if _table_exists(cursor, "orders"):
        migrate_orders_table(cursor)
        return

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL UNIQUE,
            email_id INTEGER,
            client TEXT NOT NULL,
            client_email TEXT NOT NULL,
            product TEXT NOT NULL,
            materiale TEXT,
            quantita REAL,
            machine TEXT,
            status TEXT NOT NULL DEFAULT 'NEW',
            scheduled TEXT,
            email_subject TEXT,
            email_body TEXT,
            validation_errors TEXT,
            quotation_case_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _ensure_invoices_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT NOT NULL UNIQUE,
            order_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            client_email TEXT NOT NULL,
            amount_eur REAL,
            iva_percent REAL DEFAULT 22.0,
            status TEXT NOT NULL DEFAULT 'GENERATA',
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_invio TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def init_database() -> bool:
    """
    Inizializza il database creando le tabelle se non esistono
    
    Returns:
        True se inizializzazione riuscita, False altrimenti
    """
    try:
        db_path = get_database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        _ensure_email_logs_table(cursor)
        _ensure_orders_table(cursor)
        _ensure_invoices_table(cursor)

        # Indici (ignora se già presenti)
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_email_logs_tipo ON email_logs(tipo_email)",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
            "CREATE INDEX IF NOT EXISTS idx_orders_client_email ON orders(client_email)",
            "CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)",
            "CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product)",
            "CREATE INDEX IF NOT EXISTS idx_orders_email_subject ON orders(email_subject)",
            "CREATE INDEX IF NOT EXISTS idx_orders_updated_at ON orders(updated_at)",
        ):
            try:
                cursor.execute(idx_sql)
            except sqlite3.OperationalError:
                pass

        conn.commit()
        conn.close()

        logger.info("Database inizializzato: %s", db_path)
        return True

    except Exception as e:
        logger.error("Errore inizializzazione database: %s", e)
        return False


def email_already_logged(sender: str, subject: str, max_hours: int = 168) -> bool:
    """True se stessa email (mittente+oggetto) già registrata di recente — evita doppio processo/token."""
    try:
        db_path = get_database_path()
        if not db_path.exists():
            return False
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        cursor = conn.cursor()
        norm_subj = _normalize_email_subject(subject)
        cursor.execute(
            """
            SELECT COUNT(*) FROM email_logs
            WHERE datetime(timestamp) >= datetime('now', ?)
              AND (
                    (sender = ? AND subject = ?)
                 OR (sender = ? AND subject = ?)
              )
            """,
            (
                f"-{max_hours} hours",
                sender, subject,
                sender, norm_subj,
            ),
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        logger.warning("Controllo duplicati email_logs fallito: %s", e)
        return False


def email_log_exists_for_message_id(message_id: str) -> bool:
    """True se Message-ID già registrato (idempotenza poll IMAP)."""
    return get_email_log_by_message_id(message_id) is not None


def get_email_log_by_message_id(message_id: str) -> Optional[Dict]:
    """Riga email_logs per Message-ID, o None."""
    mid = (message_id or "").strip()
    if not mid:
        return None
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM email_logs WHERE message_id = ? ORDER BY id DESC LIMIT 1",
            (mid,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.warning("Lettura email_log per message_id fallita: %s", e)
        return None


def order_exists_for_email_log_id(email_log_id: int) -> bool:
    """True se esiste una riga orders collegata a email_logs.id."""
    if not email_log_id:
        return False
    try:
        db_path = get_database_path()
        if not db_path.exists():
            return False
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        row = conn.execute(
            "SELECT 1 FROM orders WHERE email_id = ? LIMIT 1",
            (int(email_log_id),),
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        logger.warning("Controllo order per email_log_id fallito: %s", e)
        return False


def order_linked_to_email_log_row(row: Dict) -> bool:
    """True se l'email_log ha già un ordine persistito in tabella orders."""
    if not row:
        return False
    oid = (row.get("order_id") or "").strip()
    if oid and get_order_by_order_id(oid):
        return True
    return order_exists_for_email_log_id(int(row.get("id") or 0))


def imap_message_fully_processed(message_id: str) -> bool:
    """
    True se la mail non va riprocessata.
    ORDINE/CONFERMA: skip solo se l'ordine esiste davvero (non basta email_logs).
    """
    row = get_email_log_by_message_id(message_id)
    if not row:
        return False
    tipo = (row.get("tipo_email") or "").upper()
    if tipo == "ORDINE":
        return order_linked_to_email_log_row(row)
    if tipo == "CONFERMA":
        if order_linked_to_email_log_row(row):
            return True
        oid = (row.get("order_id") or "").strip()
        if oid:
            ord_row = get_order_by_order_id(oid)
            if ord_row and (ord_row.get("status") or "").upper() in (
                "CONFIRMED", "CONFIRMED_PARTIAL", "INVIATO", "IN PRODUZIONE",
                "COMPLETATO", "PENDING_APPROVAL",
            ):
                return True
        return False
    return True


def logged_ordine_missing_order(sender: str, subject: str) -> bool:
    """True se c'è un log ORDINE recente senza riga corrispondente in orders."""
    try:
        db_path = get_database_path()
        if not db_path.exists():
            return False
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        norm_subj = _normalize_email_subject(subject)
        rows = conn.execute(
            """
            SELECT id, order_id FROM email_logs
            WHERE tipo_email = 'ORDINE'
              AND datetime(timestamp) >= datetime('now', '-168 hours')
              AND (
                    (sender = ? AND subject = ?)
                 OR (sender = ? AND subject = ?)
              )
            ORDER BY id DESC
            LIMIT 5
            """,
            (sender, subject, sender, norm_subj),
        ).fetchall()
        conn.close()
        for row in rows:
            if not order_linked_to_email_log_row(dict(row)):
                return True
        return False
    except Exception as e:
        logger.warning("Controllo ordine mancante per log fallito: %s", e)
        return False


def backfill_orders_from_email_logs(limit: int = 100) -> int:
    """Crea righe orders per email_logs ORDINE mai persistite (es. dopo purge DB)."""
    import re
    from email.utils import parseaddr

    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT el.id, el.sender, el.subject, el.body, el.timestamp
            FROM email_logs el
            WHERE el.tipo_email = 'ORDINE'
              AND datetime(el.timestamp) >= datetime('now', '-72 hours')
              AND NOT EXISTS (
                  SELECT 1 FROM orders o WHERE o.email_id = el.id
              )
              AND (
                  el.order_id IS NULL OR el.order_id = ''
                  OR NOT EXISTS (
                      SELECT 1 FROM orders o2 WHERE o2.order_id = el.order_id
                  )
              )
            ORDER BY el.id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        conn.close()

        created = 0
        for row in rows:
            sender = row["sender"] or ""
            subject = row["subject"] or ""
            body = row["body"] or ""
            if not should_persist_incoming_order(subject, body, sender):
                continue
            ts = str(row["timestamp"] or datetime.now().isoformat())
            _, client_email = parseaddr(sender)
            client_email = client_email or sender
            local = client_email.split("@")[0] if "@" in client_email else client_email[:40]
            safe = re.sub(r"[^\w.\-]+", "_", local).strip("._")[:48] or "client"
            ts_clean = ts.replace(":", "").replace("-", "").replace("T", "_")[:15]
            order_id = f"{ts_clean}_{safe}_{row['id']}"

            order_data = {
                "order_id": order_id,
                "from": sender,
                "client": client_email.split("@")[0] if "@" in client_email else client_email[:80],
                "client_email": client_email,
                "subject": subject,
                "body": body,
                "product": subject,
                "timestamp": ts,
                "created_at": ts,
                "status": "NEW",
            }
            db_id = save_order(order_data, email_log_id=int(row["id"]))
            if db_id:
                try:
                    conn = sqlite3.connect(str(db_path))
                    conn.execute(
                        "UPDATE email_logs SET order_id = ? WHERE id = ?",
                        (order_id, row["id"]),
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
                created += 1
        if created:
            logger.info("Backfill orders da email_logs: %s righe create", created)
        return created
    except Exception as e:
        logger.error("Backfill orders da email_logs fallito: %s", e)
        return 0


def _normalize_email_subject(subject: str) -> str:
    import re

    s = (subject or "").strip()
    s = re.sub(r"^(?:re|fwd|fw)\s*:\s*", "", s, flags=re.I)
    return s.strip()


def should_persist_incoming_order(
    subject: str, body: str = "", sender: str = ""
) -> bool:
    """
    True solo se la mail deve entrare in tabella orders (non preventivi/richieste Quotations).
    """
    try:
        from modules.order_inbox_noise import is_inbox_noise

        if is_inbox_noise(subject=subject, body=body, sender=sender):
            return False
    except ImportError:
        pass
    subj = _normalize_email_subject(subject).lower()
    combined = f"{subj} {(body or '').lower()}"

    from modules.pipeline_keywords import ORDER_MARKERS, QUOTE_MARKERS

    order_markers = ORDER_MARKERS
    quote_markers = QUOTE_MARKERS

    has_order = any(m in combined for m in order_markers)
    has_quote = any(m in combined for m in quote_markers)

    if has_quote and not has_order:
        return False
    if has_order:
        return True
    # Materiale + quantità senza keyword esplicita — raro, accetta
    material_hints = (
        "lastre", " m2", " mq", " sqm", "marmo", "granito", "spessore",
        "marble", "granite", "stone", "slab",
    )
    return sum(1 for h in material_hints if h in combined) >= 2


def save_email_log(sender: str, subject: str, body: str, timestamp: str, 
                   tipo_email: str, confidence: float, order_id: Optional[str] = None,
                   message_id: Optional[str] = None) -> Optional[int]:
    """
    Salva log email nel database
    
    Returns:
        ID email_logs inserito o None se errore
    """
    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO email_logs (sender, subject, body, timestamp, tipo_email, confidence, order_id, message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sender, subject, body, timestamp, tipo_email, confidence, order_id, message_id))
        
        email_log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Email log salvato: ID {email_log_id}, tipo: {tipo_email}")
        return email_log_id
        
    except Exception as e:
        logger.error(f"Errore salvataggio email log: {e}")
        return None


def validate_order(order_data: Dict) -> Tuple[bool, List[str]]:
    """
    Valida i dati di un ordine
    
    Args:
        order_data: Dizionario con dati ordine
        
    Returns:
        Tuple (is_valid, errors)
    """
    errors = []
    
    # Verifica campi obbligatori
    if not order_data.get("order_id"):
        errors.append("Codice ordine mancante")
    
    if not order_data.get("client") and not order_data.get("client_email"):
        errors.append("Cliente o email cliente mancante")
    
    if not order_data.get("product") and not order_data.get("materiale"):
        errors.append("Prodotto o materiale mancante")
    
    # Verifica quantità numerica se presente
    quantita = order_data.get("quantita")
    if quantita is not None:
        try:
            float(quantita)
        except (ValueError, TypeError):
            errors.append("Quantità non numerica")
    
    # Verifica data ordine
    if not order_data.get("created_at") and not order_data.get("timestamp"):
        errors.append("Data ordine mancante")
    
    return (len(errors) == 0, errors)


def find_order_by_quotation_case_id(case_id: str) -> Optional[Dict]:
    """Ordine collegato a un case preventivo NS-Q."""
    cid = (case_id or "").strip()
    if not cid:
        return None
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, order_id, client, client_email, product, materiale, quantita,
                   machine, status, email_subject, email_body, quotation_case_id,
                   created_at, validation_errors
            FROM orders
            WHERE quotation_case_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (cid,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error("Errore ricerca ordine per case %s: %s", cid[:8], e)
        return None


def get_order_by_order_id(order_id: str) -> Optional[Dict]:
    """Carica un ordine completo per order_id."""
    try:
        db_path = get_database_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, order_id, client, client_email, product, materiale, quantita,
                   machine, status, scheduled, email_subject, email_body, created_at,
                   validation_errors, quotation_case_id
            FROM orders WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)
    except Exception as e:
        logger.error("Errore lettura ordine %s: %s", order_id, e)
        return None


def get_order_by_row_match(client_email: str, subject_fragment: str) -> Optional[Dict]:
    """Trova ordine per email cliente e frammento oggetto (tabella UI)."""
    try:
        db_path = get_database_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT order_id, client, client_email, product, materiale, quantita,
                   machine, status, email_subject, email_body, created_at
            FROM orders
            WHERE (client_email = ? OR client = ?)
              AND (email_subject LIKE ? OR product LIKE ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (client_email, client_email, f"%{subject_fragment}%", f"%{subject_fragment}%"),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error("Errore ricerca ordine: %s", e)
        return None


def find_order_for_confirmation(
    client_email: str,
    subject: str,
    body: str = "",
) -> Optional[Dict]:
    """
    Trova l'ordine più probabile per una email di conferma del cliente.
    Priorità: ID in testo → NS-Q → ordine aperto più recente del cliente.
    """
    import re

    email = (client_email or "").strip().lower()
    if not email:
        return None

    combined = f"{subject or ''}\n{body or ''}"
    clean_subj = _normalize_email_subject(subject)
    fragment = clean_subj[:60] if clean_subj else ""

    order_id_hint: Optional[str] = None
    for pattern in (
        r"(?:#|ordine\s+#?\s*)(20\d{6}_\d{6}_[\w.-]+)",
        r"\b(20\d{6}_\d{6}_[\w.-]+)\b",
        r"\b(Q-[a-z0-9]{8}-\d{8}_\d{6})\b",
        r"\b(ORD[-_][\w-]+)\b",
    ):
        match = re.search(pattern, combined, flags=re.I)
        if match:
            order_id_hint = match.group(1)
            break

    ns_q_token: Optional[str] = None
    try:
        from modules.quotation_email_thread import extract_token8

        ns_q_token = extract_token8(subject) or extract_token8(body)
    except Exception:
        pass

    open_statuses = (
        "NEW", "new", "NUOVO", "nuovo", "PENDING", "pending", "RECEIVED",
        "received", "DA CONFERMARE", "IN ATTESA", "DA_VALIDARE",
    )
    open_placeholders = ",".join("?" for _ in open_statuses)

    def _row_to_dict(row) -> Optional[Dict]:
        return dict(row) if row else None

    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row

        if order_id_hint:
            row = conn.execute(
                """
                SELECT order_id, client, client_email, product, materiale, quantita,
                       machine, status, email_subject, email_body, created_at,
                       quotation_case_id
                FROM orders WHERE order_id = ?
                """,
                (order_id_hint,),
            ).fetchone()
            if row:
                conn.close()
                return dict(row)

        if ns_q_token:
            row = conn.execute(
                """
                SELECT order_id, client, client_email, product, materiale, quantita,
                       machine, status, email_subject, email_body, created_at,
                       quotation_case_id
                FROM orders
                WHERE quotation_case_id LIKE ?
                ORDER BY datetime(created_at) DESC
                LIMIT 1
                """,
                (f"%{ns_q_token}%",),
            ).fetchone()
            if row:
                conn.close()
                return dict(row)

        params: list = [email, email]
        sql = f"""
            SELECT order_id, client, client_email, product, materiale, quantita,
                   machine, status, email_subject, email_body, created_at,
                   quotation_case_id
            FROM orders
            WHERE (LOWER(client_email) = ? OR LOWER(client) = ?)
        """
        if fragment:
            sql += """
              AND (email_subject LIKE ? OR product LIKE ? OR email_body LIKE ?)
            """
            params.extend([f"%{fragment}%", f"%{fragment}%", f"%{fragment[:40]}%"])

        sql += f"""
            ORDER BY
              CASE WHEN UPPER(status) IN ({open_placeholders}) THEN 0 ELSE 1 END,
              datetime(created_at) DESC,
              id DESC
            LIMIT 1
        """
        params.extend(open_statuses)
        row = conn.execute(sql, params).fetchone()

        if not row:
            row = conn.execute(
                f"""
                SELECT order_id, client, client_email, product, materiale, quantita,
                       machine, status, email_subject, email_body, created_at,
                       quotation_case_id
                FROM orders
                WHERE LOWER(client_email) = ? OR LOWER(client) = ?
                ORDER BY
                  CASE WHEN UPPER(status) IN ({open_placeholders}) THEN 0 ELSE 1 END,
                  datetime(created_at) DESC,
                  id DESC
                LIMIT 1
                """,
                (email, email, *open_statuses),
            ).fetchone()

        conn.close()
        return _row_to_dict(row)
    except Exception as e:
        logger.error("Errore ricerca ordine per conferma: %s", e)
        return None


def get_order_confirmation_meta(order_id: str) -> Dict:
    """Metadati conferma / scalo stock da validation_errors JSON."""
    try:
        db_path = get_database_path()
        if not db_path.exists():
            return {}
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        row = conn.execute(
            "SELECT validation_errors FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return {}
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def update_order_confirmation_result(
    order_id: str,
    status: str,
    notes: str = "",
    availability: Optional[str] = None,
    stock_report: Optional[Dict] = None,
    confirmation_email: Optional[Dict] = None,
    stock_deduction: Optional[Dict] = None,
) -> bool:
    """Aggiorna ordine dopo pipeline conferma cliente."""
    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        extra = get_order_confirmation_meta(order_id)
        extra.update({
            "availability": availability,
            "stock_report": stock_report,
            "confirmation_email": confirmation_email,
            "notes": notes,
        })
        if stock_deduction is not None:
            extra["stock_deduction"] = stock_deduction
            extra["stock_deducted"] = bool(stock_deduction.get("applied"))
        validation_errors = json.dumps(extra, ensure_ascii=False)
        conn.execute(
            """
            UPDATE orders SET
                status = ?,
                validation_errors = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (status, validation_errors, order_id),
        )
        conn.commit()
        ok = conn.total_changes > 0
        conn.close()
        return ok
    except Exception as e:
        logger.error("Errore update conferma ordine %s: %s", order_id, e)
        return False


def _confirmation_from_validation_json(raw: Optional[str]) -> Optional[Dict]:
    """Estrae metadati email inviata da validation_errors (JSON)."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("confirmation_email", "sent_confirmation_email"):
        info = data.get(key)
        if isinstance(info, dict) and info.get("sent"):
            return info
    return None


def list_sent_confirmation_orders(limit: int = 100) -> List[Dict]:
    """Ordini con email di conferma inviata (SQLite orders.validation_errors)."""
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return []

        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT order_id, client, client_email, status, validation_errors, updated_at, created_at
            FROM orders
            WHERE validation_errors IS NOT NULL AND TRIM(validation_errors) != ''
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (max(limit * 4, limit),),
        ).fetchall()
        conn.close()

        sent: List[Dict] = []
        for row in rows:
            info = _confirmation_from_validation_json(row["validation_errors"])
            if not info:
                continue
            ts = info.get("timestamp") or row["updated_at"] or row["created_at"] or ""
            sent.append(
                {
                    "order_id": row["order_id"],
                    "client": row["client_email"] or row["client"] or "",
                    "sent_timestamp": ts,
                    "sent_status": "Sent" if info.get("sent") else "Error",
                    "status": row["status"] or "",
                    "confirmation_email": info,
                }
            )
            if len(sent) >= limit:
                break

        sent.sort(key=lambda x: str(x.get("sent_timestamp", "")), reverse=True)
        return sent[:limit]
    except Exception as exc:
        logger.error("Errore list_sent_confirmation_orders: %s", exc)
        return []


def get_sent_confirmation_fingerprint() -> str:
    """Fingerprint leggero per refresh incrementale UI."""
    orders = list_sent_confirmation_orders(limit=200)
    if not orders:
        return "0"
    head = orders[0]
    return f"{len(orders)}:{head.get('order_id')}:{head.get('sent_timestamp')}"


def get_order_sent_confirmation_detail(order_id: str) -> Optional[Dict]:
    """Dettaglio ordine + email conferma inviata (SQLite)."""
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT order_id, client, client_email, product, status,
                   email_subject, email_body, validation_errors, created_at, updated_at
            FROM orders WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        info = _confirmation_from_validation_json(row["validation_errors"])
        if not info:
            return None
        return {
            "id": row["order_id"],
            "order_id": row["order_id"],
            "from": row["client_email"] or row["client"],
            "client_email": row["client_email"],
            "subject": row["email_subject"] or row["product"],
            "body": row["email_body"] or "",
            "status": row["status"],
            "sent_confirmation_email": info,
            "confirmation_email": info,
        }
    except Exception as exc:
        logger.error("Errore get_order_sent_confirmation_detail: %s", exc)
        return None


def import_sent_confirmations_from_json_dir(logs_dir: Path) -> int:
    """Migrazione: copia sent_confirmation_email da JSON legacy in SQLite."""
    imported = 0
    if not logs_dir.exists():
        return 0
    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        for order_file in logs_dir.glob("order_*.json"):
            try:
                data = json.loads(order_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            sent = data.get("sent_confirmation_email")
            if not isinstance(sent, dict) or not sent.get("sent"):
                continue
            order_id = data.get("id") or data.get("order_id")
            if not order_id:
                continue
            row = conn.execute(
                "SELECT validation_errors FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if not row:
                continue
            meta: Dict = {}
            if row[0]:
                try:
                    parsed = json.loads(row[0])
                    if isinstance(parsed, dict):
                        meta = parsed
                except json.JSONDecodeError:
                    pass
            if _confirmation_from_validation_json(json.dumps(meta) if meta else None):
                continue
            meta["sent_confirmation_email"] = sent
            conn.execute(
                """
                UPDATE orders SET validation_errors = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
                """,
                (json.dumps(meta, ensure_ascii=False), order_id),
            )
            imported += 1
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("import_sent_confirmations_from_json_dir: %s", exc)
    return imported


def delete_sent_confirmation(order_id: str, logs_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Rimuove definitivamente la registrazione dell'email di conferma inviata.

    Pulisce sia il DB (orders.validation_errors) sia il file JSON legacy
    (order_*.json), così il re-import all'avvio non la fa risorgere.
    L'ordine resta in tabella orders.
    """
    order_id = (order_id or "").strip()
    if not order_id:
        return False, "order_id mancante"

    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            row = conn.execute(
                "SELECT validation_errors FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if row is None:
                return False, f"Ordine {order_id} non trovato nel database"

            meta: Dict = {}
            if row[0]:
                try:
                    parsed = json.loads(row[0])
                    if isinstance(parsed, dict):
                        meta = parsed
                except json.JSONDecodeError:
                    meta = {}

            removed_db = False
            for key in ("sent_confirmation_email", "confirmation_email"):
                if meta.pop(key, None) is not None:
                    removed_db = True

            conn.execute(
                """
                UPDATE orders SET validation_errors = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
                """,
                (json.dumps(meta, ensure_ascii=False) if meta else None, order_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("delete_sent_confirmation DB (%s): %s", order_id, exc)
        return False, f"Errore database: {exc}"

    # Pulizia JSON legacy: senza questo passo il re-import all'avvio
    # ripristinerebbe la registrazione appena cancellata.
    removed_json = False
    if logs_dir is not None and logs_dir.exists():
        for order_file in logs_dir.glob("order_*.json"):
            try:
                data = json.loads(order_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, dict):
                continue
            if (data.get("id") or data.get("order_id")) != order_id:
                continue
            if "sent_confirmation_email" in data:
                data.pop("sent_confirmation_email", None)
                try:
                    order_file.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    removed_json = True
                except OSError as exc:
                    logger.error(
                        "delete_sent_confirmation JSON %s: %s", order_file.name, exc
                    )
                    return False, (
                        f"DB pulito, ma errore sul file {order_file.name}: {exc}. "
                        "La riga potrebbe riapparire al riavvio."
                    )

    if not removed_db and not removed_json:
        return False, f"Nessuna registrazione di invio trovata per {order_id}"

    parts = ["DB"] if removed_db else []
    if removed_json:
        parts.append("JSON")
    logger.info(
        "Registrazione invio conferma rimossa (%s) per ordine %s",
        "+".join(parts), order_id,
    )
    return True, f"Registrazione invio rimossa ({'+'.join(parts)}) per {order_id}"


def update_order_ai_fields(order_id: str, analysis: Dict) -> bool:
    """Aggiorna materiale/quantità/macchina dopo analisi AI manuale."""
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        cursor = conn.cursor()
        quantita = analysis.get("quantita_mq")
        try:
            quantita = float(quantita) if quantita is not None else None
        except (TypeError, ValueError):
            quantita = None
        cursor.execute(
            """
            UPDATE orders SET
                materiale = COALESCE(NULLIF(?, ''), materiale),
                quantita = COALESCE(?, quantita),
                machine = COALESCE(NULLIF(?, ''), machine),
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (
                analysis.get("materiale", ""),
                quantita,
                analysis.get("machine", ""),
                order_id,
            ),
        )
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        return updated
    except Exception as e:
        logger.error("Errore update ordine AI: %s", e)
        return False


def update_order_fields(order_id: str, fields: Dict) -> Dict:
    """Aggiorna campi ordine editabili dal pannello centrale Orders."""
    allowed = {
        "status",
        "email_body",
        "email_subject",
        "product",
        "materiale",
        "quantita",
        "machine",
        "client",
        "client_email",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return {"ok": False, "error": "Nessun campo valido da aggiornare"}
    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        existing = conn.execute(
            "SELECT order_id FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if not existing:
            conn.close()
            return {"ok": False, "error": f"Ordine {order_id} non trovato"}
        set_parts = []
        values: list = []
        for key, value in updates.items():
            if key == "quantita":
                try:
                    value = float(value) if value not in (None, "") else None
                except (TypeError, ValueError):
                    return {"ok": False, "error": "Quantità non valida"}
            set_parts.append(f"{key} = ?")
            values.append(value)
        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        values.append(order_id)
        conn.execute(
            f"UPDATE orders SET {', '.join(set_parts)} WHERE order_id = ?",
            values,
        )
        conn.commit()
        conn.close()
        return {"ok": True, "order_id": order_id}
    except Exception as exc:
        logger.error("Errore update ordine %s: %s", order_id, exc)
        return {"ok": False, "error": str(exc)}


def save_order(order_data: Dict, email_log_id: Optional[int] = None) -> Optional[int]:
    """
    Salva ordine nel database con validazione
    
    Args:
        order_data: Dizionario con dati ordine
        email_log_id: ID email_logs associato
        
    Returns:
        ID ordine inserito o None se errore
    """
    try:
        # Valida ordine
        is_valid, errors = validate_order(order_data)
        
        # Determina stato
        if is_valid:
            status = order_data.get("status", "NEW")
        else:
            status = "DA_VALIDARE"
        
        init_database()

        order_id = order_data.get("order_id", "")
        _, parsed_email = parseaddr(
            order_data.get("client_email") or order_data.get("from", "")
        )
        client_email = parsed_email or order_data.get("client_email") or order_data.get("from", "")
        client = order_data.get("client") or (
            client_email.split("@")[0] if "@" in client_email else client_email[:80]
        )
        product = order_data.get("product", order_data.get("subject", ""))
        materiale = order_data.get("materiale", "")
        quantita = order_data.get("quantita")
        machine = order_data.get("machine") or ""
        email_subject = order_data.get("subject", "")
        email_body = order_data.get("body", "")
        validation_errors = json.dumps(errors) if errors else None
        quotation_case_id = order_data.get("quotation_case_id") or ""
        
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO orders (
                order_id, email_id, client, client_email, product, materiale,
                quantita, machine, status, email_subject, email_body,
                validation_errors, quotation_case_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_id, email_log_id, client, client_email, product, materiale,
              quantita, machine, status, email_subject, email_body,
              validation_errors, quotation_case_id or None))
        
        order_db_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Ordine salvato: ID {order_db_id}, order_id: {order_id}, status: {status}")
        return order_db_id
        
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint" in str(e):
            logger.warning(f"Ordine già esistente: {order_id}")
        else:
            logger.error(f"Errore integrità database: {e}")
        return None
    except Exception as e:
        logger.error(f"Errore salvataggio ordine: {e}")
        return None


def save_invoice(invoice_number: str, order_id: str, file_path: str, 
                 client_email: str, amount_eur: Optional[float] = None) -> Optional[int]:
    """
    Salva fattura nel database
    
    Returns:
        ID fattura inserita o None se errore
    """
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO invoices (invoice_number, order_id, file_path, client_email, amount_eur)
            VALUES (?, ?, ?, ?, ?)
        """, (invoice_number, order_id, file_path, client_email, amount_eur))
        
        invoice_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Fattura salvata: ID {invoice_id}, invoice_number: {invoice_number}, order_id: {order_id}")
        return invoice_id
        
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint" in str(e):
            logger.warning(f"Fattura già esistente: {invoice_number}")
        else:
            logger.error(f"Errore integrità database: {e}")
        return None
    except Exception as e:
        logger.error(f"Errore salvataggio fattura: {e}")
        return None


def update_invoice_status(invoice_number: str, status: str, data_invio: Optional[str] = None) -> bool:
    """
    Aggiorna stato fattura
    
    Returns:
        True se aggiornamento riuscito
    """
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        if data_invio:
            cursor.execute("""
                UPDATE invoices 
                SET status = ?, data_invio = ?
                WHERE invoice_number = ?
            """, (status, data_invio, invoice_number))
        else:
            cursor.execute("""
                UPDATE invoices 
                SET status = ?
                WHERE invoice_number = ?
            """, (status, invoice_number))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Fattura aggiornata: {invoice_number}, status: {status}")
        return True
        
    except Exception as e:
        logger.error(f"Errore aggiornamento fattura: {e}")
        return False


# --- Centro Ordini Produzione ---

PRODUCTION_READY_STATUSES = ("CONFIRMED", "CONFIRMED_PARTIAL")
PRODUCTION_QUEUE_STATUSES = ("INVIATO", "IN PRODUZIONE", "COMPLETATO")

MACHINE_UI_TO_DB = {
    "Multifilo": "multifilo",
    "Lucidatrice": "lucidatrice",
    "CNC": "cnc",
}
MACHINE_DB_TO_UI = {v: k for k, v in MACHINE_UI_TO_DB.items()}


def normalize_machine_key(machine: Optional[str]) -> str:
    m = (machine or "").strip().lower()
    aliases = {
        "multifilo": "multifilo",
        "lucidatrice": "lucidatrice",
        "cnc": "cnc",
    }
    for key, canonical in aliases.items():
        if key in m or m == key:
            return canonical
    return m


def _row_to_production_dict(row: sqlite3.Row) -> Dict:
    data = dict(row)
    materiale = (data.get("materiale") or data.get("product") or "").strip()
    quantita = data.get("quantita")
    qty_label = f"{quantita:g} mq" if quantita is not None else "N/A"
    machine_key = normalize_machine_key(data.get("machine"))
    scheduled = data.get("scheduled") or data.get("updated_at") or data.get("created_at") or ""
    status = (data.get("status") or "").upper()
    queue_stato = "IN ARRIVO"
    if status == "IN PRODUZIONE":
        queue_stato = "IN PRODUZIONE"
    elif status == "COMPLETATO":
        queue_stato = "COMPLETATO"

    return {
        **data,
        "materiale": materiale,
        "codice": data.get("order_id"),
        "cliente": data.get("client"),
        "quantita": qty_label,
        "quantita_mq": quantita,
        "timestamp": scheduled,
        "destinazione": MACHINE_DB_TO_UI.get(machine_key, data.get("machine") or ""),
        "stato": queue_stato,
    }


def get_orders_sent_production(limit: int = 100) -> List[Dict]:
    """Ordini già inviati a una macchina (qualsiasi linea)."""
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return []
        placeholders = ",".join("?" * len(PRODUCTION_QUEUE_STATUSES))
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, order_id, client, client_email, product, materiale, quantita,
                   machine, status, scheduled, created_at, updated_at
            FROM orders
            WHERE UPPER(status) IN ({placeholders})
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (*PRODUCTION_QUEUE_STATUSES, limit),
        ).fetchall()
        conn.close()
        return [_row_to_production_dict(r) for r in rows]
    except Exception as e:
        logger.error("Errore ordini inviati produzione: %s", e)
        return []


def get_orders_production_overview(limit: int = 100) -> List[Dict]:
    """Confermati + inviati + in lavorazione (vista completa produzione)."""
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return []
        statuses = PRODUCTION_READY_STATUSES + PRODUCTION_QUEUE_STATUSES
        placeholders = ",".join("?" * len(statuses))
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, order_id, client, client_email, product, materiale, quantita,
                   machine, status, scheduled, created_at, updated_at
            FROM orders
            WHERE UPPER(status) IN ({placeholders})
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (*statuses, limit),
        ).fetchall()
        conn.close()
        return [_row_to_production_dict(r) for r in rows]
    except Exception as e:
        logger.error("Errore overview produzione: %s", e)
        return []


def get_orders_pending_production(limit: int = 100) -> List[Dict]:
    """Ordini confermati, pronti per invio a produzione."""
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return []
        placeholders = ",".join("?" * len(PRODUCTION_READY_STATUSES))
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, order_id, client, client_email, product, materiale, quantita,
                   machine, status, scheduled, created_at, updated_at
            FROM orders
            WHERE UPPER(status) IN ({placeholders})
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (*PRODUCTION_READY_STATUSES, limit),
        ).fetchall()
        conn.close()
        return [_row_to_production_dict(r) for r in rows]
    except Exception as e:
        logger.error("Errore ordini pending produzione: %s", e)
        return []


def get_orders_for_machine(machine_ui: str, limit: int = 50) -> List[Dict]:
    """Ordini già inviati a una macchina (coda persistita)."""
    machine_db = MACHINE_UI_TO_DB.get(machine_ui, normalize_machine_key(machine_ui))
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return []
        placeholders = ",".join("?" * len(PRODUCTION_QUEUE_STATUSES))
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, order_id, client, client_email, product, materiale, quantita,
                   machine, status, scheduled, created_at, updated_at
            FROM orders
            WHERE LOWER(TRIM(machine)) = ?
              AND UPPER(status) IN ({placeholders})
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (machine_db, *PRODUCTION_QUEUE_STATUSES, limit),
        ).fetchall()
        conn.close()
        return [_row_to_production_dict(r) for r in rows]
    except Exception as e:
        logger.error("Errore ordini macchina %s: %s", machine_ui, e)
        return []


def assign_order_to_machine(order_id: str, machine_ui: str) -> Tuple[bool, str]:
    """
    Assegna ordine a macchina e imposta status INVIATO.
    Returns (ok, message).
    """
    machine_db = MACHINE_UI_TO_DB.get(machine_ui)
    if not machine_db:
        return False, f"Macchina non valida: {machine_ui}"

    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, machine FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if not row:
            conn.close()
            return False, "Ordine non trovato"

        status = (row["status"] or "").upper()
        if status in PRODUCTION_QUEUE_STATUSES:
            conn.close()
            return False, f"Ordine già in produzione (stato {status})"
        if status not in PRODUCTION_READY_STATUSES:
            conn.close()
            return (
                False,
                f"Ordine non confermato (stato {status}). "
                "Solo CONFIRMED / CONFIRMED_PARTIAL possono essere inviati.",
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """
            UPDATE orders SET
                machine = ?,
                status = 'INVIATO',
                scheduled = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (machine_db, now, order_id),
        )
        conn.commit()
        conn.close()
        logger.info("Ordine %s inviato a %s", order_id, machine_db)
        return True, f"Ordine inviato a {machine_ui}"
    except Exception as e:
        logger.error("Errore assign ordine %s: %s", order_id, e)
        return False, str(e)


def update_order_production_status(order_id: str, status: str) -> bool:
    """Aggiorna stato ordine in coda produzione (es. IN PRODUZIONE, COMPLETATO)."""
    status = (status or "").upper()
    if status not in PRODUCTION_QUEUE_STATUSES:
        return False
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.execute(
            """
            UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (status, order_id),
        )
        conn.commit()
        ok = conn.total_changes > 0
        conn.close()
        return ok
    except Exception as e:
        logger.error("Errore update stato produzione %s: %s", order_id, e)
        return False


def get_order_for_production(order_id: str) -> Optional[Dict]:
    """Dettaglio ordine per Centro Produzione."""
    try:
        init_database()
        db_path = get_database_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, order_id, client, client_email, product, materiale, quantita,
                   machine, status, scheduled, created_at, updated_at, email_subject
            FROM orders WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()
        conn.close()
        return _row_to_production_dict(row) if row else None
    except Exception as e:
        logger.error("Errore lettura ordine produzione %s: %s", order_id, e)
        return None


def delete_order(order_id: str) -> bool:
    """Elimina un ordine dal database per order_id."""
    if not order_id:
        return False
    try:
        init_database()
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
        deleted = cursor.rowcount > 0
        if deleted:
            cursor.execute(
                "UPDATE email_logs SET order_id = NULL WHERE order_id = ?",
                (order_id,),
            )
        conn.commit()
        conn.close()
        if deleted:
            logger.info("Ordine eliminato: %s", order_id)
        return deleted
    except Exception as e:
        logger.error("Errore eliminazione ordine %s: %s", order_id, e)
        return False


def delete_orders(order_ids: List[str]) -> int:
    """Elimina più ordini; ritorna il numero eliminati."""
    count = 0
    for oid in order_ids:
        if delete_order(oid):
            count += 1
    return count


def get_orders_by_status(status: str) -> List[Dict]:
    """
    Recupera ordini per stato
    
    Returns:
        Lista di dizionari con dati ordini
    """
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC
        """, (status,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        logger.error(f"Errore recupero ordini: {e}")
        return []


def get_invoices_by_order(order_id: str) -> List[Dict]:
    """
    Recupera fatture per ordine
    
    Returns:
        Lista di dizionari con dati fatture
    """
    try:
        db_path = get_database_path()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM invoices WHERE order_id = ? ORDER BY created_at DESC
        """, (order_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        logger.error(f"Errore recupero fatture: {e}")
        return []

