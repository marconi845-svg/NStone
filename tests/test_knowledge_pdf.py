"""Tests PDF → Markdown per Retrieval Fabric."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


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

    from modules.knowledge_db import init_knowledge_tables

    init_knowledge_tables(db)
    return {"db": db, "knowledge": knowledge}


def test_table_to_markdown():
    from modules.knowledge_pdf import table_to_markdown

    md = table_to_markdown([["A", "B"], ["1", "2"]])
    assert "| A | B |" in md
    assert "| --- | --- |" in md
    assert "| 1 | 2 |" in md


def test_table_escapes_pipes():
    from modules.knowledge_pdf import table_to_markdown

    md = table_to_markdown([["x|y", "z"]])
    assert r"x\|y" in md


def test_pdf_to_markdown_pymupdf_fallback(monkeypatch, tmp_path: Path):
    from modules import knowledge_pdf

    pdf = tmp_path / "listino_test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(
        knowledge_pdf,
        "pdf_libraries_status",
        lambda: {"pdfplumber": False, "pymupdf": True},
    )

    class _FakePage:
        def get_text(self, _mode):
            return "Carrara lucido 85 EUR"

    class _FakeDoc:
        def __len__(self):
            return 1

        def __getitem__(self, idx):
            return _FakePage()

        def close(self):
            pass

    import types

    fake_fitz = types.SimpleNamespace(open=lambda _p: _FakeDoc())
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    md = knowledge_pdf.pdf_to_markdown(pdf)
    assert "# Listino Test" in md
    assert "Carrara lucido" in md


def test_import_pdf_file_indexes(knowledge_env, monkeypatch, tmp_path: Path):
    from modules import knowledge_pdf
    from modules.knowledge_ingest import list_documents, read_document_text

    pdf = tmp_path / "listino_marmo.pdf"
    pdf.write_bytes(b"%PDF")

    monkeypatch.setattr(
        knowledge_pdf,
        "pdf_to_markdown",
        lambda _p: "# Listino\n\n## Page 1\n\n| Codice | € |\n| --- | --- |\n| X | 85 |",
    )

    result = knowledge_pdf.import_pdf_file(pdf)
    assert result["status"] == "indexed"
    assert result["chunks"] >= 1

    docs = list_documents()
    assert len(docs) == 1
    assert docs[0]["doc_type"] == "price_list"
    text = read_document_text(docs[0]["id"])
    assert "85" in text


def test_pdf_import_unavailable_raises(monkeypatch, tmp_path: Path):
    from modules import knowledge_pdf

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"x")
    monkeypatch.setattr(
        knowledge_pdf,
        "pdf_libraries_status",
        lambda: {"pdfplumber": False, "pymupdf": False},
    )
    with pytest.raises(RuntimeError, match="pdfplumber"):
        knowledge_pdf.pdf_to_markdown(pdf)
