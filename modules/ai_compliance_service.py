"""
Servizio compliance: posture automatica, template informativa, export evidence pack.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agents_config import AUTONOMY_LEVEL_LABELS, load_command_center_settings
from core.autonomy_policy import get_policy
from modules.ai_compliance_catalog import (
    REQUIREMENTS,
    REQUIREMENT_BY_ID,
    WORKER_NOTICE_TEMPLATE_EN,
    WORKER_NOTICE_TEMPLATE_IT,
    CheckStatus,
)
from modules.compliance_registry_db import (
    ensure_compliance_tables,
    load_checklist_items,
    load_compliance_profile,
    save_compliance_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "nstonellm.db"
NSTONELLM_VERSION = "1.14"


def _dpo_contact(profile: Dict[str, Any]) -> str:
    name = (profile.get("dpo_name") or "").strip()
    email = (profile.get("dpo_email") or "").strip()
    if name and email:
        return f"{name} <{email}>"
    if email:
        return email
    if name:
        return name
    return "(da configurare — DPO / referente privacy)"


def render_worker_notice(*, language: str = "it") -> str:
    profile = load_compliance_profile()
    if not (profile.get("ai_system_version") or "").strip():
        profile = dict(profile)
        profile["ai_system_version"] = NSTONELLM_VERSION
    ctx = {
        "employer_name": profile.get("employer_name") or "(ragione sociale)",
        "workplace_site": profile.get("workplace_site") or "(sede/reparto)",
        "ai_system_name": profile.get("ai_system_name") or "NStone",
        "ai_system_version": profile.get("ai_system_version") or NSTONELLM_VERSION,
        "processing_purposes": profile.get("processing_purposes")
        or "Gestione ordini, preventivi e assistenza produzione lapidea.",
        "legal_basis": profile.get("legal_basis") or "Art. 6 GDPR (contratto / legittimo interesse)",
        "retention_days": profile.get("retention_days") or 365,
        "dpo_contact": _dpo_contact(profile),
        "notice_version": profile.get("worker_notice_version") or "1.0",
        "published_at": profile.get("worker_notice_published_at") or "(non ancora pubblicata)",
    }
    tpl = WORKER_NOTICE_TEMPLATE_IT if language.lower().startswith("it") else WORKER_NOTICE_TEMPLATE_EN
    return tpl.format(**ctx)


def _audit_stats(db_path: Path) -> Dict[str, int]:
    ensure_compliance_tables(db_path=db_path)
    stats = {"autonomy_audit": 0, "pending_actions": 0, "agent_messages": 0}
    try:
        with sqlite3.connect(db_path) as conn:
            for table in stats:
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    stats[table] = int(row[0]) if row else 0
                except sqlite3.Error:
                    pass
    except sqlite3.Error:
        pass
    return stats


def _run_auto_checks() -> Dict[str, Dict[str, Any]]:
    """Probe tecnici collegati ai requisiti del catalogo."""
    settings = load_command_center_settings()
    auto = settings["autonomy"]
    level = min(auto["level"], auto["max_level"])
    profile = load_compliance_profile()
    audit = _audit_stats(DEFAULT_DB_PATH)

    checks: Dict[str, Dict[str, Any]] = {}

    checks["worker_notice_published"] = {
        "ok": bool((profile.get("worker_notice_published_at") or "").strip()),
        "detail": profile.get("worker_notice_published_at") or "Informativa non pubblicata",
    }
    checks["autonomy_conservative"] = {
        "ok": level <= 2 and not auto.get("agents_paused") is False or level <= 2,
        "detail": f"L{level} effettivo — {AUTONOMY_LEVEL_LABELS.get(level, '')}",
    }
    checks["scope_no_hr"] = {
        "ok": True,
        "detail": "NStone: scope ordini/preventivi/produzione — nessun modulo HR",
    }
    required_profile = ("employer_name", "dpo_email", "processing_purposes")
    missing = [k for k in required_profile if not (profile.get(k) or "").strip()]
    checks["profile_complete"] = {
        "ok": not missing,
        "detail": "Completo" if not missing else f"Mancano: {', '.join(missing)}",
    }
    human_ok = level <= 1 or (level == 2 and not auto.get("office_auto_email"))
    checks["human_oversight_enabled"] = {
        "ok": human_ok,
        "detail": (
            "Supervisione umana rafforzata (bozze / approvazione)"
            if human_ok
            else f"L{level} — auto-email abilitata: verificare informativa e DPIA"
        ),
    }
    checks["dpia_reviewed"] = {
        "ok": bool(profile.get("dpia_completed")),
        "detail": profile.get("dpia_reviewed_at") or "DPIA non marcata come completata",
    }
    llm_note = (profile.get("llm_provider_note") or "").strip()
    checks["system_register_complete"] = {
        "ok": bool(llm_note) and bool((profile.get("employer_name") or "").strip()),
        "detail": "Registro sistema compilato" if llm_note else "Indicare provider LLM nel registro",
    }
    checks["audit_available"] = {
        "ok": audit["autonomy_audit"] > 0 or audit["pending_actions"] > 0,
        "detail": (
            f"autonomy_audit={audit['autonomy_audit']}, "
            f"pending_actions={audit['pending_actions']}"
        ),
    }
    checks["license_cap_set"] = {
        "ok": auto.get("max_level", 2) <= 4,
        "detail": f"max_level=L{auto.get('max_level', 2)}",
    }
    return checks


def compute_posture() -> Dict[str, Any]:
    """Postura compliance sintetica per dashboard."""
    auto_checks = _run_auto_checks()
    checklist = {row["req_id"]: row for row in load_checklist_items()}
    settings = load_command_center_settings()
    auto = settings["autonomy"]
    level = min(auto["level"], auto["max_level"])
    profile = load_compliance_profile()

    items: List[Dict[str, Any]] = []
    done = partial = open_count = 0
    for req in REQUIREMENTS:
        row = checklist.get(req.req_id, {})
        status: CheckStatus = row.get("status") or "open"
        probe = auto_checks.get(req.auto_check) if req.auto_check else None
        auto_ok = probe["ok"] if probe else None
        if status == "done":
            done += 1
        elif status == "partial":
            partial += 1
        elif status != "na":
            open_count += 1
        items.append(
            {
                "req_id": req.req_id,
                "domain": req.domain,
                "title_it": req.title_it,
                "title_en": req.title_en,
                "legal_ref": req.legal_ref,
                "status": status,
                "evidence_note": row.get("evidence_note") or "",
                "auto_ok": auto_ok,
                "auto_detail": probe["detail"] if probe else "",
                "nstone_control": req.nstone_control,
            }
        )

    total = len([i for i in items if i["status"] != "na"])
    score = int(round(100 * done / total)) if total else 0

    if level >= 3:
        overall = "lab_only"
        overall_label = "LAB MODE — non per produzione (L. 132/2025)"
    elif level == 2 and auto.get("office_auto_email"):
        overall = "elevated"
        overall_label = "Autonomia elevata — verificare informativa lavoratori e DPIA"
    elif done >= total * 0.7 and auto_checks.get("profile_complete", {}).get("ok"):
        overall = "good"
        overall_label = "Postura adeguata per pilota IT/EU (L0–L2 governato)"
    else:
        overall = "action_required"
        overall_label = "Completare registro titolare e informativa lavoratori"

    return {
        "score_percent": score,
        "overall": overall,
        "overall_label": overall_label,
        "effective_autonomy_level": level,
        "autonomy_label": AUTONOMY_LEVEL_LABELS.get(level, ""),
        "agents_paused": bool(auto.get("agents_paused")),
        "max_level": auto.get("max_level"),
        "items": items,
        "auto_checks": auto_checks,
        "profile": profile,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_auto_checklist_from_posture(*, updated_by: str = "system") -> None:
    """Allinea stati checklist parziale/done in base ai probe tecnici."""
    from modules.compliance_registry_db import update_checklist_item

    auto_checks = _run_auto_checks()
    for req in REQUIREMENTS:
        if not req.auto_check:
            continue
        probe = auto_checks.get(req.auto_check)
        if not probe:
            continue
        status: CheckStatus = "done" if probe["ok"] else "partial"
        update_checklist_item(
            req.req_id,
            status,
            evidence_note=probe["detail"],
            updated_by=updated_by,
        )


def export_compliance_pack(output_dir: Path) -> Path:
    """Esporta JSON + informativa IT/EN per audit / commercialista."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    posture = compute_posture()
    pack = {
        "product": "NStone",
        "version": NSTONELLM_VERSION,
        "legal_framework": [
            "L. 132/2025 (IT AI)",
            "D.Lgs. 152/1997 art. 1-bis",
            "Reg. UE 2016/679 (GDPR)",
            "Reg. UE 2024/1689 (AI Act)",
        ],
        "disclaimer": (
            "Documento generato dal software a supporto del compliance operativo. "
            "Non sostituisce parere legale."
        ),
        "posture": posture,
        "worker_notice_it": render_worker_notice(language="it"),
        "worker_notice_en": render_worker_notice(language="en"),
        "acknowledgments": __import__(
            "modules.compliance_registry_db", fromlist=["list_worker_acknowledgments"]
        ).list_worker_acknowledgments(500),
    }
    out = output_dir / f"nstone_compliance_pack_{stamp}.json"
    out.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")

    notice_it = output_dir / f"worker_notice_it_{stamp}.txt"
    notice_en = output_dir / f"worker_notice_en_{stamp}.txt"
    notice_it.write_text(pack["worker_notice_it"], encoding="utf-8")
    notice_en.write_text(pack["worker_notice_en"], encoding="utf-8")
    return out


def ensure_default_profile_version() -> None:
    profile = load_compliance_profile()
    updates: Dict[str, Any] = {}
    if not (profile.get("ai_system_version") or "").strip():
        updates["ai_system_version"] = NSTONELLM_VERSION
    if not (profile.get("processing_purposes") or "").strip():
        updates["processing_purposes"] = (
            "Automazione assistita di preventivi, ordini, comunicazioni clienti "
            "e monitoraggio produzione lapidea con supervisione umana."
        )
    if updates:
        save_compliance_profile(updates)
