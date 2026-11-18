"""Standalone voice bridge for Agentic Calling (not FastAPI backend)."""
from modules.voice_bridge.manager import (
    check_voice_bridge_health,
    is_voice_bridge_running,
    start_voice_bridge,
    stop_voice_bridge,
)

__all__ = [
    "check_voice_bridge_health",
    "is_voice_bridge_running",
    "start_voice_bridge",
    "stop_voice_bridge",
]
