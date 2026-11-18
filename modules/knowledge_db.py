"""
Knowledge base — DB path, schema, cartella documenti MD.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ROOT = PROJECT_ROOT / "data" / "knowledge"

DOC_TYPES = ("price_list", "procedure", "catalog", "general")

_SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document
    ON knowledge_chunks(document_id);

CREATE TABLE IF NOT EXISTS knowledge_retrieval_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    context_key TEXT,
    question TEXT NOT NULL,
    sources_json TEXT,
    answer_preview TEXT,
    module TEXT DEFAULT 'retrieval_fabric'
);

CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_log_created
    ON knowledge_retrieval_log(created_at DESC);
"""


def get_database_path() -> Path:
    try:
        from modules.orders_database import get_database_path as _gp

        return _gp()
    except ImportError:
        path = PROJECT_ROOT / "data" / "nstonellm.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def ensure_knowledge_root() -> Path:
    KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)
    return KNOWLEDGE_ROOT


def init_knowledge_tables(db_path: Optional[Path] = None) -> None:
    path = db_path or get_database_path()
    conn = sqlite3.connect(str(path), timeout=5.0)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
