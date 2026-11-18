"""Tab Ask — sessione multi-turno con retrieval + LLM (streaming)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from llm.llm_service import LLMService
from modules.knowledge_ask_session import (
    RETRIEVE_LIMIT,
    build_user_prompt,
    history_for_llm,
)
from modules.knowledge_audit_db import log_retrieval
from modules.knowledge_retriever import format_context_block, format_sources_summary, retrieve

_CONTEXT_MAP = {
    "General": ("general", None),
    "Offerte / Quotations": ("offerte", "offerte"),
    "Ordini / Orders": ("ordini", "ordini"),
    "Produzione / Production": ("produzione", "produzione"),
}

_BTN_STYLE = """
    QPushButton {
        background-color: #4a2a6a;
        color: #FFFFFF;
        border: 1px solid #5a3a7a;
        border-radius: 8px;
        font-size: 13px;
        font-weight: bold;
        padding: 10px 20px;
    }
    QPushButton:hover { background-color: #5a3a7a; }
    QPushButton:disabled { background-color: #2a2a3a; color: #666; }
"""

_SECONDARY_BTN = """
    QPushButton {
        background-color: #2a2a3a;
        color: #FFFFFF;
        border: 1px solid #3a3a4a;
        border-radius: 8px;
        font-size: 12px;
        font-weight: bold;
        padding: 8px 14px;
    }
    QPushButton:hover { background-color: #3a3a4a; }
    QPushButton:disabled { color: #666; }
"""

_TEXT_STYLE = (
    "QTextEdit { background:#0a0a1a; color:#fff; border:1px solid #2a2a3a; "
    "border-radius:8px; padding:10px; }"
)
_SESSION_STYLE = (
    "QTextEdit { background:#0a0a1a; color:#e8e8f0; border:1px solid #2a2a3a; "
    "border-radius:8px; padding:12px; font-size:13px; line-height:1.4; }"
)


class KnowledgeQueryWorker(QThread):
    chunk_ready = pyqtSignal(str)
    result_ready = pyqtSignal(str, str, str, object)
    error = pyqtSignal(str)

    def __init__(
        self,
        question: str,
        context_key: str,
        business_context: Optional[str],
        history: Optional[List[Dict[str, str]]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.question = question
        self.context_key = context_key
        self.business_context = business_context
        self.history = history or []

    def run(self) -> None:
        try:
            hits = retrieve(self.question, context_key=self.context_key, limit=RETRIEVE_LIMIT)
            context_block = format_context_block(hits)
            sources_text = format_sources_summary(hits)
            prompt = build_user_prompt(self.question, context_block)

            llm = LLMService()
            if not llm.is_configured():
                self.error.emit(llm.configuration_error_message())
                return

            chunks: List[str] = []

            def _on_chunk(text: str) -> None:
                chunks.append(text)
                self.chunk_ready.emit(text)

            answer = llm.send_message(
                prompt,
                history=self.history,
                business_context=self.business_context,
                request_kind="operational",
                on_chunk=_on_chunk,
            )
            if not chunks and answer:
                self.chunk_ready.emit(answer)
            self.result_ready.emit(answer, sources_text, context_block, hits)
        except Exception as exc:
            self.error.emit(str(exc))


class KnowledgeQueryWidget(QWidget):
    def __init__(self, on_logged: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self._on_logged = on_logged
        self._worker: Optional[KnowledgeQueryWorker] = None
        self._turns: List[Dict[str, Any]] = []
        self._pending_question = ""
        self._build_ui()

    def set_input_text(self, text: str) -> None:
        """Precompila il campo messaggio (es. da Quotations Hub)."""
        self.message_input.setPlainText((text or "").strip())

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        left = QVBoxLayout()
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Session"))
        header_row.addStretch()
        self.new_session_btn = QPushButton("New session")
        self.new_session_btn.setStyleSheet(_SECONDARY_BTN)
        self.new_session_btn.clicked.connect(self._on_new_session)
        header_row.addWidget(self.new_session_btn)
        left.addLayout(header_row)

        self.session_view = QTextEdit()
        self.session_view.setReadOnly(True)
        self.session_view.setMinimumHeight(280)
        self.session_view.setStyleSheet(_SESSION_STYLE)
        self.session_view.setPlaceholderText(
            "Ask a question to start a session. Follow-up messages keep context "
            "from the last few turns."
        )
        left.addWidget(self.session_view, 1)

        left.addWidget(QLabel("Your message"))
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText(
            "Es.: Prezzo Carrara lucido 2 cm EX WORKS per 50 m²…\n"
            "Follow-up: «solo passo 3» · «e per 3 cm?»"
        )
        self.message_input.setMaximumHeight(120)
        self.message_input.setStyleSheet(_TEXT_STYLE)
        left.addWidget(self.message_input)

        ctx_row = QHBoxLayout()
        ctx_row.addWidget(QLabel("Context:"))
        self.context_combo = QComboBox()
        for label in _CONTEXT_MAP:
            self.context_combo.addItem(label)
        ctx_row.addWidget(self.context_combo, 1)
        left.addLayout(ctx_row)

        action_row = QHBoxLayout()
        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet(_BTN_STYLE)
        self.send_btn.clicked.connect(self._on_send)
        action_row.addWidget(self.send_btn)
        action_row.addStretch()
        left.addLayout(action_row)

        quick = QHBoxLayout()
        for text in ("Prezzo Carrara 2cm", "Avvio multifilo"):
            b = QPushButton(text)
            b.setStyleSheet(_SECONDARY_BTN)
            b.clicked.connect(lambda _=False, t=text: self.message_input.setPlainText(t))
            quick.addWidget(b)
        left.addLayout(quick)
        layout.addLayout(left, 45)

        right = QVBoxLayout()
        right.addWidget(QLabel("Latest sources"))
        self.sources = QTextEdit()
        self.sources.setReadOnly(True)
        self.sources.setMaximumHeight(140)
        self.sources.setStyleSheet(
            "QTextEdit { background:#0a0a1a; color:#9fd; border:1px solid #2a4a3a; "
            "border-radius:8px; padding:8px; font-size:12px; }"
        )
        right.addWidget(self.sources)

        right.addWidget(QLabel("Retrieved context (last turn)"))
        self.context_view = QTextEdit()
        self.context_view.setReadOnly(True)
        self.context_view.setStyleSheet(
            "QTextEdit { background:#0a0a1a; color:#ccc; border:1px solid #2a2a3a; "
            "border-radius:8px; padding:8px; font-size:11px; "
            "font-family: Consolas, monospace; }"
        )
        right.addWidget(self.context_view, 1)
        layout.addLayout(right, 55)

    def _completed_turns(self) -> List[Dict[str, Any]]:
        return [t for t in self._turns if not t.get("_streaming")]

    def _render_session(self) -> None:
        parts: List[str] = []
        for turn in self._turns:
            role = turn.get("role")
            text = str(turn.get("text") or "")
            if role == "user":
                parts.append(f"── You ──\n{text.strip()}\n")
            elif role == "assistant":
                label = "Retrieval"
                if turn.get("_streaming") and not text.strip():
                    text = "…"
                parts.append(f"── {label} ──\n{text.rstrip()}\n")
        self.session_view.setPlainText("\n".join(parts).strip())
        bar = self.session_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _scroll_session_bottom(self) -> None:
        bar = self.session_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_busy(self, busy: bool) -> None:
        self.send_btn.setEnabled(not busy)
        self.new_session_btn.setEnabled(not busy)
        self.context_combo.setEnabled(not busy)

    def _on_new_session(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._turns.clear()
        self.session_view.clear()
        self.sources.clear()
        self.context_view.clear()
        self.message_input.clear()

    def _on_send(self) -> None:
        q = self.message_input.toPlainText().strip()
        if not q:
            QMessageBox.information(self, "Ask", "Enter a message first.")
            return
        if self._worker and self._worker.isRunning():
            return

        label = self.context_combo.currentText()
        ctx_key, biz = _CONTEXT_MAP.get(label, ("general", None))
        self._pending_question = q
        self.message_input.clear()

        self._turns.append({"role": "user", "text": q})
        self._turns.append({"role": "assistant", "text": "", "_streaming": True})
        self._render_session()

        history = history_for_llm(self._completed_turns()[:-2])
        self._set_busy(True)
        self.sources.setPlainText("Retrieving…")
        self.context_view.clear()

        self._worker = KnowledgeQueryWorker(q, ctx_key, biz, history=history)
        self._worker.chunk_ready.connect(self._on_chunk)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_chunk(self, chunk: str) -> None:
        if not self._turns or self._turns[-1].get("role") != "assistant":
            return
        self._turns[-1]["text"] = str(self._turns[-1].get("text") or "") + chunk
        self._render_session()

    def _on_result(self, answer: str, sources: str, context_block: str, hits) -> None:
        if self._turns and self._turns[-1].get("_streaming"):
            self._turns[-1]["text"] = answer
            self._turns[-1].pop("_streaming", None)
        self._render_session()
        self.sources.setPlainText(sources)
        self.context_view.setPlainText(context_block or "(no chunks retrieved)")
        log_retrieval(
            question=self._pending_question,
            context_key=self.context_combo.currentText(),
            hits=hits or [],
            answer_preview=answer,
        )
        if self._on_logged:
            self._on_logged()
        self._set_busy(False)

    def _on_error(self, msg: str) -> None:
        if self._turns and self._turns[-1].get("_streaming"):
            self._turns[-1]["text"] = f"Error: {msg}"
            self._turns[-1].pop("_streaming", None)
        else:
            self._turns.append({"role": "assistant", "text": f"Error: {msg}"})
        self._render_session()
        self._set_busy(False)
