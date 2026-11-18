"""Test llm_service (Ollama mock, config)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from llm.llm_service import (
    DEFAULT_LLM_CONFIG,
    LLMService,
    load_llm_config,
    llm_settings_from_ui_model,
    merge_llm_settings_from_ui,
)


def test_default_provider_is_ollama(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("llm.llm_service.PROJECT_ROOT", tmp_path)
    cfg = load_llm_config()
    assert cfg["provider"] == "ollama"
    assert cfg["ollama"]["model"] == DEFAULT_LLM_CONFIG["ollama"]["model"]


def test_ui_model_maps_to_ollama():
    llm = llm_settings_from_ui_model("Qwen 2.5 14B (Ollama locale)")
    assert llm["provider"] == "ollama"
    assert "qwen2.5" in llm["ollama"]["model"]


def test_merge_llm_settings_preserves_inference_and_contexts():
    existing = {
        "provider": "ollama",
        "inference": {"max_concurrent": 1, "max_queue": 3},
        "prewarm": {"enabled": "auto", "delay_seconds": 45},
        "ollama": {"model": "nstone-marmo:latest", "base_url": "http://127.0.0.1:11434"},
    }
    contexts = {
        "offerte": {"temperature": 0.55, "num_ctx": 4096, "num_predict": 600},
        "ordini": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 400},
        "produzione": {"temperature": 0.25, "num_ctx": 8192, "num_predict": 800},
    }
    merged = merge_llm_settings_from_ui(
        "Qwen 2.5 14B (local Ollama)",
        contexts=contexts,
        prewarm_enabled=False,
        existing_llm=existing,
    )
    assert merged["inference"]["max_queue"] == 3
    assert merged["contexts"]["produzione"]["num_ctx"] == 8192
    assert merged["prewarm"]["enabled"] is False
    assert merged["prewarm"]["delay_seconds"] == 45
    assert "qwen2.5" in merged["ollama"]["model"]


def test_ollama_send_message_parses_response():
    lines = [
        json.dumps({"message": {"role": "assistant", "content": "Risposta test"}, "done": False}),
        json.dumps(
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "eval_count": 5,
                "eval_duration": 100_000_000,
            }
        ),
    ]
    stream_body = "\n".join(lines).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.__iter__ = lambda s: iter(stream_body.splitlines(keepends=True))
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    cfg = {
        "provider": "ollama",
        "ollama": {
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen2.5:14b-instruct-q4_0",
            "timeout_seconds": 30,
        },
    }
    service = LLMService(cfg)

    with patch.object(service, "_ollama_is_available", return_value=True):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            text = service.send_message("Ciao")

    assert text == "Risposta test"


def test_not_configured_returns_error_message():
    cfg = {"provider": "ollama", "ollama": DEFAULT_LLM_CONFIG["ollama"].copy()}
    service = LLMService(cfg)
    with patch.object(service, "_ollama_is_available", return_value=False):
        msg = service.send_message("Test")
    assert msg.startswith("Errore:")
    assert "Ollama" in msg
