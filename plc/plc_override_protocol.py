"""
Protocollo deterministico per un piccolo override CNC (SHADOW / BENCH).

Scopo ristretto:
  - unica variabile ammessa: cmd_feed_override;
  - il governor deve approvare prima della richiesta;
  - sequence number per correlare request/ack;
  - ACK PLC obbligatorio;
  - read-back obbligatorio e confrontato col valore richiesto;
  - timeout, serializzazione e audit;
  - nessun trasporto PLC LIVE implementato.

Questo modulo prepara il command/ack da concordare con OEM. Non abilita
scritture reali: BENCH accetta soltanto modalità sim/bench su localhost e
richiede un transport esplicito (nei test: SimulatedOverrideTransport).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

from plc.plc_write_governor import WriteDecision, WriteGovernor, WriteRequest


ALLOWED_OVERRIDE_VARIABLES = frozenset({"cmd_feed_override"})
LOCAL_ENDPOINTS = frozenset({"", "127.0.0.1", "localhost", "::1"})
MAX_SEQUENCE = 32767  # compatibile con un INT S7 positivo


class ProtocolMode(Enum):
    SHADOW = "shadow"
    BENCH = "bench"


class OverrideState(Enum):
    REJECTED = "rejected"
    SHADOW_APPROVED = "shadow_approved"
    TRANSPORT_ERROR = "transport_error"
    ACK_REJECTED = "ack_rejected"
    TIMED_OUT = "timed_out"
    READBACK_MISMATCH = "readback_mismatch"
    VERIFIED = "verified"


@dataclass(frozen=True)
class OverrideAck:
    sequence: int
    accepted: bool
    error_code: int = 0
    message: str = ""


@dataclass
class OverrideResult:
    sequence: int
    state: OverrideState
    reason: str
    request: WriteRequest
    decision: Optional[WriteDecision] = None
    ack: Optional[OverrideAck] = None
    readback_value: Optional[float] = None
    elapsed_ms: float = 0.0

    @property
    def allowed(self) -> bool:
        return self.state in (
            OverrideState.SHADOW_APPROVED,
            OverrideState.VERIFIED,
        )

    @property
    def executed(self) -> bool:
        return self.state == OverrideState.VERIFIED

    def to_payload(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "state": self.state.value,
            "allowed": self.allowed,
            "executed": self.executed,
            "reason": self.reason,
            "request": {
                "machine_id": self.request.machine_id,
                "variable": self.request.variable,
                "value": self.request.value,
                "reason": self.request.reason,
                "source": self.request.source,
            },
            "ack": (
                {
                    "sequence": self.ack.sequence,
                    "accepted": self.ack.accepted,
                    "error_code": self.ack.error_code,
                    "message": self.ack.message,
                }
                if self.ack
                else None
            ),
            "readback_value": self.readback_value,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


class OverrideTransport(Protocol):
    """
    Contratto del futuro adapter OEM CNC.

    Nessuna implementazione Snap7 reale è fornita qui. L'implementazione OEM
    dovrà scrivere un DB di scambio dedicato, non offset interni scoperti.
    """

    def send_request(self, sequence: int, variable: str, value: float) -> bool:
        ...

    def poll_ack(self) -> Optional[OverrideAck]:
        ...

    def readback(self, variable: str) -> Optional[float]:
        ...


class OverrideProtocol:
    """Macchina a stati sincrona per request → ack → read-back."""

    def __init__(
        self,
        governor: WriteGovernor,
        *,
        mode: ProtocolMode = ProtocolMode.SHADOW,
        transport: Optional[OverrideTransport] = None,
        timeout_s: float = 2.0,
        poll_interval_s: float = 0.05,
        readback_tolerance: float = 0.01,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        audit_fn: Optional[Callable[[OverrideResult], None]] = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s deve essere > 0")
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s deve essere > 0")
        if readback_tolerance < 0:
            raise ValueError("readback_tolerance deve essere >= 0")
        self.governor = governor
        self.mode = mode
        self.transport = transport
        self.timeout_s = float(timeout_s)
        self.poll_interval_s = float(poll_interval_s)
        self.readback_tolerance = float(readback_tolerance)
        self._clock = clock
        self._sleep = sleep
        self._audit_fn = audit_fn
        self._sequence = 0
        self._lock = threading.Lock()

    def submit(
        self,
        request: WriteRequest,
        *,
        current_status: Any,
        human_approved: bool,
        plc_mode: str = "sim",
        plc_ip: str = "127.0.0.1",
    ) -> OverrideResult:
        """
        Valuta e, soltanto in BENCH locale, esegue il protocollo simulato.
        La lock impedisce due override contemporanei.
        """
        with self._lock:
            sequence = self._next_sequence()
            started = self._clock()

            if request.variable not in ALLOWED_OVERRIDE_VARIABLES:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.REJECTED,
                        "Protocollo ristretto: è ammesso solo cmd_feed_override",
                        request,
                    ),
                    started,
                )

            decision = self.governor.evaluate(
                request,
                current_status=current_status,
                human_approved=human_approved,
                plc_mode=plc_mode,
                plc_ip=plc_ip,
            )
            if not decision.allowed:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.REJECTED,
                        f"Governor: {decision.reason}",
                        request,
                        decision=decision,
                    ),
                    started,
                )

            if self.mode == ProtocolMode.SHADOW:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.SHADOW_APPROVED,
                        "SHADOW: override approvato ma nessuna richiesta inviata",
                        request,
                        decision=decision,
                    ),
                    started,
                )

            # Difesa esplicita: BENCH non può puntare a PLC live/remoti.
            if plc_mode not in ("sim", "bench") or plc_ip not in LOCAL_ENDPOINTS:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.REJECTED,
                        "BENCH bloccato: ammessi solo sim/bench su localhost",
                        request,
                        decision=decision,
                    ),
                    started,
                )
            if self.transport is None:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.TRANSPORT_ERROR,
                        "Nessun transport BENCH configurato",
                        request,
                        decision=decision,
                    ),
                    started,
                )

            try:
                sent = self.transport.send_request(
                    sequence, request.variable, float(request.value)
                )
            except Exception as exc:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.TRANSPORT_ERROR,
                        f"Errore invio richiesta: {exc}",
                        request,
                        decision=decision,
                    ),
                    started,
                )
            if not sent:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.TRANSPORT_ERROR,
                        "Transport ha rifiutato la richiesta",
                        request,
                        decision=decision,
                    ),
                    started,
                )

            ack = self._wait_matching_ack(sequence, started)
            if ack is None:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.TIMED_OUT,
                        f"ACK non ricevuto entro {self.timeout_s:.2f}s",
                        request,
                        decision=decision,
                    ),
                    started,
                )
            if not ack.accepted:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.ACK_REJECTED,
                        f"PLC ha rifiutato: code={ack.error_code} {ack.message}".strip(),
                        request,
                        decision=decision,
                        ack=ack,
                    ),
                    started,
                )

            try:
                readback = self.transport.readback(request.variable)
            except Exception as exc:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.TRANSPORT_ERROR,
                        f"Errore read-back: {exc}",
                        request,
                        decision=decision,
                        ack=ack,
                    ),
                    started,
                )
            if readback is None:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.READBACK_MISMATCH,
                        "Read-back non disponibile",
                        request,
                        decision=decision,
                        ack=ack,
                    ),
                    started,
                )

            expected = float(request.value)
            if abs(float(readback) - expected) > self.readback_tolerance:
                return self._finish(
                    OverrideResult(
                        sequence,
                        OverrideState.READBACK_MISMATCH,
                        f"Read-back {readback} != richiesto {expected} "
                        f"(tolleranza {self.readback_tolerance})",
                        request,
                        decision=decision,
                        ack=ack,
                        readback_value=float(readback),
                    ),
                    started,
                )

            # Solo ACK correlato + read-back corretto attivano cooldown/step.
            self.governor.record_protocol_verified(
                request.variable, request.value
            )
            return self._finish(
                OverrideResult(
                    sequence,
                    OverrideState.VERIFIED,
                    "ACK correlato e read-back verificato",
                    request,
                    decision=decision,
                    ack=ack,
                    readback_value=float(readback),
                ),
                started,
            )

    def _next_sequence(self) -> int:
        self._sequence = (self._sequence % MAX_SEQUENCE) + 1
        return self._sequence

    def _wait_matching_ack(
        self, sequence: int, started: float
    ) -> Optional[OverrideAck]:
        while self._clock() - started < self.timeout_s:
            try:
                ack = self.transport.poll_ack() if self.transport else None
            except Exception:
                return None
            if ack is not None and ack.sequence == sequence:
                return ack
            # ACK con sequence diversa è vecchio/estraneo: ignorato.
            self._sleep(self.poll_interval_s)
        return None

    def _finish(self, result: OverrideResult, started: float) -> OverrideResult:
        result.elapsed_ms = max(0.0, (self._clock() - started) * 1000.0)
        self._audit(result)
        return result

    def _audit(self, result: OverrideResult) -> None:
        if self._audit_fn is not None:
            self._audit_fn(result)
            return
        try:
            from modules.action_store import log_audit

            log_audit(
                "plc_write_override_protocol",
                result.allowed,
                result.reason,
                agent=result.request.source,
                payload=result.to_payload(),
            )
        except Exception:
            pass


class SimulatedOverrideTransport:
    """
    Transport esclusivamente da banco.

    auto_ack=False simula un timeout. Stale ACK possono essere accodati per
    testare la correlazione via sequence number.
    """

    def __init__(
        self,
        *,
        auto_ack: bool = True,
        accept: bool = True,
        error_code: int = 0,
        readback_offset: float = 0.0,
    ) -> None:
        self.auto_ack = auto_ack
        self.accept = accept
        self.error_code = error_code
        self.readback_offset = float(readback_offset)
        self.requests: List[Dict[str, Any]] = []
        self._acks: List[OverrideAck] = []
        self._values: Dict[str, float] = {}
        self._seen_sequences = set()

    def queue_ack(self, ack: OverrideAck) -> None:
        self._acks.append(ack)

    def send_request(self, sequence: int, variable: str, value: float) -> bool:
        if sequence in self._seen_sequences:
            return False  # idempotenza: sequence duplicata
        self._seen_sequences.add(sequence)
        self.requests.append(
            {"sequence": sequence, "variable": variable, "value": float(value)}
        )
        if self.auto_ack:
            self._acks.append(
                OverrideAck(
                    sequence=sequence,
                    accepted=self.accept,
                    error_code=self.error_code,
                    message="" if self.accept else "bench rejection",
                )
            )
            if self.accept:
                self._values[variable] = float(value) + self.readback_offset
        return True

    def poll_ack(self) -> Optional[OverrideAck]:
        if not self._acks:
            return None
        return self._acks.pop(0)

    def readback(self, variable: str) -> Optional[float]:
        return self._values.get(variable)
