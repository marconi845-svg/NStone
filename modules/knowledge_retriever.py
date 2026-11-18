"""
Recupero chunk da knowledge base (Retrieval Fabric).
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, List, Optional

from modules.knowledge_db import init_knowledge_tables, get_database_path


def _tokenize(query: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z0-9àèéìòù]+", query.lower())
    return [t for t in tokens if len(t) >= 2]


def retrieve(
    query: str,
    *,
    context_key: str = "general",
    limit: int = 5,
    doc_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Ricerca keyword sui chunk indicizzati."""
    del context_key  # riservato per filtri futuri per contesto LLM
    init_knowledge_tables()
    tokens = _tokenize(query)
    if not tokens:
        return []

    conn = sqlite3.connect(str(get_database_path()), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT c.id AS chunk_id, c.chunk_index, c.section_title, c.content,
                   d.id AS document_id, d.file_name, d.doc_type
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.id = c.document_id
        """
        params: List[Any] = []
        if doc_type:
            sql += " WHERE d.doc_type = ?"
            params.append(doc_type)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    scored: List[Dict[str, Any]] = []
    for row in rows:
        hay = f"{row['section_title']} {row['content']} {row['file_name']}".lower()
        score = sum(hay.count(tok) for tok in tokens)
        if score <= 0:
            continue
        scored.append(
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "chunk_index": row["chunk_index"],
                "section_title": row["section_title"] or "",
                "content": row["content"],
                "file_name": row["file_name"],
                "doc_type": row["doc_type"],
                "score": float(score),
            }
        )

    scored.sort(key=lambda x: (-x["score"], x["file_name"], x["chunk_index"]))
    return scored[: max(1, limit)]


def format_context_block(hits: List[Dict[str, Any]]) -> str:
    if not hits:
        return ""
    parts = ["[KNOWLEDGE BASE CONTEXT]"]
    for i, hit in enumerate(hits, 1):
        section = hit.get("section_title") or "—"
        parts.append(
            f"\n--- Source {i}: {hit['file_name']} § {section} (score {hit['score']:.0f}) ---\n"
            f"{hit['content']}\n"
        )
    parts.append(
        "\nUse ONLY facts from the sources above for prices, codes, and stock. "
        "If missing, say data is not in the knowledge base."
    )
    return "\n".join(parts)


def format_sources_summary(hits: List[Dict[str, Any]]) -> str:
    if not hits:
        return "No matching sources in knowledge base."
    lines = []
    for hit in hits:
        section = hit.get("section_title") or "—"
        lines.append(
            f"• {hit['file_name']} § {section} — chunk #{hit['chunk_index']} (score {hit['score']:.0f})"
        )
    return "\n".join(lines)
