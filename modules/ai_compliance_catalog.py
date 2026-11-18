"""
Catalogo requisiti compliance: L. 132/2025, D.Lgs. 152/1997, GDPR, AI Act (UE).

Riferimenti normativi a scopo documentale in-app — non consulenza legale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

CheckStatus = Literal["open", "partial", "done", "na"]


@dataclass(frozen=True)
class ComplianceRequirement:
    req_id: str
    domain: str
    title_it: str
    title_en: str
    legal_ref: str
    summary_it: str
    summary_en: str
    nstone_control: str
    auto_check: str  # key for automated posture probe, or ""


REQUIREMENTS: List[ComplianceRequirement] = [
    ComplianceRequirement(
        req_id="L132-11-TRANSPARENCY",
        domain="L. 132/2025",
        title_it="Trasparenza uso IA in ambito lavorativo",
        title_en="Workplace AI transparency",
        legal_ref="L. 132/2025 art. 11 co. 2; D.Lgs. 152/1997 art. 1-bis",
        summary_it=(
            "Il datore informa i lavoratori sull'impiego di sistemi di IA, finalità, "
            "logiche generali e diritti (inclusa supervisione umana)."
        ),
        summary_en=(
            "The employer informs workers about AI use, purposes, general logic, "
            "and rights (including human oversight)."
        ),
        nstone_control=(
            "AI Governance Center → Worker Information; registro presa visione; "
            "banner livello autonomia sulla dashboard."
        ),
        auto_check="worker_notice_published",
    ),
    ComplianceRequirement(
        req_id="L132-11-SAFE",
        domain="L. 132/2025",
        title_it="IA sicura, affidabile, non lesiva della dignità",
        title_en="Safe, reliable AI respecting human dignity",
        legal_ref="L. 132/2025 art. 11 co. 2",
        summary_it=(
            "L'utilizzo deve essere sicuro e trasparente; default conservativo "
            "(L0–L1) in produzione; kill switch agenti."
        ),
        summary_en=(
            "Use must be safe and transparent; conservative defaults (L0–L1) "
            "in production; agent kill switch."
        ),
        nstone_control=(
            "AutonomyPolicy L0–L4; agents_paused; L3–L4 solo lab/sim; "
            "Agents Command Center protetto da PIN."
        ),
        auto_check="autonomy_conservative",
    ),
    ComplianceRequirement(
        req_id="L132-11-NODISC",
        domain="L. 132/2025",
        title_it="Divieto discriminazioni algoritmiche",
        title_en="No algorithmic discrimination",
        legal_ref="L. 132/2025 art. 11 co. 3",
        summary_it=(
            "Nessuna decisione su rapporto di lavoro basata su categorie protette; "
            "NStone non valuta performance/disciplinary dei dipendenti."
        ),
        summary_en=(
            "No employment decisions on protected categories; NStone does not "
            "score employee performance or discipline."
        ),
        nstone_control=(
            "Scope limitato a ordini/preventivi/produzione; nessun modulo HR "
            "discriminatorio; audit azioni agenti."
        ),
        auto_check="scope_no_hr",
    ),
    ComplianceRequirement(
        req_id="GDPR-ART13",
        domain="GDPR",
        title_it="Informativa trattamento dati personali",
        title_en="Privacy notice for personal data",
        legal_ref="Reg. UE 2016/679 art. 13",
        summary_it=(
            "Titolare, finalità, base giuridica, conservazione, diritti "
            "interessato, contatto DPO."
        ),
        summary_en=(
            "Controller, purposes, legal basis, retention, data subject rights, DPO contact."
        ),
        nstone_control="AI Governance Center → Employer & Processing Register.",
        auto_check="profile_complete",
    ),
    ComplianceRequirement(
        req_id="GDPR-ART22",
        domain="GDPR",
        title_it="Decisioni automatizzate e supervisione umana",
        title_en="Automated decisions and human oversight",
        legal_ref="Reg. UE 2016/679 art. 22",
        summary_it=(
            "Comunicazioni/prezzi verso clienti: bozza o invio solo con policy L≥2; "
            "approvazione operatore tracciata."
        ),
        summary_en=(
            "Customer-facing quotes: draft-only or send at L≥2 with logged operator approval."
        ),
        nstone_control=(
            "autonomy_policy.allow(SEND_CLIENT_EMAIL); pending_actions; "
            "human_approved su PLC."
        ),
        auto_check="human_oversight_enabled",
    ),
    ComplianceRequirement(
        req_id="GDPR-ART35",
        domain="GDPR",
        title_it="Valutazione d'impatto (DPIA) ove applicabile",
        title_en="Data protection impact assessment where required",
        legal_ref="Reg. UE 2016/679 art. 35",
        summary_it=(
            "Checklist DPIA per trattamenti ad alto rischio (email ordini, LLM cloud, "
            "integrazione produzione)."
        ),
        summary_en=(
            "DPIA checklist for high-risk processing (order email, cloud LLM, plant integration)."
        ),
        nstone_control="AI Governance Center → DPIA Checklist con evidenze.",
        auto_check="dpia_reviewed",
    ),
    ComplianceRequirement(
        req_id="AIACT-TRANSPARENCY",
        domain="AI Act",
        title_it="Trasparenza verso utilizzatori professionisti",
        title_en="Transparency for professional deployers",
        legal_ref="Reg. UE 2024/1689 (AI Act) — obblighi deployer/fornitore",
        summary_it=(
            "Documentare capacità/limiti del sistema, log, override umano, "
            "versione modello e provider LLM."
        ),
        summary_en=(
            "Document system capabilities/limits, logs, human override, model version and LLM provider."
        ),
        nstone_control=(
            "System Register; export compliance pack; Settings → provider LLM."
        ),
        auto_check="system_register_complete",
    ),
    ComplianceRequirement(
        req_id="AIACT-OVERSIGHT",
        domain="AI Act",
        title_it="Supervisione umana effettiva",
        title_en="Effective human oversight",
        legal_ref="Reg. UE 2024/1689 — human oversight",
        summary_it=(
            "Operatore può ignorare, correggere o bloccare output agenti; "
            "registro autonomy_audit."
        ),
        summary_en=(
            "Operators can reject, correct, or block agent outputs; autonomy_audit log."
        ),
        nstone_control="Agents Command Center; Action Log; kill switch.",
        auto_check="audit_available",
    ),
    ComplianceRequirement(
        req_id="AIACT-LOGGING",
        domain="AI Act",
        title_it="Registro eventi e tracciabilità",
        title_en="Event logging and traceability",
        legal_ref="Reg. UE 2024/1689 — logging (high-risk systems)",
        summary_it="Conservare log policy e azioni approvate per audit e incident response.",
        summary_en="Retain policy and approved-action logs for audit and incident response.",
        nstone_control="autonomy_audit, pending_actions, agent_messages in nstonellm.db.",
        auto_check="audit_available",
    ),
    ComplianceRequirement(
        req_id="NSTONE-LICENSE-CAP",
        domain="NStone Governance",
        title_it="Cap licenza autonomia (tier commerciale)",
        title_en="Autonomy license cap (commercial tier)",
        legal_ref="Best practice / contratto licenza",
        summary_it=(
            "max_level limita automazione vendibile; upgrade L2+ solo con contratto "
            "e formazione."
        ),
        summary_en=(
            "max_level caps sellable automation; L2+ upgrade only with contract and training."
        ),
        nstone_control="agents_config.max_level; license cap in Command Center.",
        auto_check="license_cap_set",
    ),
]

REQUIREMENT_BY_ID = {r.req_id: r for r in REQUIREMENTS}

WORKER_NOTICE_TEMPLATE_IT = """INFORMATIVA AI — LAVORATORI
(L. 132/2025 art. 11; D.Lgs. 152/1997 art. 1-bis; GDPR art. 13)

