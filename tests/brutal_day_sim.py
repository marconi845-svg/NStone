"""
NStone 1 — Brutal Day Simulation (DRY-RUN)

Fase A — giornata operativa senza mail/PLC reali:
  pricing, offerte, policy, ordini, CNC governor, override, contratti, kill switch

Fase B — torture:
  email sporche, stress loop governor/pricing, probe Ollama opzionale

Uso:
  python tests/brutal_day_sim.py
  python tests/brutal_day_sim.py --stress 50
  python tests/brutal_day_sim.py --stress 50 --ollama
  python -m pytest tests/brutal_day_sim.py -q
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class DayReport:
    steps: List[StepResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(StepResult(name, ok, detail))

    @property
    def passed(self) -> int:
        return sum(1 for s in self.steps if s.ok)

    @property
    def failed(self) -> int:
        return sum(1 for s in self.steps if not s.ok)

    def print_report(self) -> None:
        print()
        print("=" * 72)
        print("NStone 1 — BRUTAL DAY SIMULATION (DRY-RUN)")
        print("=" * 72)
        for s in self.steps:
            mark = "PASS" if s.ok else "FAIL"
            line = f"[{mark}] {s.name}"
            if s.detail:
                line += f" — {s.detail}"
            print(line)
        print("-" * 72)
        print(f"Result: {self.passed} passed, {self.failed} failed, {len(self.steps)} total")
        print("=" * 72)


def _run(report: DayReport, name: str, fn: Callable[[], str]) -> None:
    try:
        detail = fn() or ""
        report.add(name, True, detail)
    except Exception as exc:
        report.add(name, False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_pricing(report: DayReport) -> None:
    def body() -> str:
        from modules.pricing_engine import calculate_quotation_pricing
        from modules.pricing_labor_db import ensure_pricing_labor_table
        from modules.quotation_request_parser import parse_quotation_request

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pricing.sqlite"
            ensure_pricing_labor_table(db_path=db)
            with patch(
                "modules.pricing_labor_db.get_database_path",
                return_value=db,
            ):
                parsed = parse_quotation_request(
                    "Preventivo 12 pezzi 60x240 cm Carrara lucidato"
                )
                assert parsed.pieces, "parser non ha trovato pezzi"
                carrara = {
                    "Name": "Bianco Carrara CD",
                    "Type": "Marble",
                    "Finish": "Polished",
                    "Thickness": "2",
                    "Dimensions": "305x152",
                    "Stock": "550",
                    "Price": "75",
                }
                result = calculate_quotation_pricing(
                    "Vorrei 25 mq di Carrara CD 2cm lucido",
                    [carrara],
                )
                assert result is not None
                assert result.mq_net == 25.0
                assert result.total_ex_works_eur == 25.0 * 75.0
                return (
                    f"parser={parsed.request_type}, "
                    f"mq={result.mq_net}, total={result.total_ex_works_eur}€"
                )

    _run(report, "01 pricing + parse richiesta", body)


def scenario_quotation_draft(report: DayReport) -> None:
    def body() -> str:
        from modules import incoming_requests_db as ird
        from modules import quotation_auto_pipeline as qap

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nstonellm.db"
            ird.set_database_path(db)
            try:
                ird.ensure_incoming_request_table(db_path=db)
                rid = "brutal-quote-1"
                ird.insert_incoming_request(
                    {
                        "id": rid,
                        "timestamp": "2026-08-07T09:00:00",
                        "nome": "Mario Test",
                        "email": "mario@example.com",
                        "messaggio": "Preventivo Carrara 100mq 2cm",
                        "stato": "NUOVA",
                    },
                    db_path=db,
                )
                with patch(
                    "modules.gemini_module.generate_reply_for_client",
                    return_value="Bozza offerta dry-run Carrara 100mq",
                ):
                    result = qap.elaborate_quotation_request(rid, send_email=False)
                assert result.get("ok") is True
                assert result.get("email_sent") is False
                row = ird.get_incoming_request(rid, db_path=db)
                assert row["stato"] == "BOZZA_IN_ATTESA"
                assert "Bozza" in (row.get("risposta_gemini") or "")
                return f"stato={row['stato']}, email_sent=False"
            finally:
                ird.set_database_path(None)

    _run(report, "02 offerta: bozza senza invio SMTP", body)


def scenario_quotation_policy_blocks_auto(report: DayReport) -> None:
    def body() -> str:
        from modules import incoming_requests_db as ird
        from modules import quotation_auto_pipeline as qap

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nstonellm.db"
            ird.set_database_path(db)
            try:
                ird.ensure_incoming_request_table(db_path=db)
                ird.insert_incoming_request(
                    {
                        "id": "brutal-quote-block",
                        "timestamp": "2026-08-07T09:05:00",
                        "nome": "Luca",
                        "email": "luca@example.com",
                        "messaggio": "Offerta granito",
                        "stato": "NUOVA",
                    },
                    db_path=db,
                )
                with patch.object(qap, "office_may_auto_email", return_value=False):
                    out = qap.process_pending_nuova_requests()
                assert out.get("processed") == 0
                row = ird.get_incoming_request("brutal-quote-block", db_path=db)
                assert row["stato"] == "NUOVA"
                return "auto-email bloccata, richiesta resta NUOVA"
            finally:
                ird.set_database_path(None)

    _run(report, "03 policy: nessuna auto-email a bassa autonomia", body)


def scenario_order_intake_ok(report: DayReport) -> None:
    def body() -> str:
        from modules.order_intake_pipeline import process_new_order_intake

        email = {
            "from": "Mario <mario@example.com>",
            "subject": "Ordine Carrara",
            "body": "Vorrei 30 mq lastre Carrara 2 cm",
            "timestamp": "2026-08-07T10:00:00",
        }
        order = {
            "order_id": "brutal_order_ok",
            "client_email": "mario@example.com",
            "client": "mario",
            "product": "Ordine Carrara",
            "email_subject": "Ordine Carrara",
            "email_body": email["body"],
            "status": "NEW",
        }
        with patch(
            "modules.orders_database.get_order_by_order_id",
            return_value=order,
        ), patch(
            "modules.order_stock_check.check_material_availability",
            return_value={"availability": "available", "message": "ok"},
        ), patch(
            "modules.order_confirmation_pipeline.dispatch_order_acknowledgment",
            return_value=True,
        ) as mock_dispatch:
            ok = process_new_order_intake("brutal_order_ok", email, use_llm=False)
        assert ok is True
        analysis = mock_dispatch.call_args.args[1]
        assert analysis["status"] == "confirmed"
        return f"ack status={analysis['status']}"

    _run(report, "04 ordine: intake + stock OK + ack (SMTP mock)", body)


def scenario_order_stock_partial(report: DayReport) -> None:
    def body() -> str:
        from modules.order_intake_pipeline import process_new_order_intake

        email = {
            "from": "Sara <sara@example.com>",
            "subject": "Ordine Granito Nero",
            "body": "200 mq Granito Nero Assoluto",
            "timestamp": "2026-08-07T10:30:00",
        }
        order = {
            "order_id": "brutal_order_partial",
            "client_email": "sara@example.com",
            "client": "sara",
            "product": "Granito Nero",
            "email_subject": email["subject"],
            "email_body": email["body"],
            "status": "NEW",
        }
        with patch(
            "modules.orders_database.get_order_by_order_id",
            return_value=order,
        ), patch(
            "modules.order_stock_check.check_material_availability",
            return_value={
                "availability": "partial",
                "message": "disponibili solo 40 mq",
            },
        ), patch(
            "modules.order_confirmation_pipeline.dispatch_order_acknowledgment",
            return_value=True,
        ) as mock_dispatch:
            ok = process_new_order_intake(
                "brutal_order_partial", email, use_llm=False
            )
        assert ok is True
        analysis = mock_dispatch.call_args.args[1]
        # rule-based intake conferma comunque la presa in carico
        assert "confirmation_email_text" in analysis
        return f"availability=partial, status={analysis.get('status')}"

    _run(report, "05 ordine: stock parziale gestito senza crash", body)


def scenario_cnc_governor_shadow(report: DayReport) -> None:
    def body() -> str:
        from core.autonomy_policy import PolicyResult
        from plc.plc_write_governor import (
            WritableVar,
            WriteGovernor,
            WriteRequest,
            parse_model_intent,
        )

        class Allow:
            def allow(self, action, ctx=None):
                return PolicyResult(True, "brutal: allow")

        feed = WritableVar(
            name="cmd_feed_override",
            db_number=101,
            offset=0,
            var_type="REAL",
            unit="%",
            min_value=50.0,
            max_value=120.0,
            max_step=10.0,
            min_delta=1.0,
            cooldown_s=10.0,
            allowed_states=("RUN", "HOLD"),
            step_reference="feed_override",
        )
        gov = WriteGovernor(
            "cnc",
            variables=[feed],
            placeholder=False,
            policy=Allow(),
            shadow=True,
            audit_fn=lambda d: None,
        )
        status = {
            "machine_state": "RUN",
            "raw_values": {"feed_override": 100.0},
        }

        # Proposta valida
        intent, err = parse_model_intent(
            '{"action":"write","variable":"cmd_feed_override",'
            '"value":92.0,"reason":"carico alto"}'
        )
        assert err == "" and intent["action"] == "write"
        d_ok = gov.execute(
            WriteRequest("cnc", "cmd_feed_override", 92.0, "carico alto"),
            current_status=status,
            human_approved=True,
        )
        assert d_ok.allowed and not d_ok.executed

        # No-op
        d_noop = gov.evaluate(
            WriteRequest("cnc", "cmd_feed_override", 100.0, "inutile"),
            current_status=status,
            human_approved=True,
        )
        assert not d_noop.allowed

        # Fuori range
        d_range = gov.evaluate(
            WriteRequest("cnc", "cmd_feed_override", 300.0, "pazzia"),
            current_status=status,
            human_approved=True,
        )
        assert not d_range.allowed

        # Intent malformato
        bad, bad_err = parse_model_intent("Alza pure il feed del 20% grazie")
        assert bad is None and bad_err

        return "valid+shadow / no-op / range / parser OK"

    _run(report, "06 CNC: governor shadow + rifiuti deterministici", body)


def scenario_override_protocol(report: DayReport) -> None:
    def body() -> str:
        from core.autonomy_policy import PolicyResult
        from plc.plc_override_protocol import (
            OverrideProtocol,
            OverrideState,
            ProtocolMode,
            SimulatedOverrideTransport,
        )
        from plc.plc_write_governor import WritableVar, WriteGovernor, WriteRequest

        class Allow:
            def allow(self, action, ctx=None):
                return PolicyResult(True, "brutal: allow")

        class Clock:
            def __init__(self):
                self.t = 0.0

            def __call__(self):
                return self.t

            def sleep(self, s):
                self.t += s

        feed = WritableVar(
            name="cmd_feed_override",
            db_number=101,
            offset=0,
            var_type="REAL",
            min_value=50.0,
            max_value=120.0,
            max_step=10.0,
            min_delta=1.0,
            cooldown_s=10.0,
            allowed_states=("RUN",),
            step_reference="feed_override",
        )
        clock = Clock()
        gov = WriteGovernor(
            "cnc",
            variables=[feed],
            placeholder=False,
            policy=Allow(),
            clock=clock,
            audit_fn=lambda d: None,
        )
        status = {
            "machine_state": "RUN",
            "raw_values": {"feed_override": 100.0},
        }
        req = WriteRequest(
            "cnc", "cmd_feed_override", 95.0, "bench", source="operator"
        )

        # SHADOW: nessuna richiesta al transport
        transport = SimulatedOverrideTransport()
        shadow = OverrideProtocol(
            gov,
            mode=ProtocolMode.SHADOW,
            transport=transport,
            clock=clock,
            sleep=clock.sleep,
            audit_fn=lambda r: None,
        )
        r1 = shadow.submit(req, current_status=status, human_approved=True)
        assert r1.state == OverrideState.SHADOW_APPROVED
        assert transport.requests == []

        # BENCH live remoto bloccato
        bench = OverrideProtocol(
            gov,
            mode=ProtocolMode.BENCH,
            transport=SimulatedOverrideTransport(),
            clock=clock,
            sleep=clock.sleep,
            audit_fn=lambda r: None,
        )
        r2 = bench.submit(
            req,
            current_status=status,
            human_approved=True,
            plc_mode="live",
            plc_ip="192.168.1.50",
        )
        assert r2.state == OverrideState.REJECTED

        # BENCH locale verificato
        local_transport = SimulatedOverrideTransport()
        bench_ok = OverrideProtocol(
            gov,
            mode=ProtocolMode.BENCH,
            transport=local_transport,
            timeout_s=0.2,
            poll_interval_s=0.05,
            clock=clock,
            sleep=clock.sleep,
            audit_fn=lambda r: None,
        )
        r3 = bench_ok.submit(
            req,
            current_status=status,
            human_approved=True,
            plc_mode="sim",
            plc_ip="127.0.0.1",
        )
        assert r3.state == OverrideState.VERIFIED
        return f"shadow={r1.state.value}, live_block={r2.state.value}, bench={r3.state.value}"

    _run(report, "07 override protocol: shadow + bench locale + live bloccato", body)


def scenario_contracts_and_placeholder(report: DayReport) -> None:
    def body() -> str:
        from core.governance_schemas import build_map_contract_report
        from plc.plc_write_governor import WriteGovernor, WriteRequest, map_is_placeholder
        from core.autonomy_policy import PolicyResult

        class Allow:
            def allow(self, action, ctx=None):
                return PolicyResult(True, "ok")

        assert map_is_placeholder("oem_cnc_v1") is True
        report_map = build_map_contract_report("oem_cnc_v1")
        assert report_map["valid"] is True
        assert report_map["placeholder"] is True
        assert report_map["override_protocol"]["live_transport_implemented"] is False

        # Con profilo reale placeholder il governor rifiuta tutto
        gov = WriteGovernor(
            "cnc",
            profile_id="oem_cnc_v1",
            policy=Allow(),
            audit_fn=lambda d: None,
        )
        d = gov.evaluate(
            WriteRequest("cnc", "cmd_feed_override", 95.0, "x"),
            current_status={
                "machine_state": "RUN",
                "raw_values": {"feed_override": 100.0},
            },
            human_approved=True,
        )
        assert d.allowed is False
        return (
            f"contracts valid={report_map['valid']}, "
            f"writable={report_map['writable_valid']}/{report_map['writable_total']}, "
            f"placeholder blocks writes"
        )

    _run(report, "08 contratti dati + placeholder blocca scritture", body)


def scenario_kill_switch(report: DayReport) -> None:
    def body() -> str:
        from core.autonomy_policy import Action, ActionContext, AutonomyPolicy

        settings = {
            "autonomy": {
                "level": 2,
                "max_level": 2,
                "agents_paused": True,
                "plant_auto_plc_write": True,
                "plant_sim_only": True,
                "office_auto_email": True,
                "office_auto_stock": False,
                "require_pin_above": 2,
                "admin_pin_hash": "",
            },
            "agents": {"enabled": ["office", "plant"]},
            "commercial": {"tone": 1, "max_tone": 2},
        }
        policy = AutonomyPolicy(settings)
        plc = policy.allow(
            Action.PLC_WRITE,
            ActionContext(machine_id="cnc", human_approved=True, plc_mode="sim"),
        )
        mail = policy.allow(Action.SEND_CLIENT_EMAIL)
        assert plc.allowed is False
        assert mail.allowed is False
        assert "Kill switch" in plc.reason or "paused" in plc.reason.lower()
        return f"PLC={plc.reason}; email blocked"

    _run(report, "09 kill switch blocca PLC write e auto-email", body)


def scenario_fault_ollama_and_empty(report: DayReport) -> None:
    def body() -> str:
        from modules import incoming_requests_db as ird
        from modules import quotation_auto_pipeline as qap
        from modules.gemini_module import GeminiReplyError

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nstonellm.db"
            ird.set_database_path(db)
            try:
                ird.ensure_incoming_request_table(db_path=db)
                rid = "brutal-ollama-down"
                ird.insert_incoming_request(
                    {
                        "id": rid,
                        "timestamp": "2026-08-07T11:00:00",
                        "nome": "Paolo",
                        "email": "paolo@example.com",
                        "messaggio": "Preventivo",
                        "stato": "NUOVA",
                    },
                    db_path=db,
                )

                def boom(_data):
                    raise GeminiReplyError("ollama unreachable", code="llm_down")

                with patch(
                    "modules.gemini_module.generate_reply_for_client",
                    side_effect=boom,
                ):
                    result = qap.elaborate_quotation_request(rid, send_email=False)
                assert result.get("ok") is False
                row = ird.get_incoming_request(rid, db_path=db)
                assert row["stato"] == "ERRORE"
                return f"stato={row['stato']}, no crash, no email"
            finally:
                ird.set_database_path(None)

    _run(report, "10 guasto: LLM/Ollama assente → ERRORE senza invio", body)


def scenario_cnc_ready_rejects_write(report: DayReport) -> None:
    def body() -> str:
        from core.autonomy_policy import PolicyResult
        from plc.plc_write_governor import WritableVar, WriteGovernor, WriteRequest

        class Allow:
            def allow(self, action, ctx=None):
                return PolicyResult(True, "ok")

        feed = WritableVar(
            name="cmd_feed_override",
            db_number=101,
            offset=0,
            var_type="REAL",
            min_value=50.0,
            max_value=120.0,
            max_step=10.0,
            min_delta=1.0,
            allowed_states=("RUN", "HOLD"),
            step_reference="feed_override",
        )
        gov = WriteGovernor(
            "cnc",
            variables=[feed],
            placeholder=False,
            policy=Allow(),
            audit_fn=lambda d: None,
        )
        d = gov.evaluate(
            WriteRequest("cnc", "cmd_feed_override", 95.0, "x"),
            current_status={
                "machine_state": "READY",
                "raw_values": {"feed_override": 100.0},
            },
            human_approved=True,
        )
        assert d.allowed is False
        failed = {c.name for c in d.failed_checks()}
        assert "machine_state_allowed" in failed
        return "READY → write rejected"

    _run(report, "11 CNC: stato READY rifiuta override", body)


# ---------------------------------------------------------------------------
# Fase B — torture
# ---------------------------------------------------------------------------

DIRTY_EMAIL_CASES = [
    # (subject, body, sender, expected_tipo)
    (
        "Ordine",
        "Confermo l ordine per 100 mq Botticino lastre lucide.",
        "cliente@example.com",
        "CONFERMA",
    ),
    (
        "Richiesta ordine marmo",
        "Vorrei 50 mq di Carrara spessore 2cm",
        "cliente@example.com",
        "ORDINE",
    ),
    (
        "Newsletter pietra naturale",
        "Scopri le ultime lastre in promo questo mese",
        "marketing@stonepromo.com",
        "NON_RILEVANTE",
    ),
    (
        "RE: Offerta",
        "Ok procediamo, accettato. Grazie",
        "buyer@fab.com",
        "CONFERMA",
    ),
    (
        "Ciao",
        "Mi potete richiamare?",
        "random@mail.com",
        "NON_RILEVANTE",
    ),
    (
        "Purchase order PO-9921",
        "Please supply 20 sqm white marble slabs 2cm",
        "buyer@usfab.com",
        "ORDINE",
    ),
    (
        "Quotation request",
        "Need quote for Taj Mahal quartzite 30 sqm",
        "info@studio.com",
        "ORDINE",
    ),
    (
        "Ordine urgente!!!",
        "???????? quantita???",
        "confused@client.it",
        "ORDINE",
    ),
    (
        "",
        "",
        "",
        "NON_RILEVANTE",
    ),
    (
        "FWD: Ordine Carrara",
        "Inoltro: vorremmo 12 mq lastre",
        "segreteria@studio.it",
        "ORDINE",
    ),
]


def scenario_dirty_emails(report: DayReport) -> None:
    def body() -> str:
        from modules.email_classifier import classify_email_with_rules
        from modules.quotation_request_parser import parse_quotation_request

        mismatches = []
        for subject, body_text, sender, expected in DIRTY_EMAIL_CASES:
            tipo, _conf = classify_email_with_rules(subject, body_text, sender)
            if tipo != expected:
                mismatches.append(
                    f"{subject!r}->{tipo} (atteso {expected})"
                )

        # Parser non deve crashare su testo sporco
        for msg in (
            "",
            "asdf qwerty",
            "1000000 mq di materiale inesistente XYZ",
            "pezzi 60x240 senza materiale",
            "Preventivo\n" + ("spam " * 500),
        ):
            parsed = parse_quotation_request(msg)
            assert parsed is not None

        if mismatches:
            raise AssertionError("; ".join(mismatches[:5]))
        return f"{len(DIRTY_EMAIL_CASES)} classificazioni + parser anti-crash"

    _run(report, "12 email sporche: classificazione + parser robusto", body)


def scenario_stress_loop(report: DayReport, cycles: int = 50) -> None:
    def body() -> str:
        from core.autonomy_policy import PolicyResult
        from modules.pricing_engine import calculate_quotation_pricing
        from modules.pricing_labor_db import ensure_pricing_labor_table
        from plc.plc_write_governor import WritableVar, WriteGovernor, WriteRequest

        class Allow:
            def allow(self, action, ctx=None):
                return PolicyResult(True, "ok")

        feed = WritableVar(
            name="cmd_feed_override",
            db_number=101,
            offset=0,
            var_type="REAL",
            min_value=50.0,
            max_value=120.0,
            max_step=10.0,
            min_delta=1.0,
            cooldown_s=0.0,  # stress: niente cooldown tra cicli
            allowed_states=("RUN",),
            step_reference="feed_override",
        )
        gov = WriteGovernor(
            "cnc",
            variables=[feed],
            placeholder=False,
            policy=Allow(),
            shadow=True,
            audit_fn=lambda d: None,
        )
        carrara = {
            "Name": "Bianco Carrara CD",
            "Type": "Marble",
            "Finish": "Polished",
            "Thickness": "2",
            "Dimensions": "305x152",
            "Stock": "550",
            "Price": "75",
        }

        allowed = rejected = 0
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pricing.sqlite"
            ensure_pricing_labor_table(db_path=db)
            with patch(
                "modules.pricing_labor_db.get_database_path",
                return_value=db,
            ):
                for i in range(cycles):
                    mq = 10.0 + (i % 20)
                    priced = calculate_quotation_pricing(
                        f"Vorrei {mq} mq di Carrara CD 2cm lucido",
                        [carrara],
                    )
                    assert priced is not None
                    assert priced.total_ex_works_eur == mq * 75.0

                    # Alterna proposte valide e rifiuti
                    feed_now = 100.0
                    status = {
                        "machine_state": "RUN",
                        "raw_values": {"feed_override": feed_now},
                    }
                    if i % 3 == 0:
                        value = 300.0  # fuori range
                    elif i % 3 == 1:
                        value = 100.0  # no-op
                    else:
                        value = 92.0  # valida
                    d = gov.execute(
                        WriteRequest(
                            "cnc",
                            "cmd_feed_override",
                            value,
                            f"stress-{i}",
                        ),
                        current_status=status,
                        human_approved=True,
                    )
                    if d.allowed:
                        allowed += 1
                        assert d.executed is False  # shadow
                    else:
                        rejected += 1

        elapsed = time.perf_counter() - t0
        assert allowed + rejected == cycles
        assert allowed > 0 and rejected > 0
        return (
            f"{cycles} cicli in {elapsed:.2f}s "
            f"(governor allow={allowed} reject={rejected}, sempre shadow)"
        )

    _run(report, f"13 stress loop x{cycles}: pricing + governor", body)


def scenario_double_click_approve(report: DayReport) -> None:
    def body() -> str:
        from core.autonomy_policy import PolicyResult
        from plc.plc_write_governor import WritableVar, WriteGovernor, WriteRequest

        class Allow:
            def allow(self, action, ctx=None):
                return PolicyResult(True, "ok")

        class Clock:
            def __init__(self):
                self.t = 1000.0

            def __call__(self):
                return self.t

        clock = Clock()
        feed = WritableVar(
            name="cmd_feed_override",
            db_number=101,
            offset=0,
            var_type="REAL",
            min_value=50.0,
            max_value=120.0,
            max_step=10.0,
            min_delta=1.0,
            cooldown_s=10.0,
            allowed_states=("RUN",),
            step_reference="feed_override",
        )
        gov = WriteGovernor(
            "cnc",
            variables=[feed],
            placeholder=False,
            policy=Allow(),
            shadow=True,
            clock=clock,
            audit_fn=lambda d: None,
        )
        status = {
            "machine_state": "RUN",
            "raw_values": {"feed_override": 100.0},
        }
        first = gov.execute(
            WriteRequest("cnc", "cmd_feed_override", 92.0, "first"),
            current_status=status,
            human_approved=True,
        )
        second = gov.execute(
            WriteRequest("cnc", "cmd_feed_override", 93.0, "double-click"),
            current_status={
                "machine_state": "RUN",
                "raw_values": {"feed_override": 92.0},
            },
            human_approved=True,
        )
        assert first.allowed is True
        assert second.allowed is False
        assert any(c.name == "cooldown" and not c.passed for c in second.checks)
        return "secondo approve entro cooldown rifiutato"

    _run(report, "14 doppio click approve: cooldown fail-closed", body)


def scenario_state_changed_before_approve(report: DayReport) -> None:
    def body() -> str:
        from core.autonomy_policy import PolicyResult
        from plc.plc_write_governor import WritableVar, WriteGovernor, WriteRequest

        class Allow:
            def allow(self, action, ctx=None):
                return PolicyResult(True, "ok")

        feed = WritableVar(
            name="cmd_feed_override",
            db_number=101,
            offset=0,
            var_type="REAL",
            min_value=50.0,
            max_value=120.0,
            max_step=10.0,
            min_delta=1.0,
            allowed_states=("RUN", "HOLD"),
            step_reference="feed_override",
        )
        gov = WriteGovernor(
            "cnc",
            variables=[feed],
            placeholder=False,
            policy=Allow(),
            shadow=True,
            audit_fn=lambda d: None,
        )
        preview = gov.evaluate(
            WriteRequest("cnc", "cmd_feed_override", 92.0, "ok"),
            current_status={
                "machine_state": "RUN",
                "raw_values": {"feed_override": 100.0},
            },
            human_approved=True,
        )
        assert preview.allowed is True
        # Tra proposta e approve la macchina va in ERROR
        late = gov.execute(
            WriteRequest("cnc", "cmd_feed_override", 92.0, "ok"),
            current_status={
                "machine_state": "ERROR",
                "raw_values": {"feed_override": 100.0},
            },
            human_approved=True,
        )
        assert late.allowed is False
        return "proposta ok, approve su ERROR rifiutata"

    _run(report, "15 race: stato cambia prima dell'approve", body)


def scenario_ollama_probe(report: DayReport) -> None:
    def body() -> str:
        url = "http://127.0.0.1:11434/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return f"SKIP Ollama non raggiungibile ({exc})"

        models = [m.get("name", "") for m in data.get("models") or []]
        if not models:
            return "SKIP Ollama su ma nessun modello"

        # Micro-generate: solo se Qwen è presente, altrimenti primo modello
        preferred = next(
            (m for m in models if "qwen" in m.lower()),
            models[0],
        )
        payload = json.dumps(
            {
                "model": preferred,
                "prompt": 'Reply with exactly: {"action":"none","reason":"probe"}',
                "stream": False,
                "options": {"temperature": 0, "num_predict": 40},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read().decode("utf-8")).get("response", "")

        from plc.plc_write_governor import parse_model_intent

        intent, err = parse_model_intent(out)
        if intent is None:
            # Probe di raggiungibilità OK anche se output non conforme
            return f"Ollama OK model={preferred}, intent non conforme: {err[:80]}"
        return f"Ollama OK model={preferred}, intent={intent.get('action')}"

    _run(report, "16 probe Ollama (opzionale)", body)


def run_day(
    *,
    stress_cycles: int = 50,
    probe_ollama: bool = False,
) -> DayReport:
    report = DayReport()
    # Fase A
    scenario_pricing(report)
    scenario_quotation_draft(report)
    scenario_quotation_policy_blocks_auto(report)
    scenario_order_intake_ok(report)
    scenario_order_stock_partial(report)
    scenario_cnc_governor_shadow(report)
    scenario_override_protocol(report)
    scenario_contracts_and_placeholder(report)
    scenario_kill_switch(report)
    scenario_fault_ollama_and_empty(report)
    scenario_cnc_ready_rejects_write(report)
    # Fase B
    scenario_dirty_emails(report)
    scenario_stress_loop(report, cycles=stress_cycles)
    scenario_double_click_approve(report)
    scenario_state_changed_before_approve(report)
    if probe_ollama:
        scenario_ollama_probe(report)
    return report


def test_brutal_day_simulation():
    """Entry point pytest: giornata A+B (stress ridotto, niente Ollama)."""
    report = run_day(stress_cycles=20, probe_ollama=False)
    failed = [s for s in report.steps if not s.ok]
    assert not failed, "; ".join(f"{s.name}: {s.detail}" for s in failed)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NStone brutal day dry-run")
    parser.add_argument(
        "--stress",
        type=int,
        default=50,
        help="Cicli stress pricing+governor (default 50)",
    )
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Aggiunge probe Ollama locale (skip soft se spento)",
    )
    args = parser.parse_args(argv)
    report = run_day(stress_cycles=args.stress, probe_ollama=args.ollama)
    report.print_report()
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
