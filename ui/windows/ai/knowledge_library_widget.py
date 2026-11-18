"""Tab Library — gestione documenti MD indicizzati."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from modules.knowledge_db import DOC_TYPES, ensure_knowledge_root
from modules.knowledge_ingest import (
    index_paths,
    list_documents,
    read_document_text,
    reindex_all,
    remove_document,
)
from modules.knowledge_pdf import import_pdf_file, pdf_import_available
from ui.common.floppy_drive_animation import FloppyImportOverlay

_PANEL_STYLE = """
    QFrame, QWidget#libraryPanel {
        background-color: #1a1a2a;
        border: 1px solid #2a2a3a;
        border-radius: 10px;
    }
"""

_BTN_PDF_STYLE = """
    QPushButton {
        background-color: #1a3a4a;
        color: #a8e8ff;
        border: 1px solid #3a7a9a;
        border-radius: 8px;
        font-size: 12px;
        font-weight: bold;
        padding: 8px 14px;
    }
    QPushButton:hover { background-color: #2a4a5a; }
    QPushButton:disabled { background-color: #2a2a3a; color: #666; }
"""

_BTN_STYLE = """
    QPushButton {
        background-color: #4a2a6a;
        color: #FFFFFF;
        border: 1px solid #5a3a7a;
        border-radius: 8px;
        font-size: 12px;
        font-weight: bold;
        padding: 8px 14px;
    }
    QPushButton:hover { background-color: #5a3a7a; }
    QPushButton:disabled { background-color: #2a2a3a; color: #666; }
"""


class _PdfImportWorker(QThread):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, pdf_path: Path, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path

    def run(self) -> None:
        try:
            result = import_pdf_file(self.pdf_path)
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class KnowledgeLibraryWidget(QWidget):
    """Document library: add, preview, reindex, remove."""

    def __init__(self, on_stats_changed: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self._on_stats_changed = on_stats_changed
        self._selected_doc_id: Optional[int] = None
        self._pdf_worker: Optional[_PdfImportWorker] = None
        self._build_ui()
        self.refresh(notify=False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("Add files…")
        self.btn_add.setStyleSheet(_BTN_STYLE)
        self.btn_add.clicked.connect(self._add_files)
        toolbar.addWidget(self.btn_add)

        self.btn_import_pdf = QPushButton("Import PDF…")
        self.btn_import_pdf.setStyleSheet(_BTN_PDF_STYLE)
        self.btn_import_pdf.clicked.connect(self._import_pdf)
        if not pdf_import_available():
            self.btn_import_pdf.setToolTip(
                "Installa pdfplumber o pymupdf:\npip install -r requirements-knowledge.txt"
            )
        toolbar.addWidget(self.btn_import_pdf)

        self.btn_folder = QPushButton("Open folder")
        self.btn_folder.setStyleSheet(_BTN_STYLE)
        self.btn_folder.clicked.connect(self._open_folder)
        toolbar.addWidget(self.btn_folder)

        self.btn_reindex = QPushButton("Reindex all")
        self.btn_reindex.setStyleSheet(_BTN_STYLE)
        self.btn_reindex.clicked.connect(self._reindex_all)
        toolbar.addWidget(self.btn_reindex)

        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setStyleSheet(_BTN_STYLE)
        self.btn_remove.clicked.connect(self._remove_selected)
        toolbar.addWidget(self.btn_remove)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.type_filter = QComboBox()
        self.type_filter.addItem("All types", "")
        for dt in DOC_TYPES:
            self.type_filter.addItem(dt.replace("_", " ").title(), dt)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(self.type_filter)
        filter_row.addStretch()
        left_layout.addLayout(filter_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Chunks", "Indexed"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setStyleSheet(
            "QTableWidget { background:#0a0a1a; color:#fff; gridline-color:#2a2a3a; }"
            "QHeaderView::section { background:#2a2a3a; color:#fff; padding:6px; }"
        )
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.meta_label = QLabel("Select a document")
        self.meta_label.setStyleSheet("color: #ccc; font-size: 12px;")
        self.meta_label.setWordWrap(True)
        right_layout.addWidget(self.meta_label)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Markdown preview…")
        self.preview.setStyleSheet(
            "QTextEdit { background:#0a0a1a; color:#e8ecf1; border:1px solid #2a2a3a; border-radius:8px; padding:10px; }"
        )
        right_layout.addWidget(self.preview, 1)
        splitter.addWidget(right)
        splitter.setSizes([420, 680])
        layout.addWidget(splitter, 1)

        self._floppy_overlay = FloppyImportOverlay(self)
        self._floppy_overlay.setGeometry(self.rect())
        self._floppy_overlay.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_floppy_overlay"):
            self._floppy_overlay.setGeometry(self.rect())

    def refresh(self, *, notify: bool = True) -> None:
        docs = list_documents()
        filt = self.type_filter.currentData()
        if filt:
            docs = [d for d in docs if d.get("doc_type") == filt]
        self.table.setRowCount(len(docs))
        for row, doc in enumerate(docs):
            self.table.setItem(row, 0, QTableWidgetItem(doc.get("file_name") or ""))
            self.table.setItem(row, 1, QTableWidgetItem(str(doc.get("doc_type") or "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(doc.get("chunk_count") or 0)))
            self.table.setItem(row, 3, QTableWidgetItem(str(doc.get("indexed_at") or "—")[:19]))
            id_item = QTableWidgetItem()
            id_item.setData(Qt.UserRole, doc.get("id"))
            self.table.setItem(row, 0, self.table.item(row, 0))
            self.table.item(row, 0).setData(Qt.UserRole, doc.get("id"))
        if notify and self._on_stats_changed:
            self._on_stats_changed()

    def _selected_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_selection_changed(self) -> None:
        doc_id = self._selected_id()
        self._selected_doc_id = doc_id
        if doc_id is None:
            self.meta_label.setText("Select a document")
            self.preview.clear()
            return
        docs = {d["id"]: d for d in list_documents()}
        doc = docs.get(doc_id)
        if not doc:
            return
        self.meta_label.setText(
            f"File: {doc.get('file_name')}\n"
            f"Type: {doc.get('doc_type')} · Chunks: {doc.get('chunk_count')}\n"
            f"Path: {doc.get('file_path')}"
        )
        self.preview.setPlainText(read_document_text(doc_id))

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Markdown documents",
            str(ensure_knowledge_root()),
            "Markdown (*.md)",
        )
        if not paths:
            return
        results = index_paths([Path(p) for p in paths])
        errors = [r for r in results if r.get("status") == "error"]
        if errors:
            QMessageBox.warning(
                self,
                "Indexing",
                "Some files failed:\n" + "\n".join(f"{r['path']}: {r.get('error')}" for r in errors),
            )
        self.refresh()

    def _import_pdf(self) -> None:
        if not pdf_import_available():
            QMessageBox.warning(
                self,
                "Import PDF",
                "Serve pdfplumber o PyMuPDF.\n\n"
                "pip install -r requirements-knowledge.txt",
            )
            return
        if self._pdf_worker and self._pdf_worker.isRunning():
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import PDF to knowledge base",
            str(ensure_knowledge_root()),
            "PDF (*.pdf)",
        )
        if not path:
            return

        self._set_pdf_busy(True)
        self._floppy_overlay.start(f"Importing {Path(path).name}…")
        self._pdf_worker = _PdfImportWorker(Path(path), self)
        self._pdf_worker.finished_ok.connect(self._on_pdf_import_ok)
        self._pdf_worker.failed.connect(self._on_pdf_import_failed)
        self._pdf_worker.finished.connect(lambda: self._set_pdf_busy(False))
        self._pdf_worker.start()

    def _set_pdf_busy(self, busy: bool) -> None:
        for btn in (self.btn_add, self.btn_import_pdf, self.btn_reindex, self.btn_remove):
            btn.setEnabled(not busy)

    def _on_pdf_import_ok(self, result: object) -> None:
        self._floppy_overlay.finish()
        data = result if isinstance(result, dict) else {}
        md_path = data.get("md_path", "")
        chunks = data.get("chunks", "?")
        QMessageBox.information(
            self,
            "Import PDF",
            f"Convertito e indicizzato.\n\nMD: {md_path}\nChunks: {chunks}",
        )
        self.refresh()

    def _on_pdf_import_failed(self, message: str) -> None:
        self._floppy_overlay.finish()
        QMessageBox.critical(self, "Import PDF", message)
        self.refresh()

    def _open_folder(self) -> None:
        import os
        import sys

        folder = str(ensure_knowledge_root())
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        else:
            QMessageBox.information(self, "Knowledge folder", folder)

    def _reindex_all(self) -> None:
        n = reindex_all()
        QMessageBox.information(self, "Reindex", f"Reindexed {n} document(s).")
        self.refresh()

    def _remove_selected(self) -> None:
        doc_id = self._selected_id()
        if doc_id is None:
            QMessageBox.information(self, "Remove", "Select a document first.")
            return
        reply = QMessageBox.question(
            self,
            "Remove document",
            "Remove from knowledge base index? (file on disk is kept)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        remove_document(doc_id, delete_file=False)
        self.refresh()
