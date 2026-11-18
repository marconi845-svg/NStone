"""
Esecuzione azioni approvate (PLC, ecc.) con policy e audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.autonomy_policy import Action, ActionContext, get_policy
from core.machine_plc_config import get_machine
from modules.action_store import enqueue_pending_action, log_audit


@dataclass
class ExecutionResult:
    success: bool
    message: str
    plc_executed: bool
    action_id: Optional[int] = None


def build_plc_context(machine_id: str) -> ActionContext:
    cfg = get_machine(machine_id)
    return ActionContext(
        machine_id=machine_id,
        plc_mode=str(cfg.get("mode", "sim")),
        plc_ip=str(cfg.get("ip", "127.0.0.1")),
        agent_id="plant",
    )


def _resolve_updater(parent: Any, machine_id: str) -> Any:
    if parent is None:
        return None
    if machine_id == "multifilo" and hasattr(parent, "multifilo_updater"):
        return parent.multifilo_updater
    if machine_id == "lucidatrice" and hasattr(parent, "lucidatrice_updater"):
        return parent.lucidatrice_updater
    return None


def _execute_plc_command(updater: Any, action_type: str) -> tuple[bool, str]:
    if updater is None:
        return False, "PLC non collegato (apri Gestione macchina con connessione attiva)."

    action_key = (action_type or "").strip().lower()
    if action_key in ("start", "avvia", "run"):
        if hasattr(updater, "send_start"):
            ok = updater.send_start()
            return ok, "Comando Start inviato al PLC." if ok else "Invio Start fallito."
    if action_key in ("stop", "ferma", "hold", "idle"):
        if hasattr(updater, "send_stop"):
            ok = updater.send_stop()
            return ok, "Comando Stop inviato al PLC." if ok else "Invio Stop fallito."
    if action_key in ("reset", "reset_allarme", "reset_alarm"):
        if hasattr(updater, "send_reset"):
            ok = updater.send_reset()
            return ok, "Comando Reset inviato al PLC." if ok else "Invio Reset fallito."
    if action_key in ("set_parameter", "optimize", "set_param"):
        return (
            False,
            "Modifica parametro: registrata in coda; scrittura DB parametri in sviluppo.",
        )
    return False, f"Azione PLC non mappata: {action_type}"


def process_operator_approval(
    machine_id: str,
    suggestion: Dict[str, Any],
    parent_window: Any = None,
) -> ExecutionResult:
    """
    Dopo approvazione operatore: audit, coda, eventuale write PLC se policy consente.
    """
    policy = get_policy()
    level = policy.effective_level()
    ctx = build_plc_context(machine_id)
    ctx.human_approved = True

    log_audit(
        Action.QUEUE_FOR_APPROVAL.value,
        True,
        "Approvazione operatore",
        level=level,
        agent="operator",
        payload=suggestion,
    )

    queue_ok = policy.allow(Action.QUEUE_FOR_APPROVAL, ctx)
    if not queue_ok.allowed:
        log_audit(Action.QUEUE_FOR_APPROVAL.value, False, queue_ok.reason, level=level)
        return ExecutionResult(False, queue_ok.reason, False)

    plc_result = policy.allow(Action.PLC_WRITE, ctx)
    log_audit(
        Action.PLC_WRITE.value,
        plc_result.allowed,
        plc_result.reason,
        level=level,
        payload={"action": suggestion.get("action")},
    )

    messages = [f"Policy L{level}: suggerimento registrato."]
    plc_executed = False

    if plc_result.allowed:
        updater = _resolve_updater(parent_window, machine_id)
        ok, msg = _execute_plc_command(updater, str(suggestion.get("action", "")))
        plc_executed = ok
        messages.append(msg)
    else:
        messages.append(f"PLC: {plc_result.reason}")

    action_id = enqueue_pending_action(
        machine_id,
        suggestion,
        policy_level=level,
        status="approved",
        result_message=" | ".join(messages),
    )

    return ExecutionResult(
        success=True,
        message="\n".join(messages),
        plc_executed=plc_executed,
        action_id=action_id,
    )
