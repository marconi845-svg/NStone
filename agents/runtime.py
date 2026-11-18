"""
Runtime agenti ufficio ↔ produzione: bus SQLite, tick orchestrato, policy L≥1.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from PyQt5.QtCore import QObject, QTimer

from core.agents_config import load_command_center_settings
from core.autonomy_policy import Action, ActionContext, get_policy
from core.machine_plc_config import get_machine
from modules.action_store import (
    list_agent_messages,
    log_audit,
    mark_agent_message_done,
    post_agent_message,
)

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MS = 8000


def _machine_snapshot(machine_id: str) -> Dict[str, Any]:
    cfg = get_machine(machine_id)
    return {
        "machine_id": machine_id,
        "mode": cfg.get("mode", "sim"),
        "ip": cfg.get("ip", "127.0.0.1"),
        "map_profile": cfg.get("map_profile", ""),
    }


def _parent_machine_connected(parent: Any, machine_id: str) -> bool:
    if parent is None:
        return False
    updater = None
    if machine_id == "multifilo" and hasattr(parent, "multifilo_updater"):
        updater = parent.multifilo_updater
    elif machine_id == "lucidatrice" and hasattr(parent, "lucidatrice_updater"):
        updater = parent.lucidatrice_updater
    if updater is None:
        return False
    return bool(getattr(updater, "connected", False) or getattr(updater, "is_connected", False))


class AgentRuntime(QObject):
    """Orchestratore leggero: scambia messaggi office/plant sul bus SQLite."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._main_window: Any = None
        self._round_counts: Dict[str, int] = {}

    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self, main_window: Any = None, interval_ms: int = DEFAULT_INTERVAL_MS) -> Tuple[bool, str]:
        policy = get_policy()
        level = policy.effective_level()
        ctx = ActionContext(agent_id="runtime")
        gate = policy.allow(Action.RUN_AGENT_LOOP, ctx)
        log_audit(
            Action.RUN_AGENT_LOOP.value,
            gate.allowed,
            gate.reason,
            level=level,
            agent="runtime",
        )
        if not gate.allowed:
            return False, gate.reason

        settings = load_command_center_settings()
        if settings["autonomy"].get("agents_paused"):
            return False, "Kill switch: agents paused"

        self._main_window = main_window
        self._timer.start(max(3000, interval_ms))
        post_agent_message(
            from_agent="runtime",
            to_agent="office",
            msg_type="runtime_started",
            payload={"level": level},
            correlation_id=str(uuid.uuid4()),
        )
        logger.info("Agent runtime avviato (L%s)", level)
        return True, "Agent runtime started"

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            log_audit(
                Action.RUN_AGENT_LOOP.value,
                True,
                "Runtime arrestato",
                level=get_policy().effective_level(),
                agent="runtime",
            )
            post_agent_message(
                from_agent="runtime",
                to_agent="office",
                msg_type="runtime_stopped",
                payload={},
                correlation_id=str(uuid.uuid4()),
            )

    def tick_once(self) -> None:
        self._on_tick()

    def _on_tick(self) -> None:
        policy = get_policy()
        if not policy.allow(Action.RUN_AGENT_LOOP, ActionContext(agent_id="runtime")).allowed:
            self.stop()
            return

        settings = load_command_center_settings()
        if settings["autonomy"].get("agents_paused"):
            self.stop()
            return

        agents = settings["agents"]
        max_rounds = agents.get("max_rounds_per_case", 5)

        if agents.get("office_enabled"):
            self._office_pass(settings, max_rounds)
        if agents.get("plant_enabled"):
            self._plant_pass(settings, max_rounds)

    def _office_pass(self, settings: Dict[str, Any], max_rounds: int) -> None:
        msgs = list_agent_messages(to_agent="office", status="new", limit=5)
        for msg in msgs:
            cid = msg.get("correlation_id") or ""
            rounds = self._round_counts.get(cid, 0)
            if rounds >= max_rounds:
                mark_agent_message_done(int(msg["id"]))
                continue
            if msg.get("msg_type") == "plant_status":
                mark_agent_message_done(int(msg["id"]))
                continue
            mark_agent_message_done(int(msg["id"]))

        machines = []
        ag = settings.get("agents") or settings
        if ag.get("plant_watch_multifilo"):
            machines.append("multifilo")
        if ag.get("plant_watch_lucidatrice"):
            machines.append("lucidatrice")

        for mid in machines:
            cid = f"office-watch-{mid}"
            if self._round_counts.get(cid, 0) >= max_rounds:
                continue
            post_agent_message(
                from_agent="office",
                to_agent="plant",
                msg_type="watch_request",
                correlation_id=cid,
                round_no=self._round_counts.get(cid, 0),
                payload={"machine_id": mid, "reason": "periodic_watch"},
            )
            self._round_counts[cid] = self._round_counts.get(cid, 0) + 1

    def _plant_pass(self, settings: Dict[str, Any], max_rounds: int) -> None:
        ag = settings.get("agents") or settings
        inbox = list_agent_messages(to_agent="plant", status="new", limit=10)
        for msg in inbox:
            cid = msg.get("correlation_id") or ""
            if self._round_counts.get(f"plant-{cid}", 0) >= max_rounds:
                mark_agent_message_done(int(msg["id"]))
                continue

            payload = {}
            try:
                import json

                raw = msg.get("payload_json") or "{}"
                payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                payload = {}

            mid = str(payload.get("machine_id") or "multifilo")
            if mid == "cnc" and not ag.get("plant_watch_cnc"):
                mark_agent_message_done(int(msg["id"]))
                continue
            if mid == "multifilo" and not ag.get("plant_watch_multifilo"):
                mark_agent_message_done(int(msg["id"]))
                continue
            if mid == "lucidatrice" and not ag.get("plant_watch_lucidatrice"):
                mark_agent_message_done(int(msg["id"]))
                continue

            snap = _machine_snapshot(mid)
            snap["plc_connected"] = _parent_machine_connected(self._main_window, mid)

            post_agent_message(
                from_agent="plant",
                to_agent="office",
                msg_type="plant_status",
                correlation_id=cid or str(uuid.uuid4()),
                round_no=int(msg.get("round_no") or 0) + 1,
                payload=snap,
            )
            mark_agent_message_done(int(msg["id"]))
            self._round_counts[f"plant-{cid}"] = self._round_counts.get(f"plant-{cid}", 0) + 1


_runtime: Optional[AgentRuntime] = None


def get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


def start_runtime(main_window: Any = None, interval_ms: int = DEFAULT_INTERVAL_MS) -> Tuple[bool, str]:
    return get_runtime().start(main_window, interval_ms)


def stop_runtime() -> None:
    get_runtime().stop()


def is_runtime_running() -> bool:
    return get_runtime().is_running()


def tick_once() -> None:
    get_runtime().tick_once()
