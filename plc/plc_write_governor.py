"""
Canale di scrittura PLC deterministico (governor).

Il modello NON scrive mai sul PLC: propone al massimo un "intent" JSON.
Ogni scrittura — da modello o operatore — passa da qui e viene valutata
SOLO con regole Python deterministiche, nell'ordine:

  1. mappa non placeholder            (mappa da commissioning = zero scritture)
  2. variabile in whitelist           (writable=true nella mappa DB)
  3. tipo valore valido               (numerico finito / bool coerente col tipo S7)
  4. range min/max                    (nessun clamp: fuori range = rifiuto)
  5. step massimo                     (delta rispetto a un riferimento noto)
  6. cooldown                         (tempo minimo tra scritture accettate)
  7. stato macchina disponibile       (senza status live non si scrive)
  8. nessuna emergenza                (PlcWriteGuard + stato ERROR)
  9. stato macchina ammesso           (allowed_states della variabile)
 10. autonomy policy                  (Action.PLC_WRITE, approvazione operatore)

Fail-closed ovunque: qualsiasi dubbio = rifiuto con motivo esplicito.
Default SHADOW MODE: la decisione viene calcolata e loggata in audit,
ma nessun byte parte verso il PLC finché shadow=False esplicito.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.autonomy_policy import Action, ActionContext, AutonomyPolicy, get_policy
from plc.plc_db_write import PlcWriteGuard, write_variable

VALID_URGENCIES = ("low", "normal", "high")
INTENT_ACTIONS = ("write", "none")
_INTENT_WRITE_KEYS = ("action", "variable", "value", "reason")
_INTENT_OPTIONAL_KEYS = ("urgency",)


# ---------------------------------------------------------------------------
# Whitelist dalla mappa DB
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WritableVar:
    """Variabile scrivibile come dichiarata nella mappa DB (whitelist)."""

    name: str
    db_number: int
    offset: int
    var_type: str
    unit: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    max_step: Optional[float] = None
    min_delta: Optional[float] = None
    cooldown_s: float = 0.0
    allowed_states: Tuple[str, ...] = ()
    step_reference: str = ""
    comment: str = ""


def load_writable_variables(profile_id: str, machine_id: str = "") -> List[WritableVar]:
    """
    Estrae dalla mappa le sole variabili con writable=true (tutti i DB).

    Se Pydantic (governance_schemas) è disponibile, ogni variabile viene
    validata nella forma: vincoli incoerenti (min>max, min_delta>max_step,
    tipo non scrivibile, blocco non sw_to_plc, offset duplicato) la
    ESCLUDONO dalla whitelist — fail-closed, mai crash all'avvio.
    """
    from plc.plc_map_loader import load_map_document

    try:
        from core.governance_schemas import validate_writable_variable
    except ImportError:
        validate_writable_variable = None

    doc = load_map_document(profile_id)
    out: List[WritableVar] = []
    seen_offsets: set = set()
    for block in doc.get("data_blocks") or []:
        if not isinstance(block, dict):
            continue
        db_number = int(block.get("number", 0))
        direction = str(block.get("direction", "plc_to_sw"))
        for var in block.get("variables") or []:
            if not isinstance(var, dict) or not var.get("writable"):
                continue
            var_name = str(var.get("name", "?"))
            if validate_writable_variable is not None:
                errors = validate_writable_variable(var, block_direction=direction)
                if errors:
                    print(
                        f"⛔ Whitelist scrittura: '{var_name}' (DB{db_number}) "
                        f"esclusa (fail-closed): {errors[0]}"
                    )
                    continue
            key = (db_number, int(var.get("offset", 0)))
            if key in seen_offsets:
                print(
                    f"⛔ Whitelist scrittura: '{var_name}' esclusa: offset "
                    f"{key[1]} duplicato in DB{db_number}"
                )
                continue
            seen_offsets.add(key)
            states = var.get("allowed_states") or []
            out.append(
                WritableVar(
                    name=str(var.get("name", "")),
                    db_number=db_number,
                    offset=int(var.get("offset", 0)),
                    var_type=str(var.get("type", "")).upper(),
                    unit=str(var.get("unit") or ""),
                    min_value=_opt_float(var.get("min")),
                    max_value=_opt_float(var.get("max")),
                    max_step=_opt_float(var.get("max_step")),
                    min_delta=_opt_float(var.get("min_delta")),
                    cooldown_s=float(var.get("cooldown_s") or 0.0),
                    allowed_states=tuple(str(s).upper() for s in states),
                    step_reference=str(var.get("step_reference") or ""),
                    comment=str(var.get("comment_it") or var.get("comment") or ""),
                )
            )
    return out


def map_is_placeholder(profile_id: str) -> bool:
    from plc.plc_map_loader import load_map_document

    try:
        return bool(load_map_document(profile_id).get("placeholder"))
    except (OSError, ValueError):
        return True  # mappa illeggibile = fail-closed


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


# ---------------------------------------------------------------------------
# Richiesta / decisione
# ---------------------------------------------------------------------------

@dataclass
class WriteRequest:
    machine_id: str
    variable: str
    value: Any
    reason: str = ""
    source: str = "model"  # "model" | "operator"
    urgency: str = "normal"


@dataclass
class CheckOutcome:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class WriteDecision:
    allowed: bool
    reason: str
    checks: List[CheckOutcome] = field(default_factory=list)
    request: Optional[WriteRequest] = None
    shadow: bool = True
    executed: bool = False
    execute_message: str = ""

    def failed_checks(self) -> List[CheckOutcome]:
        return [c for c in self.checks if not c.passed]

    def to_payload(self) -> Dict[str, Any]:
        req = self.request
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "shadow": self.shadow,
            "executed": self.executed,
            "execute_message": self.execute_message,
            "request": {
                "machine_id": req.machine_id if req else "",
                "variable": req.variable if req else "",
                "value": req.value if req else None,
                "reason": req.reason if req else "",
                "source": req.source if req else "",
                "urgency": req.urgency if req else "",
            },
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Governor
# ---------------------------------------------------------------------------

class WriteGovernor:
    """
    Valuta ed (eventualmente) esegue scritture PLC secondo la whitelist.

    shadow=True (default): evaluate+audit ma NESSUNA scrittura reale.
    Il flag va abbassato esplicitamente e consapevolmente in commissioning.
    """

    def __init__(
        self,
        machine_id: str,
        *,
        profile_id: str = "",
        variables: Optional[List[WritableVar]] = None,
        placeholder: Optional[bool] = None,
        policy: Optional[AutonomyPolicy] = None,
        shadow: bool = True,
        clock: Callable[[], float] = time.monotonic,
        audit_fn: Optional[Callable[[WriteDecision], None]] = None,
    ) -> None:
        self.machine_id = machine_id
        self.profile_id = profile_id
        self.shadow = bool(shadow)
        self._policy = policy
        self._clock = clock
        self._audit_fn = audit_fn
        if variables is not None:
            self._vars = {v.name: v for v in variables}
            self._placeholder = bool(placeholder) if placeholder is not None else False
        else:
            if not profile_id:
                raise ValueError("Serve profile_id oppure variables espliciti")
            self._vars = {
                v.name: v for v in load_writable_variables(profile_id, machine_id)
            }
            self._placeholder = (
                bool(placeholder)
                if placeholder is not None
                else map_is_placeholder(profile_id)
            )
        # Stato interno deterministico per step/cooldown.
        self._last_write_value: Dict[str, float] = {}
        self._last_write_ts: Dict[str, float] = {}

    # -- introspezione ------------------------------------------------------

    def whitelist(self) -> List[WritableVar]:
        return list(self._vars.values())

    def record_protocol_verified(self, variable: str, value: Any) -> None:
        """
        Registra step/cooldown SOLO dopo che un protocollo esterno ha ricevuto
        ACK e verificato il read-back. Non esegue alcuna scrittura.

        Usato da plc_override_protocol; una variabile fuori whitelist viene
        rifiutata per evitare che lo stato interno venga contaminato.
        """
        var = self._vars.get(variable)
        if var is None:
            raise ValueError(f"Variabile '{variable}' non in whitelist")
        self._record_accepted(var, value)

    # -- valutazione --------------------------------------------------------

    def evaluate(
        self,
        request: WriteRequest,
        *,
        current_status: Any = None,
        human_approved: bool = False,
        plc_mode: str = "live",
        plc_ip: str = "",
    ) -> WriteDecision:
        checks: List[CheckOutcome] = []

        def add(name: str, passed: bool, detail: str = "") -> bool:
            checks.append(CheckOutcome(name, passed, detail))
            return passed

        # 1. mappa placeholder
        add(
            "map_not_placeholder",
            not self._placeholder,
            "" if not self._placeholder
            else "Mappa placeholder: nessuna scrittura prima del commissioning",
        )

        # 2. whitelist
        var = self._vars.get(request.variable)
        add(
            "variable_whitelisted",
            var is not None,
            "" if var is not None
            else f"Variabile '{request.variable}' non in whitelist scrittura",
        )

        state, raw_values, status_available = _extract_status(current_status)

        if var is not None:
            # 3. tipo valore
            type_ok, type_detail = _value_type_ok(var.var_type, request.value)
            add("value_type", type_ok, type_detail)

            if type_ok:
                numeric = float(request.value) if not isinstance(request.value, bool) else float(bool(request.value))

                # 4. range
                range_ok = True
                detail = ""
                if var.min_value is not None and numeric < var.min_value:
                    range_ok, detail = False, (
                        f"{numeric} < min {var.min_value} {var.unit}".strip()
                    )
                if var.max_value is not None and numeric > var.max_value:
                    range_ok, detail = False, (
                        f"{numeric} > max {var.max_value} {var.unit}".strip()
                    )
                add("range", range_ok, detail)

                # 5. step massimo
                if var.max_step is not None:
                    reference = self._step_reference_value(var, raw_values)
                    if reference is None:
                        add(
                            "max_step",
                            False,
                            "Nessun riferimento per il controllo step "
                            "(né lettura live né scrittura precedente)",
                        )
                    else:
                        delta = abs(numeric - reference)
                        add(
                            "max_step",
                            delta <= var.max_step,
                            "" if delta <= var.max_step
                            else f"Delta {delta:.3f} > max_step {var.max_step} "
                                 f"(riferimento {reference})",
                        )
                else:
                    add("max_step", True, "Nessun limite step definito")

                # 5b. no-op / delta minimo: una scrittura che non cambia
                # (abbastanza) il valore è inutile e viene rifiutata.
                reference = self._step_reference_value(var, raw_values)
                if reference is None:
                    add(
                        "no_op",
                        True,
                        "Riferimento non disponibile: delta non verificabile "
                        "(se richiesto, ci pensa max_step)",
                    )
                else:
                    delta = abs(numeric - reference)
                    if var.min_delta is not None:
                        add(
                            "no_op",
                            delta >= var.min_delta,
                            "" if delta >= var.min_delta
                            else f"Delta {delta:.3f} < min_delta {var.min_delta} "
                                 f"(riferimento {reference}): variazione insignificante",
                        )
                    else:
                        add(
                            "no_op",
                            delta > 0,
                            "" if delta > 0
                            else f"Scrittura no-op: valore identico al "
                                 f"riferimento ({reference})",
                        )

            # 6. cooldown
            if var.cooldown_s > 0:
                last_ts = self._last_write_ts.get(var.name)
                if last_ts is None:
                    add("cooldown", True, "Nessuna scrittura precedente")
                else:
                    elapsed = self._clock() - last_ts
                    add(
                        "cooldown",
                        elapsed >= var.cooldown_s,
                        "" if elapsed >= var.cooldown_s
                        else f"Cooldown attivo: {elapsed:.1f}s / {var.cooldown_s}s",
                    )
            else:
                add("cooldown", True, "Nessun cooldown definito")

        # 7. stato macchina disponibile
        add(
            "live_status_available",
            status_available,
            "" if status_available
            else "Status macchina non disponibile: impossibile verificare "
                 "emergenza e stato (fail-closed)",
        )

        if status_available:
            # 8. emergenza
            emergency = PlcWriteGuard.emergency_active(raw_values) or state == "ERROR"
            add(
                "no_emergency",
                not emergency,
                "" if not emergency
                else f"Emergenza/allarme attivo (stato={state})",
            )

            # 9. stati ammessi
            if var is not None and var.allowed_states:
                state_ok = state in var.allowed_states
                add(
                    "machine_state_allowed",
                    state_ok,
                    "" if state_ok
                    else f"Stato '{state}' non in {list(var.allowed_states)}",
                )

        # 10. autonomy policy
        policy = self._policy or get_policy()
        ctx = ActionContext(
            machine_id=request.machine_id,
            plc_mode=plc_mode,
            plc_ip=plc_ip,
            human_approved=human_approved,
        )
        result = policy.allow(Action.PLC_WRITE, ctx)
        add("autonomy_policy", result.allowed, result.reason)

        failed = [c for c in checks if not c.passed]
        allowed = not failed
        reason = "Tutti i controlli superati" if allowed else (
            f"{failed[0].name}: {failed[0].detail}"
        )
        return WriteDecision(
            allowed=allowed,
            reason=reason,
            checks=checks,
            request=request,
            shadow=self.shadow,
        )

    # -- esecuzione ---------------------------------------------------------

    def execute(
        self,
        request: WriteRequest,
        plc_client: Any = None,
        *,
        current_status: Any = None,
        human_approved: bool = False,
        plc_mode: str = "live",
        plc_ip: str = "",
    ) -> WriteDecision:
        decision = self.evaluate(
            request,
            current_status=current_status,
            human_approved=human_approved,
            plc_mode=plc_mode,
            plc_ip=plc_ip,
        )

        if decision.allowed:
            var = self._vars[request.variable]
            if self.shadow:
                decision.execute_message = (
                    "SHADOW MODE: scrittura approvata ma NON eseguita"
                )
                # Anche in shadow aggiorna step/cooldown: il comportamento
                # osservato in shadow deve essere identico a quello reale.
                self._record_accepted(var, request.value)
            elif plc_client is None:
                decision.allowed = False
                decision.reason = "Nessun client PLC disponibile"
                decision.execute_message = decision.reason
            else:
                ok, msg, _old, _new = write_variable(
                    plc_client,
                    var.db_number,
                    var.offset,
                    var.var_type,
                    request.value,
                    name=var.name,
                )
                decision.executed = ok
                decision.execute_message = msg
                if ok:
                    self._record_accepted(var, request.value)
        else:
            decision.execute_message = f"Rifiutata: {decision.reason}"

        self._audit(decision)
        return decision

    # -- interni ------------------------------------------------------------

    def _step_reference_value(
        self, var: WritableVar, raw_values: Dict[str, Any]
    ) -> Optional[float]:
        if var.step_reference:
            ref = raw_values.get(var.step_reference)
            if isinstance(ref, (int, float)) and not isinstance(ref, bool):
                return float(ref)
        last = self._last_write_value.get(var.name)
        if last is not None:
            return last
        return None

    def _record_accepted(self, var: WritableVar, value: Any) -> None:
        try:
            self._last_write_value[var.name] = float(value)
        except (TypeError, ValueError):
            pass
        self._last_write_ts[var.name] = self._clock()

    def _audit(self, decision: WriteDecision) -> None:
        if self._audit_fn is not None:
            self._audit_fn(decision)
            return
        try:
            from modules.action_store import log_audit

            req = decision.request
            log_audit(
                "plc_write",
                decision.allowed,
                decision.reason,
                agent=req.source if req else "",
                payload=decision.to_payload(),
            )
        except Exception:
            # L'audit non deve mai bloccare né mascherare la decisione,
            # che resta comunque disponibile al chiamante.
            pass


def _extract_status(status: Any) -> Tuple[str, Dict[str, Any], bool]:
    """Normalizza lo status (CNCLiveStatus, dict o None) in (stato, raw, ok)."""
    if status is None:
        return "UNKNOWN", {}, False
    if isinstance(status, dict):
        state = status.get("machine_state", "UNKNOWN")
        raw = status.get("raw_values") or {}
    else:
        state = getattr(status, "machine_state", "UNKNOWN")
        raw = getattr(status, "raw_values", None) or {}
    state_str = str(getattr(state, "value", state)).upper()
    if state_str in ("", "UNKNOWN"):
        return "UNKNOWN", dict(raw), False
    return state_str, dict(raw), True


def _value_type_ok(var_type: str, value: Any) -> Tuple[bool, str]:
    t = var_type.upper()
    if t == "BOOL":
        if isinstance(value, bool):
            return True, ""
        return False, f"Atteso BOOL, ricevuto {type(value).__name__}"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, f"Atteso numero per {t}, ricevuto {type(value).__name__}"
    if not math.isfinite(float(value)):
        return False, "Valore non finito (nan/inf)"
    if t in ("INT", "BYTE") and float(value) != int(value):
        return False, f"Atteso intero per {t}, ricevuto {value}"
    if t == "BYTE" and not 0 <= int(value) <= 255:
        return False, f"BYTE fuori range 0-255: {value}"
    return True, ""


# ---------------------------------------------------------------------------
# Fase 2 — intent del modello (parsing rigido, il modello NON tocca il PLC)
# ---------------------------------------------------------------------------

def parse_model_intent(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Estrae e valida l'intent JSON proposto dal modello.

    Schema accettato (nient'altro):
      {"action": "none"}
      {"action": "write", "variable": "...", "value": <num|bool>,
       "reason": "...", "urgency": "low|normal|high"?}

    Ritorna (intent, "") se valido, (None, motivo) altrimenti.
    Qualsiasi deviazione dallo schema = rifiuto (il chiamante NON deve
    'interpretare' output ambigui del modello).

    Validazione primaria: Pydantic (governance_schemas, tipi strict).
    Fallback: validazione manuale equivalente se Pydantic non è installato.
    """
    if not text or not text.strip():
        return None, "Testo vuoto"

    obj = _extract_first_json_object(text)
    if obj is None:
        return None, "Nessun oggetto JSON valido nel testo"

    try:
        from core.governance_schemas import validate_intent_dict
    except ImportError:
        return _validate_intent_manual(obj)
    return validate_intent_dict(obj)


