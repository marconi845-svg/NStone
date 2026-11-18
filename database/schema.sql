-- ============================================================================
-- NStone Database Schema (SQLite)
-- ============================================================================

-- Tabella: online_stock
-- Gestisce lo stock dei materiali disponibili
CREATE TABLE IF NOT EXISTS online_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    color TEXT NOT NULL,
    origin TEXT NOT NULL,
    finish TEXT NOT NULL,
    thickness REAL NOT NULL,
    dimensions TEXT NOT NULL,
    stock REAL NOT NULL,
    price REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabella: quotations
-- Gestisce i preventivi per i clienti
CREATE TABLE IF NOT EXISTS quotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT NOT NULL,
    materiale TEXT NOT NULL,
    numero_blocco TEXT NOT NULL,
    misure_cm TEXT NOT NULL,
    quantita_mq REAL NOT NULL,
    prezzo_mq REAL NOT NULL,
    status INTEGER NOT NULL DEFAULT 0,
    valid_until DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabella: orders
-- Gestisce gli ordini di produzione
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL UNIQUE,
    client TEXT NOT NULL,
    product TEXT NOT NULL,
    machine TEXT NOT NULL,
    status TEXT NOT NULL,
    scheduled TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabella: collection
-- Gestisce i trasporti e le consegne
CREATE TABLE IF NOT EXISTS collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transporter TEXT NOT NULL,
    transport_id TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    driver TEXT,
    eta TEXT,
    destination TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabella: production
-- Gestisce lo stato delle macchine di produzione
CREATE TABLE IF NOT EXISTS production (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine TEXT NOT NULL,
    status TEXT NOT NULL,
    current_work TEXT,
    completion INTEGER NOT NULL DEFAULT 0,
    efficiency REAL NOT NULL DEFAULT 0.0,
    consumption REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabella: administration
-- Gestisce le fatture e l'amministrazione
CREATE TABLE IF NOT EXISTS administration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL UNIQUE,
    client TEXT NOT NULL,
    amount_eur REAL NOT NULL,
    date DATE NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Indici per migliorare le performance delle query
-- ============================================================================

-- Indici per online_stock
CREATE INDEX IF NOT EXISTS idx_online_stock_type ON online_stock(type);
CREATE INDEX IF NOT EXISTS idx_online_stock_color ON online_stock(color);
CREATE INDEX IF NOT EXISTS idx_online_stock_origin ON online_stock(origin);

-- Indici per quotations
CREATE INDEX IF NOT EXISTS idx_quotations_cliente ON quotations(cliente);
CREATE INDEX IF NOT EXISTS idx_quotations_status ON quotations(status);
CREATE INDEX IF NOT EXISTS idx_quotations_valid_until ON quotations(valid_until);

-- Indici per orders
CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_machine ON orders(machine);

-- Indici per collection
CREATE INDEX IF NOT EXISTS idx_collection_transport_id ON collection(transport_id);
CREATE INDEX IF NOT EXISTS idx_collection_status ON collection(status);
CREATE INDEX IF NOT EXISTS idx_collection_destination ON collection(destination);

-- Indici per production
CREATE INDEX IF NOT EXISTS idx_production_machine ON production(machine);
CREATE INDEX IF NOT EXISTS idx_production_status ON production(status);

-- Indici per administration
CREATE INDEX IF NOT EXISTS idx_administration_invoice_number ON administration(invoice_number);
CREATE INDEX IF NOT EXISTS idx_administration_client ON administration(client);
CREATE INDEX IF NOT EXISTS idx_administration_status ON administration(status);
CREATE INDEX IF NOT EXISTS idx_administration_date ON administration(date);

CREATE TABLE IF NOT EXISTS incoming_request (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    nome TEXT NOT NULL,
    email TEXT NOT NULL,
    messaggio TEXT NOT NULL,
    stato TEXT NOT NULL DEFAULT 'NUOVA',
    risposta_gemini TEXT,
    data_elaborazione TEXT,
    email_inviata INTEGER,
    data_invio_email TEXT,
    errore_email TEXT,
    updated_at TEXT
);

-- Tabella: app_user (workstation operators / administrators)
CREATE TABLE IF NOT EXISTS app_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

-- Tabella: compliance_profile (AI Governance — employer / GDPR register)
CREATE TABLE IF NOT EXISTS compliance_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    employer_name TEXT NOT NULL DEFAULT '',
    employer_vat TEXT NOT NULL DEFAULT '',
    dpo_name TEXT NOT NULL DEFAULT '',
    dpo_email TEXT NOT NULL DEFAULT '',
    workplace_site TEXT NOT NULL DEFAULT '',
    ai_system_name TEXT NOT NULL DEFAULT 'NStone',
    ai_system_version TEXT NOT NULL DEFAULT '',
    legal_rep_name TEXT NOT NULL DEFAULT '',
    processing_purposes TEXT NOT NULL DEFAULT '',
    legal_basis TEXT NOT NULL DEFAULT 'Legittimo interesse / esecuzione contratto (art. 6 GDPR)',
    retention_days INTEGER NOT NULL DEFAULT 365,
    llm_provider_note TEXT NOT NULL DEFAULT '',
    worker_notice_version TEXT NOT NULL DEFAULT '1.0',
    worker_notice_published_at TEXT NOT NULL DEFAULT '',
    dpia_completed INTEGER NOT NULL DEFAULT 0,
    dpia_reviewed_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT
);

-- Tabella: compliance_checklist (requirement tracking L.132 / GDPR / AI Act)
CREATE TABLE IF NOT EXISTS compliance_checklist (
    req_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'open',
    evidence_note TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    updated_by TEXT NOT NULL DEFAULT ''
);

-- Tabella: compliance_worker_ack (worker information acknowledgments)
CREATE TABLE IF NOT EXISTS compliance_worker_ack (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_name TEXT NOT NULL,
    worker_role TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    notice_version TEXT NOT NULL,
    acknowledged_at TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'in_app',
    notes TEXT NOT NULL DEFAULT ''
);

-- Tabella: section_password (Access Control — section PINs)
CREATE TABLE IF NOT EXISTS section_password (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL DEFAULT '',
    protection_enabled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

-- ============================================================================
-- Trigger per aggiornare updated_at automaticamente
-- ============================================================================

CREATE TRIGGER IF NOT EXISTS update_online_stock_timestamp 
    AFTER UPDATE ON online_stock
    BEGIN
        UPDATE online_stock SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_quotations_timestamp 
    AFTER UPDATE ON quotations
    BEGIN
        UPDATE quotations SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_orders_timestamp 
    AFTER UPDATE ON orders
    BEGIN
        UPDATE orders SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_collection_timestamp 
    AFTER UPDATE ON collection
    BEGIN
        UPDATE collection SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_production_timestamp 
    AFTER UPDATE ON production
    BEGIN
        UPDATE production SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_administration_timestamp 
    AFTER UPDATE ON administration
    BEGIN
        UPDATE administration SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

-- Retrieval Fabric — knowledge documents (Markdown)
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    doc_type TEXT NOT NULL DEFAULT 'general',
    content_hash TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    indexed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    section_title TEXT,
    content TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document ON knowledge_chunks(document_id);

CREATE TABLE IF NOT EXISTS knowledge_retrieval_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    context_key TEXT,
    question TEXT NOT NULL,
    sources_json TEXT,
    answer_preview TEXT,
    module TEXT DEFAULT 'retrieval_fabric'
);

CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_log_created ON knowledge_retrieval_log(created_at DESC);


