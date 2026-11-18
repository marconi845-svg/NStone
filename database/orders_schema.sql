-- ============================================================================
-- NStone Orders & Invoices Schema (SQLite extension)
-- Additive: run after schema.sql. Safe on existing DBs.
-- ============================================================================

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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
);

-- Extend core orders table when columns are missing (SQLite ignores duplicates via init helper)
-- Columns applied by init_db.py via PRAGMA-aware ALTERs:
--   email_id, client_email, materiale, quantita, email_subject, email_body, validation_errors

CREATE INDEX IF NOT EXISTS idx_email_logs_tipo ON email_logs(tipo_email);
CREATE INDEX IF NOT EXISTS idx_email_logs_timestamp ON email_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_email_logs_processed ON email_logs(processed);
CREATE INDEX IF NOT EXISTS idx_email_logs_order_id ON email_logs(order_id);

CREATE INDEX IF NOT EXISTS idx_invoices_order_id ON invoices(order_id);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);

CREATE TRIGGER IF NOT EXISTS update_invoices_timestamp
    AFTER UPDATE ON invoices
    BEGIN
        UPDATE invoices SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_order_status_on_invoice_sent
    AFTER UPDATE OF status ON invoices
    WHEN NEW.status = 'INVIATA' AND OLD.status != 'INVIATA'
    BEGIN
        UPDATE orders SET status = 'FATTURATO' WHERE order_id = NEW.order_id;
    END;
