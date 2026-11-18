"""
PDF → Markdown per Retrieval Fabric (pdfplumber + fallback PyMuPDF).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.knowledge_db import ensure_knowledge_root
from modules.knowledge_ingest import index_file, infer_doc_type


def pdf_libraries_status() -> Dict[str, bool]:
    """Stato dipendenze opzionali."""
    has_plumber = False
    has_mupdf = False
    try:
        import pdfplumber  # noqa: F401

        has_plumber = True
    except ImportError:
        pass
    try:
        import fitz  # noqa: F401

        has_mupdf = True
    except ImportError:
        pass
    return {"pdfplumber": has_plumber, "pymupdf": has_mupdf}


def pdf_import_available() -> bool:
    return any(pdf_libraries_status().values())


def _missing_deps_message() -> str:
    return (
        "Import PDF richiede almeno una di:\n"
        "  pip install pdfplumber\n"
        "  pip install pymupdf\n"
        "Oppure: pip install -r requirements-knowledge.txt"
    )


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    return text.replace("|", "\\|")


def table_to_markdown(rows: List[List[Any]]) -> str:
    """Converte righe tabella in markdown pipe-table."""
    if not rows:
        return ""
    normalized: List[List[str]] = []
    for row in rows:
        if not row:
            continue
        cells = [_clean_cell(c) for c in row]
        if any(cells):
            normalized.append(cells)
    if not normalized:
        return ""

    width = max(len(r) for r in normalized)
    padded = [r + [""] * (width - len(r)) for r in normalized]
    header = padded[0]
    sep = ["---"] * width
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for row in padded[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _page_block(page_num: int, body_parts: List[str]) -> str:
    body = "\n\n".join(p for p in body_parts if p.strip())
    if not body.strip():
        return ""
    return f"## Page {page_num}\n\n{body.strip()}"


def _pdf_to_markdown_pdfplumber(pdf_path: Path) -> str:
    import pdfplumber

    blocks: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            parts: List[str] = []
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(text)

            tables = page.extract_tables() or []
            for table in tables:
                md_table = table_to_markdown(table)
                if md_table:
                    parts.append(md_table)

            block = _page_block(idx, parts)
            if block:
                blocks.append(block)

    title = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    if not blocks:
        return f"# {title}\n\n*(PDF senza testo estraibile — possibile scansione)*\n"
    return f"# {title}\n\n" + "\n\n".join(blocks) + "\n"


def _pdf_to_markdown_pymupdf(pdf_path: Path) -> str:
    import fitz

    blocks: List[str] = []
    doc = fitz.open(str(pdf_path))
    try:
        for idx in range(len(doc)):
            page = doc[idx]
            text = (page.get_text("text") or "").strip()
            block = _page_block(idx + 1, [text] if text else [])
            if block:
                blocks.append(block)
    finally:
        doc.close()

    title = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    if not blocks:
        return f"# {title}\n\n*(PDF senza testo estraibile — possibile scansione)*\n"
    return f"# {title}\n\n" + "\n\n".join(blocks) + "\n"


def pdf_to_markdown(pdf_path: Path) -> str:
    """Estrae testo/tabelle da PDF → markdown."""
    src = Path(pdf_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    if src.suffix.lower() != ".pdf":
        raise ValueError("Atteso file .pdf")

    status = pdf_libraries_status()
    errors: List[str] = []
    if status["pdfplumber"]:
        try:
            return _pdf_to_markdown_pdfplumber(src)
        except Exception as exc:
            errors.append(f"pdfplumber: {exc}")
    if status["pymupdf"]:
        try:
            return _pdf_to_markdown_pymupdf(src)
        except Exception as exc:
            errors.append(f"pymupdf: {exc}")

    if not status["pdfplumber"] and not status["pymupdf"]:
        raise RuntimeError(_missing_deps_message())
    raise RuntimeError("Conversione PDF fallita:\n" + "\n".join(errors))


def _target_md_path(pdf_path: Path) -> Path:
    root = ensure_knowledge_root()
    base = pdf_path.stem
    candidate = root / f"{base}.md"
    if not candidate.exists():
        return candidate
    alt = root / f"{base}_from_pdf.md"
    n = 2
    while alt.exists():
        alt = root / f"{base}_from_pdf_{n}.md"
        n += 1
    return alt


def import_pdf_file(
    pdf_path: Path,
    *,
    doc_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Converte PDF → .md in data/knowledge/ e indicizza.
    """
    src = Path(pdf_path).resolve()
    md_text = pdf_to_markdown(src)
    md_path = _target_md_path(src)
    md_path.write_text(md_text, encoding="utf-8")
    dtype = doc_type or infer_doc_type(src.name)
    result = index_file(md_path, doc_type=dtype, copy_to_knowledge_root=False)
    return {
        **result,
        "pdf_path": str(src),
        "md_path": str(md_path),
        "markdown_bytes": len(md_text.encode("utf-8")),
    }
