"""
Audit log retrieval per Retrieval Fabric.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from modules.knowledge_db import get_database_path, init_knowledge_tables


def log_retrieval(
    *,
    question: str,
    context_key: str = "general",
    hits: Optional[List[Dict[str, Any]]] = None,
    answer_preview: str = "",
    module: str = "retrieval_fabric",
) -> int:
    init_knowledge_tables()
    sources = []
    for hit in hits or []:
        sources.append(
            {
                "file_name": hit.get("file_name"),
                "section_title": hit.get("section_title"),
                "chunk_id": hit.get("chunk_id"),
                "chunk_index": hit.get("chunk_index"),
                "score": hit.get("score"),
            }
        )
    conn = sqlite3.connect(str(get_database_path()), timeout=5.0)
    try:
        cur = conn.execute(
            """
            INSERT INTO knowledge_retrieval_log
            (context_key, question, sources_json, answer_preview, module)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                context_key,
                question.strip(),
                json.dumps(sources, ensure_ascii=False),
                (answer_preview or "")[:2000],
                module,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_logs(*, limit: int = 100) -> List[Dict[str, Any]]:
    init_knowledge_tables()
    conn = sqlite3.connect(str(get_database_path()), timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, context_key, question, sources_json,
                   answer_preview, module
            FROM knowledge_retrieval_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["sources"] = json.loads(item.pop("sources_json") or "[]")
            except json.JSONDecodeError:
                item["sources"] = []
            out.append(item)
        return out
    finally:
        conn.close()