Datore di lavoro: {employer_name}
Sede / reparto: {workplace_site}
Sistema: {ai_system_name} (versione {ai_system_version})

1. FINALITÀ
Il software NStone utilizza componenti di intelligenza artificiale (LLM) per:
- classificare email e richieste commerciali;
- proporre bozze di preventivo e risposte ordini;
- suggerire azioni di produzione (monitoraggio macchine / PLC);
- assistere operatori e ufficio — non sostituisce il giudizio umano.

Finalità dichiarate dal titolare: {processing_purposes}

2. LOGICA GENERALE
Le decisioni automatiche sono governate da livelli di autonomia (L0–L4).
In produzione il default consigliato è L0–L1 (suggerimenti / approvazione obbligatoria).
Ogni azione rilevante può essere registrata nel registro audit.

3. SUPERVISIONE UMANA
L'operatore può approvare, rifiutare o modificare ogni suggerimento.
Il livello di autonomia è configurabile solo da personale autorizzato (PIN).
Kill switch disponibile per sospendere gli agenti.

4. DATI PERSONALI
Possono essere trattati: email clienti, nomi, riferimenti ordini, contenuti comunicazioni.
Base giuridica indicata: {legal_basis}
Conservazione indicativa: {retention_days} giorni (salvo obblighi di legge).

5. DIRITTI
I lavoratori e gli interessati possono esercitare i diritti GDPR (accesso, rettifica,
cancellazione, limitazione, opposizione) contattando: {dpo_contact}

6. NON DISCRIMINAZIONE
Il sistema non è utilizzato per valutazioni disciplinari o assunzioni basate su
categorie protette (L. 132/2025 art. 11 co. 3).

Versione informativa: {notice_version}
Data pubblicazione: {published_at}

---
Dichiarazione di presa visione (compilare in AI Governance Center):
Ho ricevuto e compreso l'informativa sull'uso dell'intelligenza artificiale.
"""

WORKER_NOTICE_TEMPLATE_EN = """AI WORKER NOTICE
(Italy L. 132/2025 art. 11; Legislative Decree 152/1997 art. 1-bis; GDPR art. 13)

Employer: {employer_name}
Site / department: {workplace_site}
System: {ai_system_name} (version {ai_system_version})

1. PURPOSE
NStone uses AI (LLM) components to:
- classify emails and commercial requests;
- draft quotations and order replies;
- suggest production actions (machine / PLC monitoring);
- assist office and shop-floor staff — not replace human judgment.

Declared purposes: {processing_purposes}

2. GENERAL LOGIC
Automated decisions are governed by autonomy levels (L0–L4).
Production default: L0–L1 (suggestions / mandatory approval).
Relevant actions are logged in the audit register.

3. HUMAN OVERSIGHT
Operators can approve, reject, or edit every suggestion.
Autonomy level changes require authorized personnel (PIN).
Kill switch available to pause all agents.

4. PERSONAL DATA
May process: customer emails, names, order references, communication content.
Legal basis: {legal_basis}
Retention (indicative): {retention_days} days (unless legal obligations differ).

5. RIGHTS
Workers and data subjects may exercise GDPR rights by contacting: {dpo_contact}

6. NON-DISCRIMINATION
The system is not used for disciplinary or hiring decisions on protected categories.

Notice version: {notice_version}
Published: {published_at}

---
Acknowledgment (record in AI Governance Center):
I have received and understood the AI workplace notice.
"""
