#!/usr/bin/env python3
"""CLI: converte PDF in Markdown e indicizza in Retrieval Fabric."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.knowledge_pdf import import_pdf_file, pdf_import_available, pdf_libraries_status


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF → data/knowledge/*.md + index")
    parser.add_argument("pdf", type=Path, nargs="+", help="File PDF da importare")
    args = parser.parse_args()

    if not pdf_import_available():
        print("Dipendenze mancanti:", pdf_libraries_status(), file=sys.stderr)
        print("Installa: pip install -r requirements-knowledge.txt", file=sys.stderr)
        return 1

    ok = 0
    for pdf in args.pdf:
        try:
            result = import_pdf_file(pdf)
            print(f"OK {pdf.name} → {result.get('md_path')} [{result.get('status')}]")
            ok += 1
        except Exception as exc:
            print(f"ERR {pdf}: {exc}", file=sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
