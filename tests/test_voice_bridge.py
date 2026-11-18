"""Voice bridge lifecycle and HTTP health."""
from __future__ import annotations

import json
import urllib.request

from modules.voice_bridge.manager import (
    check_voice_bridge_health,
    start_voice_bridge,
    stop_voice_bridge,
)


def test_health_after_start():
    stop_voice_bridge()
    result = start_voice_bridge(force=True)
    assert result.started, result.message
    ok, detail = check_voice_bridge_health(result.host, result.port)
    assert ok, detail
    stop_voice_bridge()


def test_voice_turn_text_only():
    result = start_voice_bridge(force=True)
    assert result.started
    try:
        body = json.dumps(
            {
                "extension_key": "commercial",
                "text_in": "Test vocale",
                "source": "pytest",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"http://{result.host}:{result.port}/voice/turn",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload.get("text_in") == "Test vocale"
        assert "text_out" in payload
    finally:
        stop_voice_bridge()
