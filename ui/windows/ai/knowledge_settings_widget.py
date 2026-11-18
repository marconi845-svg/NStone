"""Tab Settings — opzioni knowledge base."""

from __future__ import annotations

import os
import sys

from PyQt5.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from llm.llm_service import LLMService, load_llm_config, ui_model_label_from_config
from modules.knowledge_db import KNOWLEDGE_ROOT, ensure_knowledge_root
from modules.knowledge_ingest import reindex_all, stats_summary
from modules.knowledge_pdf import pdf_import_available, pdf_libraries_status


class KnowledgeSettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        ensure_knowledge_root()
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: #ccc; font-size: 13px;")
        layout.addWidget(self.info)

        open_btn = QPushButton("Open knowledge folder")
        open_btn.clicked.connect(self._open_folder)
        layout.addWidget(open_btn)

        reindex_btn = QPushButton("Reindex all .md in folder")
        reindex_btn.clicked.connect(self._reindex)
        layout.addWidget(reindex_btn)

        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        stats = stats_summary()
        model = ui_model_label_from_config(load_llm_config())
        pdf_status = pdf_libraries_status()
        pdf_line = (
            "PDF import: pdfplumber + PyMuPDF ready"
            if pdf_import_available()
            else "PDF import: install requirements-knowledge.txt (pdfplumber / pymupdf)"
        )
        self.info.setText(
            f"Knowledge root:\n{KNOWLEDGE_ROOT}\n\n"
            f"Indexed: {stats['documents']} documents · {stats['chunks']} chunks\n"
            f"Supported: Markdown (.md) · PDF via Library import\n"
            f"{pdf_line}\n"
            f"  pdfplumber={pdf_status['pdfplumber']} · pymupdf={pdf_status['pymupdf']}\n"
            f"Active LLM: {model}\n\n"
            "Place price lists, procedures, and catalogs here, then use Library or Reindex."
        )

    def _open_folder(self) -> None:
        folder = str(ensure_knowledge_root())
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        else:
            QMessageBox.information(self, "Folder", folder)

    def _reindex(self) -> None:
        n = reindex_all()
        QMessageBox.information(self, "Reindex", f"Reindexed {n} file(s).")
        self.refresh()
