"""
Contratti Pydantic per il canale di scrittura governato (confini del sistema).

Tre confini validati:
  1. Intent del modello (JSON LLM → WriteIntent / NoActionIntent):
     tipi STRICT, chiavi extra vietate, enum chiusi.
  2. Whitelist della mappa DB (variabili writable=true):
     vincoli coerenti (min<=max, min_delta<=max_step, tipo supportato,
     solo in blocchi sw_to_plc). Variabile incoerente = esclusa (fail-closed).
  3. Payload audit (WriteDecision.to_payload): struttura garantita per la
     Governance Console.

Pydantic valida la FORMA dei dati. Le decisioni di merito (range, step,
cooldown, stato macchina, emergenza, policy) restano nel plc_write_governor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

# Tipi S7 per cui esiste un encoder in plc_db_write (scrittura possibile).
PLC_WRITABLE_TYPES = ("BOOL", "BYTE", "INT", "REAL")


# ---------------------------------------------------------------------------
# 1. Intent del modello
# ---------------------------------------------------------------------------

class NoActionIntent(BaseModel):
    """Il modello dichiara che non serve alcuna scrittura."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["none"]
    reason: str = ""


class WriteIntent(BaseModel):
    """
    Proposta di scrittura del modello. STRICT: "95" (stringa) non è 95,
    True non è 1, chiavi sconosciute = rifiuto.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["write"]
    variable: str
    value: Union[StrictBool, StrictInt, StrictFloat]
    reason: str
    urgency: Literal["low", "normal", "high"] = "normal"

    @field_validator("variable")
    @classmethod
    def variable_non_vuota(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("'variable' deve essere una stringa non vuota")
        return v.strip()

    @field_validator("reason")
    @classmethod
    def reason_non_vuota(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("'reason' deve spiegare il motivo della scrittura")
        return v.strip()


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "__root__")
        msg = err.get("msg", "valore non valido")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "Intent non valido"


def validate_intent_dict(obj: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Valida un oggetto intent già estratto dal testo del modello.
    Ritorna (intent normalizzato, "") oppure (None, motivo).
    Stesso contratto di plc_write_governor.parse_model_intent.
    """
    if not isinstance(obj, dict):
        return None, "L'intent deve essere un oggetto JSON"

    action = obj.get("action")
    if action == "none":
        model_cls = NoActionIntent
    elif action == "write":
        model_cls = WriteIntent
    else:
        return None, "'action' deve essere uno di ['write', 'none']"

    try:
        model = model_cls.model_validate(obj)
    except ValidationError as exc:
        return None, _format_validation_error(exc)
    return model.model_dump(), ""


# ---------------------------------------------------------------------------
# 2. Whitelist della mappa DB (solo variabili writable=true)
# ---------------------------------------------------------------------------

class WritableVariableSpec(BaseModel):
    """
    Vincoli di forma per una variabile dichiarata scrivibile nella mappa.
    extra="allow": le mappe portano campi propri (comment_it, role, unit…).
    """

    model_config = ConfigDict(extra="allow")

    offset: int = Field(ge=0)
    type: str
    name: str
    min: Optional[float] = None
    max: Optional[float] = None
    max_step: Optional[float] = Field(default=None, gt=0)
    min_delta: Optional[float] = Field(default=None, ge=0)
    cooldown_s: float = Field(default=0.0, ge=0)
    allowed_states: List[str] = Field(default_factory=list)
    step_reference: str = ""

    @field_validator("name")
    @classmethod
    def name_non_vuoto(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("nome variabile vuoto")
        return v

    @field_validator("type")
    @classmethod
    def tipo_scrivibile(cls, v: str) -> str:
        t = str(v).upper()
        if t not in PLC_WRITABLE_TYPES:
            raise ValueError(
                f"tipo '{v}' non supportato in scrittura "
                f"(ammessi: {list(PLC_WRITABLE_TYPES)})"
            )
        return t

    @model_validator(mode="after")
    def vincoli_coerenti(self) -> "WritableVariableSpec":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) > max ({self.max})")
        if (
            self.min_delta is not None
            and self.max_step is not None
            and self.min_delta > self.max_step
        ):
            raise ValueError(
                f"min_delta ({self.min_delta}) > max_step ({self.max_step}): "
                "nessuna scrittura potrebbe mai passare"
            )
        return self


