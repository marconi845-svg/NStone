"""Test stato runtime Ollama."""
import pytest

from llm.ollama_runtime import (
    InferenceSession,
    get_snapshot,
    request_finished,
    request_queued,
    request_started,
    reset_runtime_state,
    update_poll,
)


@pytest.fixture(autouse=True)
def _clean_runtime():
    reset_runtime_state()
    yield
    reset_runtime_state()


def test_status_waiting_then_running():
    request_queued("qwen2.5:14b-instruct-q4_0")
    snap = get_snapshot()
    assert snap.status == "waiting"

    request_started("qwen2.5:14b-instruct-q4_0")
    snap = get_snapshot()
    assert snap.status == "running"

    request_finished(final_tokens_per_sec=42.0, jitter_ms=12.5)
    snap = get_snapshot()
    assert snap.status == "idle"
    assert snap.tokens_per_sec == 42.0
    assert snap.jitter_ms == 12.5


def test_inference_session_jitter():
    session = InferenceSession("test-model")
    session.on_chunk("a", None)
    session.on_chunk("b", None)
    session.on_chunk("c", None)
    session.finish(eval_count=10, eval_duration_ns=100_000_000)
    snap = get_snapshot()
    assert snap.tokens_per_sec == 100.0
    assert snap.jitter_ms is not None


def test_update_poll():
    update_poll(reachable=True, loaded_models=["qwen2.5:14b-instruct-q4_0"])
    snap = get_snapshot()
    assert snap.ollama_reachable is True
    assert "qwen2.5" in snap.loaded_in_vram[0]
