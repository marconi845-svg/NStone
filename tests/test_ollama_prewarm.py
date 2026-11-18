"""Test policy pre-warm Ollama."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from modules.ollama_prewarm import (
    _model_loaded,
    request_lazy_prewarm,
    reset_prewarm_session,
    should_prewarm,
)
from llm.ollama_runtime import get_snapshot, reset_runtime_state, set_warm_state


@pytest.fixture(autouse=True)
def _clean():
    reset_runtime_state()
    reset_prewarm_session()
    yield
    reset_prewarm_session()
    reset_runtime_state()


def test_should_prewarm_off_without_nvidia():
    cfg = {"provider": "ollama", "prewarm": {"enabled": "auto"}}
    with patch("core.host_hardware.detect_nvidia_gpu_info", return_value={"available": False}):
        ok, reason = should_prewarm(cfg)
    assert ok is False
    assert "NVIDIA" in reason


def test_should_prewarm_on_rtx_4050():
    cfg = {"provider": "ollama", "prewarm": {"enabled": "auto", "min_vram_gb": 4}}
    gpu = {"available": True, "name": "NVIDIA GeForce RTX 4050 Laptop GPU", "vram_gb": 6.0}
    with patch("core.host_hardware.detect_nvidia_gpu_info", return_value=gpu):
        ok, reason = should_prewarm(cfg)
    assert ok is True
    assert "4050" in reason


def test_should_prewarm_off_integrated_name():
    cfg = {"provider": "ollama", "prewarm": {"enabled": "auto"}}
    gpu = {"available": True, "name": "Intel Iris Xe Graphics", "vram_gb": 2.0}
    with patch("core.host_hardware.detect_nvidia_gpu_info", return_value=gpu):
        ok, reason = should_prewarm(cfg)
    assert ok is False


def test_should_prewarm_cloud_provider():
    ok, reason = should_prewarm({"provider": "gemini"})
    assert ok is False
    assert "cloud" in reason


def test_model_loaded_matches_base_name():
    payload = json.dumps({"models": [{"name": "nstone-marmo:latest"}]}).encode()

    class _Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    with patch("urllib.request.urlopen", return_value=_Resp()):
        assert _model_loaded("http://127.0.0.1:11434", "nstone-marmo:latest") is True


def test_request_lazy_sets_off_when_disabled():
    cfg = {"provider": "ollama", "prewarm": {"enabled": False}}
    with patch("modules.ollama_prewarm.load_llm_config", return_value=cfg):
        request_lazy_prewarm(reason="test")
    snap = get_snapshot()
    assert snap.warm_state == "off"


def test_section_uses_ollama_machine_windows():
    from modules.ollama_prewarm import section_uses_ollama

    class GestioneMultifiloWindow:
        pass

    class OnlineStockWindow:
        pass

    assert section_uses_ollama(GestioneMultifiloWindow()) is True
    assert section_uses_ollama(OnlineStockWindow()) is False


def test_production_agent_prewarm_reason(monkeypatch):
    from modules import ollama_prewarm

    calls = []

    def _capture(**kwargs):
        calls.append(kwargs.get("reason"))

    monkeypatch.setattr(ollama_prewarm, "request_lazy_prewarm", _capture)
    ollama_prewarm.request_production_agent_prewarm("cnc")
    assert calls == ["production_agent_cnc"]


def test_request_lazy_starts_warm_thread(monkeypatch):
    cfg = {"provider": "ollama", "prewarm": {"enabled": True}}
    monkeypatch.setattr("modules.ollama_prewarm.load_llm_config", lambda: cfg)
    monkeypatch.setattr("modules.ollama_prewarm.should_prewarm", lambda _cfg=None: (True, "test gpu"))
    monkeypatch.setattr("modules.ollama_prewarm._model_loaded", lambda *_a: False)
    monkeypatch.setattr("modules.ollama_prewarm._inference_idle", lambda: True)

    called = {}

    def _fake_run(reason, attempt):
        called["reason"] = reason
        set_warm_state("ready", "mock")

    monkeypatch.setattr("modules.ollama_prewarm._run_prewarm", _fake_run)
    request_lazy_prewarm(reason="unit")
    import time

    time.sleep(0.3)
    assert called.get("reason") == "unit"
    assert get_snapshot().warm_state == "ready"