def validate_writable_variable(
    var: Dict[str, Any], *, block_direction: str = "sw_to_plc"
) -> List[str]:
    """
    Errori di forma per una variabile writable=true. Lista vuota = valida.
    Il chiamante (load_writable_variables) esclude le variabili con errori.
    """
    errors: List[str] = []
    if str(block_direction) != "sw_to_plc":
        errors.append(
            f"variabile scrivibile in blocco '{block_direction}': "
            "la scrittura è ammessa solo in blocchi sw_to_plc"
        )
    try:
        WritableVariableSpec.model_validate(var)
    except ValidationError as exc:
        errors.append(_format_validation_error(exc))
    return errors


def build_map_contract_report(profile_id: str) -> Dict[str, Any]:
    """
    Report sola lettura sulla salute del contratto di una mappa PLC.

    Conta le variabili writable valide/escluse usando le stesse regole del
    governor e riporta errori comprensibili dalla Governance Console.
    Una mappa placeholder può essere strutturalmente valida, ma resta
    esplicitamente non commissionata e quindi non abilita scritture.
    """
    from plc.plc_map_loader import load_map_document

    report: Dict[str, Any] = {
        "profile_id": profile_id,
        "schema": "",
        "version": "",
        "title": "",
        "placeholder": True,
        "writable_total": 0,
        "writable_valid": 0,
        "writable_excluded": 0,
        "override_protocol": {},
        "errors": [],
        "valid": False,
    }
    try:
        doc = load_map_document(profile_id)
    except Exception as exc:
        report["errors"].append(
            {
                "db": None,
                "variable": "",
                "message": f"Mappa non leggibile: {exc}",
            }
        )
        return report

    report.update(
        {
            "schema": str(doc.get("schema") or ""),
            "version": str(doc.get("version") or ""),
            "title": str(doc.get("title") or profile_id),
            "placeholder": bool(doc.get("placeholder")),
            "override_protocol": dict(doc.get("override_protocol") or {}),
        }
    )

    seen_offsets = set()
    for block in doc.get("data_blocks") or []:
        if not isinstance(block, dict):
            report["errors"].append(
                {"db": None, "variable": "", "message": "Data block non valido"}
            )
            continue
        try:
            db_number = int(block.get("number", 0))
        except (TypeError, ValueError):
            report["errors"].append(
                {
                    "db": None,
                    "variable": "",
                    "message": f"Numero DB non valido: {block.get('number')!r}",
                }
            )
            continue
        direction = str(block.get("direction", "plc_to_sw"))
        for var in block.get("variables") or []:
            if not isinstance(var, dict) or not var.get("writable"):
                continue
            report["writable_total"] += 1
            name = str(var.get("name") or "?")
            errors = validate_writable_variable(var, block_direction=direction)

            try:
                key = (db_number, int(var.get("offset", 0)))
            except (TypeError, ValueError):
                key = None
            if key is not None and key in seen_offsets:
                errors.append(f"offset {key[1]} duplicato in DB{db_number}")

            if errors:
                report["writable_excluded"] += 1
                for message in errors:
                    report["errors"].append(
                        {
                            "db": db_number,
                            "variable": name,
                            "message": message,
                        }
                    )
                continue

            if key is not None:
                seen_offsets.add(key)
            report["writable_valid"] += 1

    report["valid"] = not report["errors"]
    return report


# ---------------------------------------------------------------------------
# 3. Payload audit (contratto con la Governance Console)
# ---------------------------------------------------------------------------

class CheckOutcomePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    detail: str = ""


class WriteRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine_id: str
    variable: str
    value: Any = None
    reason: str = ""
    source: str = ""
    urgency: str = ""


class WriteDecisionPayload(BaseModel):
    """Struttura garantita di WriteDecision.to_payload() nell'audit."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str
    shadow: bool
    executed: bool
    execute_message: str = ""
    request: WriteRequestPayload
    checks: List[CheckOutcomePayload] = Field(default_factory=list)
