"""Tests for Retrieval Fabric — knowledge ingest, retrieve, audit."""
from __future__ import annotations

from pathlib import Path

import pytest

SAMPLE_MD = """# Carrara CD — Listino test

## Lucido 2 cm
| Codice | Finitura | €/m² |
|--------|----------|------|
| CAR-LUC-20 | Lucido | 85.00 |

## Regole
Sconto oltre 200 m²: -5% su accordo commerciale.
"""


@pytest.fixture
def knowledge_env(tmp_path: Path, monkeypatch):
    """Isolated DB + knowledge folder."""
    db = tmp_path / "nstonellm.db"
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()

    monkeypatch.setattr("modules.knowledge_db.get_database_path", lambda: db)
    monkeypatch.setattr("modules.knowledge_db.KNOWLEDGE_ROOT", knowledge)
    monkeypatch.setattr("modules.knowledge_ingest.get_database_path", lambda: db)
    monkeypatch.setattr("modules.knowledge_retriever.get_database_path", lambda: db)
    monkeypatch.setattr("modules.knowledge_audit_db.get_database_path", lambda: db)

    from modules.knowledge_db import init_knowledge_tables

    init_knowledge_tables(db)
    return {"db": db, "knowledge": knowledge}


def test_chunk_markdown_splits_sections():
    from modules.knowledge_ingest import chunk_markdown

    chunks = chunk_markdown(SAMPLE_MD)
    assert len(chunks) >= 2
    titles = [c.get("section_title", "") for c in chunks]
    assert any("Lucido" in t for t in titles)


def test_index_and_list_document(knowledge_env):
    from modules.knowledge_ingest import index_file, list_documents, read_document_text

    md = knowledge_env["knowledge"] / "listino_carrara_test.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")

    result = index_file(md, copy_to_knowledge_root=False)
    assert result["status"] == "indexed"
    assert result["chunks"] >= 2

    docs = list_documents()
    assert len(docs) == 1
    assert docs[0]["file_name"] == "listino_carrara_test.md"
    assert docs[0]["doc_type"] == "price_list"

    text = read_document_text(docs[0]["id"])
    assert "Carrara" in text


def test_reindex_unchanged(knowledge_env):
    from modules.knowledge_ingest import index_file

    md = knowledge_env["knowledge"] / "listino.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    first = index_file(md, copy_to_knowledge_root=False)
    second = index_file(md, copy_to_knowledge_root=False)
    assert first["status"] == "indexed"
    assert second["status"] == "unchanged"


def test_retrieve_finds_carrara_price(knowledge_env):
    from modules.knowledge_ingest import index_file
    from modules.knowledge_retriever import format_context_block, retrieve

    md = knowledge_env["knowledge"] / "listino_carrara.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    index_file(md, copy_to_knowledge_root=False)

    hits = retrieve("Prezzo Carrara lucido 2 cm EX WORKS", limit=5)
    assert len(hits) >= 1
    assert any("85" in h["content"] or "Carrara" in h["content"] for h in hits)

    ctx = format_context_block(hits)
    assert "KNOWLEDGE BASE CONTEXT" in ctx
    assert "listino_carrara.md" in ctx


def test_audit_log(knowledge_env):
    from modules.knowledge_audit_db import list_logs, log_retrieval

    log_id = log_retrieval(
        question="Test query Carrara",
        context_key="Offerte",
        hits=[
            {
                "file_name": "x.md",
                "section_title": "Lucido",
                "chunk_id": 1,
                "chunk_index": 0,
                "score": 3.0,
            }
        ],
        answer_preview="Risposta di test",
    )
    assert log_id >= 1

    logs = list_logs(limit=10)
    assert len(logs) >= 1
    assert logs[0]["question"] == "Test query Carrara"
    assert len(logs[0]["sources"]) == 1


def test_remove_document(knowledge_env):
    from modules.knowledge_ingest import index_file, list_documents, remove_document

    md = knowledge_env["knowledge"] / "temp.md"
    md.write_text("# Temp\nBody", encoding="utf-8")
    result = index_file(md, copy_to_knowledge_root=False)
    doc_id = result["document_id"]

    assert remove_document(doc_id, delete_file=False) is True
    assert len(list_documents()) == 0
    assert md.is_file()


def test_stats_summary(knowledge_env):
    from modules.knowledge_ingest import index_file, stats_summary

    md = knowledge_env["knowledge"] / "a.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    index_file(md, copy_to_knowledge_root=False)

    stats = stats_summary()
    assert stats["documents"] == 1
    assert stats["chunks"] >= 1


def test_infer_doc_type():
    from modules.knowledge_ingest import infer_doc_type

    assert infer_doc_type("listino_marmo_2026.md") == "price_list"
    assert infer_doc_type("procedure_taglio.md") == "procedure"
    assert infer_doc_type("notes.md") == "general"
