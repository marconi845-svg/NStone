"""
Indicizzazione documenti Markdown per Retrieval Fabric.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.knowledge_db import (
    DOC_TYPES,
    ensure_knowledge_root,
    get_database_path,
    init_knowledge_tables,
)

_CHUNK_MAX = 900


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def infer_doc_type(file_name: str) -> str:
    name = file_name.lower()
    if any(k in name for k in ("listino", "price", "prezzi", "tariff")):
        return "price_list"
    if any(k in name for k in ("catalog", "catalogo", "stock")):
        return "catalog"
    if any(k in name for k in ("procedure", "procedur", "policy", "guida")):
        return "procedure"
    return "general"


def chunk_markdown(text: str) -> List[Dict[str, str]]:
    """Spezza MD per heading ## oppure paragrafi."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    sections: List[Dict[str, str]] = []
    parts = re.split(r"(?m)^##\s+(.+)$", text)
    if len(parts) > 1:
        intro = parts[0].strip()
        if intro:
            sections.append({"section_title": "Introduction", "content": intro})
        for i in range(1, len(parts), 2):
            title = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if body:
                sections.append({"section_title": title, "content": body})
    else:
        sections.append({"section_title": "", "content": text})

    chunks: List[Dict[str, str]] = []
    for sec in sections:
        body = sec["content"]
        title = sec["section_title"]
        if len(body) <= _CHUNK_MAX:
            chunks.append({"section_title": title, "content": body})
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        buf = ""
        for para in paragraphs:
            candidate = f"{buf}\n\n{para}".strip() if buf else para
            if len(candidate) <= _CHUNK_MAX:
                buf = candidate
            else:
                if buf:
                    chunks.append({"section_title": title, "content": buf})
                buf = para[:_CHUNK_MAX]
        if buf:
            chunks.append({"section_title": title, "content": buf})
    return chunks


def list_documents() -> List[Dict[str, Any]]:
    init_knowledge_tables()
    conn = sqlite3.connect(str(get_database_path()), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, file_name, file_path, doc_type, content_hash,
                   chunk_count, indexed_at, updated_at
            FROM knowledge_documents
            ORDER BY file_name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def read_document_text(doc_id: int) -> str:
    row = get_document(doc_id)
    if not row:
        return ""
    path = Path(row["file_path"])
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
    init_knowledge_tables()
    conn = sqlite3.connect(str(get_database_path()), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def index_file(
    file_path: Path,
    *,
    doc_type: Optional[str] = None,
    copy_to_knowledge_root: bool = True,
) -> Dict[str, Any]:
    init_knowledge_tables()
    ensure_knowledge_root()
    src = Path(file_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    if src.suffix.lower() != ".md":
        raise ValueError("Solo file .md supportati in questa versione.")

    text = src.read_text(encoding="utf-8", errors="replace")
    content_hash = _file_hash(text)
    dtype = doc_type or infer_doc_type(src.name)

    dest = src
    if copy_to_knowledge_root:
        dest = ensure_knowledge_root() / src.name
        if dest.resolve() != src:
            dest.write_text(text, encoding="utf-8")

    chunks = chunk_markdown(text)
    now = _now_iso()
    conn = sqlite3.connect(str(get_database_path()), timeout=10.0)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        existing = conn.execute(
            "SELECT id, content_hash FROM knowledge_documents WHERE file_path = ?",
            (str(dest),),
        ).fetchone()
        if existing and existing[1] == content_hash:
            return {"status": "unchanged", "document_id": existing[0], "chunks": len(chunks)}

        if existing:
            doc_id = existing[0]
            conn.execute(
                """
                UPDATE knowledge_documents
                SET file_name = ?, doc_type = ?, content_hash = ?,
                    chunk_count = ?, indexed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (dest.name, dtype, content_hash, len(chunks), now, now, doc_id),
            )
            conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (doc_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO knowledge_documents
                (file_name, file_path, doc_type, content_hash, chunk_count, indexed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (dest.name, str(dest), dtype, content_hash, len(chunks), now, now),
            )
            doc_id = int(cur.lastrowid)

        for idx, ch in enumerate(chunks):
            conn.execute(
                """
                INSERT INTO knowledge_chunks (document_id, chunk_index, section_title, content)
                VALUES (?, ?, ?, ?)
                """,
                (doc_id, idx, ch.get("section_title") or "", ch["content"]),
            )
        conn.commit()
        return {"status": "indexed", "document_id": doc_id, "chunks": len(chunks)}
    finally:
        conn.close()


def index_paths(paths: List[Path]) -> List[Dict[str, Any]]:
    results = []
    for p in paths:
        try:
            results.append({"path": str(p), **index_file(p)})
        except Exception as exc:
            results.append({"path": str(p), "status": "error", "error": str(exc)})
    return results


def reindex_all() -> int:
    ensure_knowledge_root()
    md_files = sorted(ensure_knowledge_root().glob("*.md"))
    count = 0
    for md in md_files:
        result = index_file(md, copy_to_knowledge_root=False)
        if result.get("status") in ("indexed", "unchanged"):
            count += 1
    return count


def remove_document(doc_id: int, *, delete_file: bool = False) -> bool:
    init_knowledge_tables()
    conn = sqlite3.connect(str(get_database_path()), timeout=5.0)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute(
            "SELECT file_path FROM knowledge_documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM knowledge_documents WHERE id = ?", (doc_id,))
        conn.commit()
        if delete_file:
            path = Path(row[0])
            if path.is_file():
                path.unlink()
        return True
    finally:
        conn.close()


def stats_summary() -> Dict[str, Any]:
    init_knowledge_tables()
    conn = sqlite3.connect(str(get_database_path()), timeout=5.0)
    try:
        docs = conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
        return {"documents": int(docs), "chunks": int(chunks)}
    finally:
        conn.close()
