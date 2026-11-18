"""
Export PDF dossier compliance per consulente del lavoro / DPO (L. 132/2025, GDPR).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.ai_compliance_service import (
    NSTONELLM_VERSION,
    compute_posture,
    render_worker_notice,
)
from modules.compliance_registry_db import list_worker_acknowledgments, load_compliance_profile

logger = logging.getLogger(__name__)


def _safe_pdf_text(value: Any, *, max_len: int = 4000) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    replacements = {
        "€": " EUR",
        "–": "-",
        "—": "-",
        "'": "'",
        "'": "'",
        """: '"',
        """: '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text or "-"


class CompliancePdfBuilder:
    """Generatore PDF A4 — stile allineato a order_confirmation_pdf."""

    def __init__(self) -> None:
        try:
            from fpdf import FPDF
            from fpdf.enums import XPos, YPos
        except ImportError as exc:
            raise ImportError("fpdf2 required: pip install fpdf2") from exc
        self._FPDF = FPDF
        self._XPos = XPos
        self._YPos = YPos
        self.pdf = FPDF(format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=18)
        self.pdf.set_margins(18, 18, 18)
        self.w = self.pdf.epw

    def _title(self, text: str, size: int = 16) -> None:
        self.pdf.set_font("Helvetica", "B", size)
        self.pdf.set_text_color(35, 45, 65)
        self.pdf.multi_cell(self.w, 8, _safe_pdf_text(text))
        self.pdf.ln(2)

    def _subtitle(self, text: str) -> None:
        self.pdf.set_font("Helvetica", "I", 9)
        self.pdf.set_text_color(90, 90, 100)
        self.pdf.multi_cell(self.w, 5, _safe_pdf_text(text))
        self.pdf.ln(3)

    def _h2(self, text: str) -> None:
        self.pdf.ln(2)
        self.pdf.set_font("Helvetica", "B", 11)
        self.pdf.set_text_color(45, 55, 75)
        self.pdf.multi_cell(self.w, 6, _safe_pdf_text(text))
        self.pdf.ln(1)

    def _body(self, text: str) -> None:
        self.pdf.set_font("Helvetica", "", 9)
        self.pdf.set_text_color(25, 25, 30)
        for paragraph in _safe_pdf_text(text).split("\n"):
            line = paragraph.strip()
            if line:
                self.pdf.multi_cell(self.w, 4.5, line)
            else:
                self.pdf.ln(2)
        self.pdf.ln(1)

    def _kv_rows(self, rows: List[tuple[str, str]]) -> None:
        self.pdf.set_font("Helvetica", "", 9)
        for label, value in rows:
            self.pdf.set_font("Helvetica", "B", 9)
            self.pdf.cell(52, 5, _safe_pdf_text(label)[:40], new_x=self._XPos.RIGHT, new_y=self._YPos.TOP)
            self.pdf.set_font("Helvetica", "", 9)
            self.pdf.multi_cell(self.w - 52, 5, _safe_pdf_text(value))

    def _bullet_list(self, items: List[str]) -> None:
        self.pdf.set_font("Helvetica", "", 9)
        for item in items:
            self.pdf.multi_cell(self.w, 4.5, f"  -  {_safe_pdf_text(item)}")

    def add_cover(self, employer: str, stamp: str) -> None:
        self.pdf.add_page()
        self._title("NStone - Dossier compliance AI")
        self._subtitle(
            "Documento per consulente del lavoro / referente HR / DPO. "
            "L. 132/2025, D.Lgs. 152/1997 art. 1-bis, GDPR, EU AI Act."
        )
        self.pdf.ln(4)
        self._kv_rows(
            [
                ("Datore di lavoro:", employer or "(non compilato)"),
                ("Sistema:", f"NStone v{NSTONELLM_VERSION}"),
                ("Generato il:", stamp),
            ]
        )
        self.pdf.ln(4)
        self._body(
            "Avvertenza: documento generato automaticamente dal software a supporto "
            "della trasparenza verso i lavoratori e del compliance operativo. "
            "Non sostituisce parere legale o consulenza del lavoro."
        )

    def add_employer_register(self, profile: Dict[str, Any]) -> None:
        self.pdf.add_page()
        self._h2("1. Registro titolare / dati azienda (GDPR art. 13)")
        self._kv_rows(
            [
                ("Ragione sociale:", profile.get("employer_name") or ""),
                ("P.IVA / CF:", profile.get("employer_vat") or ""),
                ("Sede / reparto:", profile.get("workplace_site") or ""),
                ("Rappresentante:", profile.get("legal_rep_name") or ""),
                ("DPO / privacy:", profile.get("dpo_name") or ""),
                ("Email DPO:", profile.get("dpo_email") or ""),
                ("Finalita trattamento:", profile.get("processing_purposes") or ""),
                ("Base giuridica:", profile.get("legal_basis") or ""),
                ("Conservazione (gg):", str(profile.get("retention_days") or "")),
                ("Provider LLM:", profile.get("llm_provider_note") or ""),
                ("DPIA completata:", "Si" if profile.get("dpia_completed") else "No"),
                ("Revisione DPIA:", profile.get("dpia_reviewed_at") or ""),
            ]
        )

    def add_posture(self, posture: Dict[str, Any]) -> None:
        self._h2("2. Postura compliance e autonomia sistema")
        self._kv_rows(
            [
                ("Score checklist:", f"{posture.get('score_percent', 0)}%"),
                ("Valutazione:", posture.get("overall_label") or ""),
                (
                    "Livello autonomia effettivo:",
                    f"L{posture.get('effective_autonomy_level')} - "
                    f"{posture.get('autonomy_label', '')}",
                ),
                ("Cap licenza (max):", f"L{posture.get('max_level')}"),
                ("Kill switch agenti:", "Attivo" if posture.get("agents_paused") else "No"),
            ]
        )
        self.pdf.ln(2)
        self._body(
            "L. 132/2025 art. 11: l'IA in ambito lavorativo deve essere sicura, "
            "affidabile e trasparente. NStone implementa livelli L0-L4 con default "
            "conservativo (suggerimenti / approvazione umana) e registro audit."
        )

    def add_worker_notice(self) -> None:
        self.pdf.add_page()
        self._h2("3. Informativa lavoratori (art. 11 L. 132/2025; art. 1-bis D.Lgs. 152/1997)")
        notice = render_worker_notice(language="it")
        self._body(notice)

    def add_checklist(self, items: List[Dict[str, Any]]) -> None:
        self.pdf.add_page()
        self._h2("4. Checklist requisiti normativi")
        for item in items:
            if item.get("status") == "na":
                continue
            auto = ""
            if item.get("auto_ok") is True:
                auto = " [probe OK]"
            elif item.get("auto_ok") is False:
                auto = " [verificare]"
            self.pdf.set_font("Helvetica", "B", 9)
            self.pdf.multi_cell(
                self.w,
                5,
                _safe_pdf_text(f"{item.get('domain')} - {item.get('title_it')}{auto}"),
            )
            self.pdf.set_font("Helvetica", "", 8)
            self.pdf.multi_cell(
                self.w,
                4,
                _safe_pdf_text(
                    f"Riferimento: {item.get('legal_ref')} | Stato: {item.get('status')}"
                ),
            )
            ev = item.get("evidence_note") or item.get("auto_detail") or ""
            if ev:
                self.pdf.multi_cell(self.w, 4, _safe_pdf_text(f"Evidenza: {ev}"))
            self.pdf.ln(1)

    def add_acknowledgments(self, rows: List[Dict[str, Any]]) -> None:
        self.pdf.add_page()
        self._h2("5. Registro presa visione lavoratori")
        if not rows:
            self._body("Nessuna presa visione registrata in applicazione.")
            return
        self.pdf.set_font("Helvetica", "B", 8)
        col_w = [38, 42, 38, 22, 40]
        headers = ["Data", "Nome", "Ruolo", "Ver.", "Metodo"]
        for i, h in enumerate(headers):
            self.pdf.cell(col_w[i], 6, h, border=1)
        self.pdf.ln()
        self.pdf.set_font("Helvetica", "", 8)
        for r in rows[:80]:
            vals = [
                str(r.get("acknowledged_at", ""))[:16],
                str(r.get("worker_name", ""))[:28],
                str(r.get("worker_role", ""))[:22],
                str(r.get("notice_version", ""))[:8],
                str(r.get("method", ""))[:18],
            ]
            for i, v in enumerate(vals):
                self.pdf.cell(col_w[i], 5, _safe_pdf_text(v), border=1)
            self.pdf.ln()

    def add_technical_safeguards(self, posture: Dict[str, Any]) -> None:
        self.pdf.add_page()
        self._h2("6. Salvaguardie tecniche NStone")
        auto = posture.get("auto_checks") or {}
        bullets = [
            f"Informativa pubblicata: {auto.get('worker_notice_published', {}).get('detail', '')}",
            f"Profilo titolare: {auto.get('profile_complete', {}).get('detail', '')}",
            f"Supervisione umana: {auto.get('human_oversight_enabled', {}).get('detail', '')}",
            f"Audit trail: {auto.get('audit_available', {}).get('detail', '')}",
            f"Cap autonomia: {auto.get('license_cap_set', {}).get('detail', '')}",
            "Agents Command Center: accesso protetto da password sezione",
            "Registro DB: autonomy_audit, pending_actions, compliance_worker_ack",
        ]
        self._bullet_list(bullets)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(path))
        return path


def export_compliance_pdf_for_consultant(output_dir: Path) -> Path:
    """Genera PDF dossier per consulente del lavoro."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    file_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    profile = load_compliance_profile()
    posture = compute_posture()
    acks = list_worker_acknowledgments(500)

    builder = CompliancePdfBuilder()
    builder.add_cover(profile.get("employer_name") or "", stamp)
    builder.add_employer_register(profile)
    builder.add_posture(posture)
    builder.add_worker_notice()
    builder.add_checklist(posture.get("items") or [])
    builder.add_acknowledgments(acks)
    builder.add_technical_safeguards(posture)

    employer_slug = re.sub(r"[^\w]+", "_", (profile.get("employer_name") or "nstone").lower())[:30]
    out = output_dir / f"nstone_compliance_consulente_{employer_slug}_{file_stamp}.pdf"
    builder.save(out)
    logger.info("Compliance PDF exported: %s", out)
    return out
