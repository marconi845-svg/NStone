"""
Finestra dettaglio richiesta preventivo: messaggio cliente, email inviata, thread conversazione.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.common.section_window import SectionDialog


def _text_field_style() -> str:
    return """
        QTextEdit {
            background-color: #0a0a1a; color: #E8E8E8;
            border: 1px solid #2a2a3a; border-radius: 6px; padding: 8px;
            font-size: 12px;
        }
    """


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: bold;")
    return lbl


def _meta_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #AAAAAA; font-size: 11px;")
    return lbl


class QuotationRequestDetailDialog(SectionDialog):
    """Dettaglio completo richiesta: messaggio, risposta/email inviata, storico thread."""

    saved = pyqtSignal(dict)

    def __init__(
        self,
        request: dict,
        related_emails: Optional[List[dict]] = None,
        *,
        extract_material_hints: Optional[Callable[[str], str]] = None,
        parent=None,
        initial_tab: int = 0,
    ):
        super().__init__(parent)
        self._request = dict(request or {})
        self._related_emails = list(related_emails or [])
        self._extract_material_hints = extract_material_hints or (lambda t: "—")
        self._case_id = str(self._request.get("id") or "")

        self.setWindowTitle("Dettaglio richiesta preventivo")
        self.setMinimumSize(720, 560)
        self._build_ui()
        self._load_data()
        if 0 <= initial_tab < self.tabs.count():
            self.tabs.setCurrentIndex(initial_tab)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Dettaglio richiesta")
        title.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.header_meta = _meta_label("—")
        layout.addWidget(self.header_meta)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #2a2a3a; border-radius: 8px;
                background-color: #12121f; padding: 8px;
            }
            QTabBar::tab {
                background-color: #1a1a2a; color: #AAAAAA;
                padding: 8px 16px; margin-right: 4px;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #2a2a4a; color: #FFFFFF;
            }
        """)

        self.tabs.addTab(self._build_request_tab(), "Messaggio cliente")
        self.tabs.addTab(self._build_email_tab(), "Email inviata")
        self.tabs.addTab(self._build_conversation_tab(), "Conversazione")

        layout.addWidget(self.tabs, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("Salva modifiche")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a5a3a; color: #fff; border-radius: 6px;
                padding: 10px 20px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2a6a4a; }
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        close_btn = QPushButton("Chiudi")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a2a6a; color: #fff; border-radius: 6px;
                padding: 10px 24px; font-weight: bold;
            }
            QPushButton:hover { background-color: #5a3a7a; }
        """)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)
        self.setStyleSheet("QDialog { background-color: #0a0a15; }")

    def _build_request_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        v.addWidget(_section_label("Cliente"))
        self.contact_label = QLabel("—")
        self.contact_label.setWordWrap(True)
        self.contact_label.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        v.addWidget(self.contact_label)

        v.addWidget(_section_label("Stato"))
        self.stato_label = QLabel("—")
        self.stato_label.setStyleSheet("color: #E8E8E8; font-size: 12px;")
        v.addWidget(self.stato_label)

        v.addWidget(_section_label("Materiali / prodotti rilevati"))
        self.materials_field = QTextEdit()
        self.materials_field.setReadOnly(True)
        self.materials_field.setMaximumHeight(64)
        self.materials_field.setStyleSheet(_text_field_style())
        v.addWidget(self.materials_field)

        v.addWidget(_section_label("Messaggio completo"))
        self.message_field = QTextEdit()
        self.message_field.setStyleSheet(_text_field_style())
        v.addWidget(self.message_field, 1)

        return w

    def _build_email_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        self.email_meta = _meta_label("—")
        v.addWidget(self.email_meta)

        v.addWidget(_section_label("Oggetto"))
        self.email_subject = QTextEdit()
        self.email_subject.setReadOnly(True)
        self.email_subject.setMaximumHeight(48)
        self.email_subject.setStyleSheet(_text_field_style())
        v.addWidget(self.email_subject)

        v.addWidget(_section_label("Corpo email inviata al cliente"))
        self.email_body = QTextEdit()
        self.email_body.setStyleSheet(_text_field_style())
        v.addWidget(self.email_body, 1)

        v.addWidget(_section_label("Bozza / risposta AI (modificabile)"))
        self.draft_field = QTextEdit()
        self.draft_field.setStyleSheet(_text_field_style())
        self.draft_field.setPlaceholderText(
            "Nessuna bozza ancora. Genera il preventivo dalla colonna centrale."
        )
        v.addWidget(self.draft_field, 1)

        return w

    def _build_conversation_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        self.conversation_layout = QVBoxLayout(inner)
        self.conversation_layout.setContentsMargins(4, 4, 4, 4)
        self.conversation_layout.setSpacing(12)
        self.conversation_empty = QLabel(
            "Nessun messaggio nel thread email per questa richiesta."
        )
        self.conversation_empty.setWordWrap(True)
        self.conversation_empty.setStyleSheet("color: #888899; font-size: 12px; padding: 20px;")
        self.conversation_layout.addWidget(self.conversation_empty)
        self.conversation_layout.addStretch()

        scroll.setWidget(inner)
        return scroll

    def _load_data(self) -> None:
        r = self._request
        rid = self._case_id
        short_id = rid[:8] + "…" if len(rid) > 8 else rid
        ts = str(r.get("timestamp") or "—")
        stato = str(r.get("stato") or "NUOVA")
        self.header_meta.setText(f"ID {short_id} · Ricevuta: {ts} · Stato: {stato}")

        nome = str(r.get("nome") or "—")
        email = str(r.get("email") or "—")
        self.contact_label.setText(f"{nome} · {email}")
        self.stato_label.setText(stato)
        if stato.upper() == "ORDINE_CONFERMATO":
            linked = str(r.get("linked_order_id") or "").strip()
            if linked:
                short_oid = linked[:16] + "…" if len(linked) > 16 else linked
                self.header_meta.setText(
                    f"{self.header_meta.text()} · Ordine: {short_oid}"
                )

        messaggio = str(r.get("messaggio") or "")
        self.message_field.setPlainText(messaggio)
        self.materials_field.setPlainText(self._extract_material_hints(messaggio))

        self._populate_email_tab(r)
        self._populate_conversation_tab()

    def _populate_email_tab(self, r: dict) -> None:
        latest = self._related_emails[0] if self._related_emails else None
        body = ""
        subject = "—"
        to_addr = str(r.get("email") or "—")
        ts = "—"
        status = "—"

        if latest:
            body = str(latest.get("body") or latest.get("summary") or "").strip()
            subject = str(latest.get("subject") or "—")
            to_addr = str(latest.get("to") or to_addr)
            ts = str(latest.get("timestamp") or "—")
            status = str(latest.get("status") or "—")
        else:
            body = str(r.get("risposta_gemini") or "").strip()
            if body and self._case_id:
                try:
                    from modules.quotation_email_thread import make_initial_subject

                    subject = make_initial_subject(self._case_id, str(r.get("nome") or ""))
                except Exception:
                    subject = f"Risposta alla tua richiesta — NStone ({r.get('nome') or 'Cliente'})"
            ts = str(r.get("data_invio_email") or r.get("data_elaborazione") or "—")
            if r.get("email_inviata"):
                status = "inviata"
            elif body:
                status = "bozza non inviata"
            elif r.get("errore_email"):
                status = f"errore: {r.get('errore_email')}"

        if r.get("errore_email") and not latest:
            status = f"errore invio: {r.get('errore_email')}"

        self.email_meta.setText(f"A: {to_addr} · Quando: {ts} · Stato: {status}")
        self.email_subject.setPlainText(subject)
        self.email_body.setPlainText(body or "Nessuna email inviata ancora per questa richiesta.")
        draft = str(r.get("risposta_gemini") or "").strip()
        self.draft_field.setPlainText(draft)

    def _populate_conversation_tab(self) -> None:
        while self.conversation_layout.count():
            item = self.conversation_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        turns: List[Dict] = []
        if self._case_id:
            try:
                from modules.quotation_email_db import list_turns_for_case

                turns = list_turns_for_case(self._case_id)
            except Exception:
                turns = []

        if not turns:
            empty = QLabel("Nessun messaggio nel thread email per questa richiesta.")
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #888899; font-size: 12px; padding: 20px;")
            self.conversation_layout.addWidget(empty)
            self.conversation_layout.addStretch()
            return

        for turn in turns:
            self.conversation_layout.addWidget(self._turn_card(turn))
        self.conversation_layout.addStretch()

    def _turn_card(self, turn: dict) -> QFrame:
        direction = str(turn.get("direction") or "").upper()
        is_out = direction == "OUTBOUND"
        frame = QFrame()
        border_color = "#3a5a8a" if is_out else "#3a6a4a"
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: #0f0f1c;
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        v = QVBoxLayout(frame)
        v.setSpacing(6)

        who = "NStone → cliente" if is_out else "Cliente → NStone"
        when = str(turn.get("created_at") or "—")
        subj = str(turn.get("subject") or "—")
        header = QLabel(f"<b>{who}</b> · {when}")
        header.setStyleSheet("color: #CCCCCC; font-size: 11px;")
        v.addWidget(header)

        subj_lbl = QLabel(f"Oggetto: {subj}")
        subj_lbl.setWordWrap(True)
        subj_lbl.setStyleSheet("color: #9999AA; font-size: 11px;")
        v.addWidget(subj_lbl)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(str(turn.get("body") or "").strip() or "—")
        body.setMaximumHeight(160)
        body.setStyleSheet(_text_field_style())
        v.addWidget(body)

        return frame

    def _on_save(self) -> None:
        fields = {
            "messaggio": self.message_field.toPlainText().strip(),
            "risposta_gemini": self.draft_field.toPlainText().strip(),
        }
        self._request.update(fields)
        self.saved.emit(fields)
        QMessageBox.information(
            self,
            "Salvato",
            "Modifiche registrate in memoria. Usa «Salva nel DB» nel pannello centrale per persistere.",
        )
