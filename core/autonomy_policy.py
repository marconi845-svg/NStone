"""
Policy runtime: autonomia e tattiche commerciali (fonte unica per guard nel codice).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.agents_config import (
    CommandCenterSettings,
    effective_autonomy_level,
    effective_commercial_tone,
    load_command_center_settings,
)


class Action(Enum):
    SUGGEST = "suggest"
    QUEUE_FOR_APPROVAL = "queue"
    SEND_CLIENT_EMAIL = "send_client_email"
    UPDATE_ORDER_AUTO = "update_order_auto"
    PLC_WRITE = "plc_write"
    RUN_AGENT_LOOP = "run_agent_loop"


@dataclass
class ActionContext:
    machine_id: str = ""
    plc_mode: str = "sim"
    plc_ip: str = "127.0.0.1"
    agent_id: str = ""
    human_approved: bool = False


@dataclass
class PolicyResult:
    allowed: bool
    reason: str


class AutonomyPolicy:
    def __init__(self, settings: Optional[CommandCenterSettings] = None) -> None:
        self._settings = settings or load_command_center_settings()

    def reload(self) -> None:
        self._settings = load_command_center_settings()

    @property
    def settings(self) -> CommandCenterSettings:
        return self._settings

    def effective_level(self) -> int:
        return effective_autonomy_level(self._settings["autonomy"])

    def effective_commercial_tone(self) -> int:
        return effective_commercial_tone(self._settings["commercial"])

    def banner_text(self) -> str:
        level = self.effective_level()
        if self._settings["autonomy"].get("agents_paused"):
            return "Agents paused — kill switch active"
        if level >= 3:
            return f"LAB MODE L{level} — simulation / bench only"
        if level == 2:
            return f"Autonomy L{level} — assisted office"
        if level == 1:
            return f"Autonomy L{level} — mandatory approval"
        return f"Autonomy L{level} — suggestions only"

    def allow(self, action: Action, ctx: Optional[ActionContext] = None) -> PolicyResult:
        ctx = ctx or ActionContext()
        auto = self._settings["autonomy"]
        comm = self._settings["commercial"]
        agents = self._settings["agents"]
        level = self.effective_level()

        if auto.get("agents_paused") and action in (
            Action.PLC_WRITE,
            Action.SEND_CLIENT_EMAIL,
            Action.UPDATE_ORDER_AUTO,
            Action.RUN_AGENT_LOOP,
        ):
            return PolicyResult(False, "Kill switch: agents paused")

        if action == Action.SUGGEST:
            return PolicyResult(True, "Always allowed")

        if action == Action.QUEUE_FOR_APPROVAL:
            if ctx.human_approved:
                return PolicyResult(True, "Recorded with operator approval")
            return PolicyResult(level >= 1, "Requires autonomy level ≥ 1")

        if action == Action.RUN_AGENT_LOOP:
            if level < 1:
                return PolicyResult(False, "Agent runtime requires level ≥ 1")
            if not agents.get("enabled"):
                return PolicyResult(False, "No agents enabled")
            return PolicyResult(True, "Agent runtime allowed")

        if action == Action.SEND_CLIENT_EMAIL:
            if level < 2:
                return PolicyResult(False, "Auto email sending requires level ≥ 2")
            if not auto.get("office_auto_email"):
                return PolicyResult(False, "office_auto_email disabled")
            if self.effective_commercial_tone() >= 3 and level < 2:
                return PolicyResult(False, "Assertive tone requires dedicated policy")
            return PolicyResult(True, "Automatic email sending allowed")

        if action == Action.UPDATE_ORDER_AUTO:
            if level < 2:
                return PolicyResult(False, "Auto order updates require level ≥ 2")
            return PolicyResult(True, "Order updates allowed")

        if action == Action.PLC_WRITE:
            if level < 1:
                return PolicyResult(False, "PLC write requires level ≥ 1")
            if level < 3 and not auto.get("plant_auto_plc_write"):
                if not ctx.human_approved:
                    return PolicyResult(
                        False,
                        "PLC write only after operator approval (L≥1)",
                    )
            if level >= 3 and auto.get("plant_sim_only"):
                if ctx.plc_mode != "sim" and ctx.plc_ip not in (
                    "127.0.0.1",
                    "localhost",
                ):
                    return PolicyResult(False, "L3+: write only in sim / localhost")
            return PolicyResult(True, "PLC write allowed by policy")

        return PolicyResult(False, "Unclassified action")


_policy: Optional[AutonomyPolicy] = None


def get_policy() -> AutonomyPolicy:
    global _policy
    if _policy is None:
        _policy = AutonomyPolicy()
    return _policy


def reload_policy() -> AutonomyPolicy:
    global _policy
    _policy = AutonomyPolicy()
    return _policy