def _validate_intent_manual(
    obj: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Fallback senza Pydantic: stessa semantica di validate_intent_dict."""
    action = obj.get("action")
    if action not in INTENT_ACTIONS:
        return None, f"'action' deve essere uno di {list(INTENT_ACTIONS)}"

    if action == "none":
        extra = set(obj) - {"action", "reason"}
        if extra:
            return None, f"Chiavi non ammesse per action=none: {sorted(extra)}"
        return {"action": "none", "reason": str(obj.get("reason", ""))}, ""

    allowed_keys = set(_INTENT_WRITE_KEYS) | set(_INTENT_OPTIONAL_KEYS)
    extra = set(obj) - allowed_keys
    if extra:
        return None, f"Chiavi non ammesse: {sorted(extra)}"
    for key in _INTENT_WRITE_KEYS:
        if key not in obj:
            return None, f"Chiave obbligatoria mancante: '{key}'"

    variable = obj["variable"]
    if not isinstance(variable, str) or not variable.strip():
        return None, "'variable' deve essere una stringa non vuota"

    value = obj["value"]
    if isinstance(value, str) or not isinstance(value, (int, float, bool)):
        return None, "'value' deve essere numerico o booleano (non stringa)"

    reason = obj["reason"]
    if not isinstance(reason, str) or not reason.strip():
        return None, "'reason' deve spiegare il motivo della scrittura"

    urgency = obj.get("urgency", "normal")
    if urgency not in VALID_URGENCIES:
        return None, f"'urgency' deve essere uno di {list(VALID_URGENCIES)}"

    return {
        "action": "write",
        "variable": variable.strip(),
        "value": value,
        "reason": reason.strip(),
        "urgency": urgency,
    }, ""


def intent_to_request(
    intent: Dict[str, Any], machine_id: str, *, source: str = "model"
) -> WriteRequest:
    return WriteRequest(
        machine_id=machine_id,
        variable=str(intent.get("variable", "")),
        value=intent.get("value"),
        reason=str(intent.get("reason", "")),
        source=source,
        urgency=str(intent.get("urgency", "normal")),
    )


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Primo oggetto JSON bilanciato nel testo (tollera ```json ... ```)."""
    cleaned = text.replace("```json", "```").replace("```", "")
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
        start = cleaned.find("{", start + 1)
    return None


# ---------------------------------------------------------------------------
# Prompt per il modello (whitelist esplicita, output SOLO JSON)
# ---------------------------------------------------------------------------

def describe_whitelist_for_prompt(variables: List[WritableVar]) -> str:
    if not variables:
        return "(nessuna variabile scrivibile disponibile)"
    lines = []
    for v in variables:
        parts = [f"- {v.name} ({v.var_type}"]
        if v.unit:
            parts.append(f", {v.unit}")
        parts.append(")")
        if v.min_value is not None or v.max_value is not None:
            parts.append(f" range [{v.min_value}..{v.max_value}]")
        if v.max_step is not None:
            parts.append(f", step max {v.max_step}")
        if v.min_delta is not None:
            parts.append(f", variazione minima {v.min_delta}")
        if v.cooldown_s:
            parts.append(f", cooldown {v.cooldown_s:.0f}s")
        if v.allowed_states:
            parts.append(f", stati ammessi {list(v.allowed_states)}")
        lines.append("".join(parts))
    return "\n".join(lines)


def build_write_intent_prompt(
    machine_context: str, goal: str, variables: List[WritableVar]
) -> str:
    whitelist = describe_whitelist_for_prompt(variables)
    return f"""You are the PLC advisor for an industrial CNC. You can only PROPOSE a parameter change; a deterministic validator decides. You NEVER write to the PLC directly.

WRITABLE VARIABLES (whitelist — anything else will be rejected):
{whitelist}

MACHINE STATUS:
{machine_context}

GOAL: {goal}

RULES:
- Respond with ONE JSON object only. No prose, no markdown, no explanations outside JSON.
- If a change helps: {{"action": "write", "variable": "<name from whitelist>", "value": <number>, "reason": "<short factual reason based ONLY on the status above>", "urgency": "low|normal|high"}}
- If no change is needed or data is insufficient: {{"action": "none", "reason": "<why>"}}
- Never invent values outside the declared ranges. Never propose variables not in the whitelist.
- Never propose a value equal (or nearly equal) to the current one: a no-op write will be rejected.
- If the status does not justify a change, choose action "none". When in doubt: "none"."""
