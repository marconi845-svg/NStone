"""Tests sessione Ask Retrieval Fabric."""
from modules.knowledge_ask_session import (
    MAX_HISTORY_TURNS,
    build_user_prompt,
    history_for_llm,
)


def test_build_user_prompt_with_context():
    prompt = build_user_prompt("Prezzo?", "[KNOWLEDGE BASE CONTEXT]\nfoo")
    assert "[KNOWLEDGE BASE CONTEXT]" in prompt
    assert "[USER QUESTION]" in prompt
    assert prompt.endswith("Prezzo?")


def test_build_user_prompt_without_context():
    assert build_user_prompt("Solo domanda", "") == "Solo domanda"


def test_history_for_llm_trims_old_turns():
    turns = []
    for i in range(MAX_HISTORY_TURNS + 2):
        turns.append({"role": "user", "text": f"q{i}"})
        turns.append({"role": "assistant", "text": f"a{i}"})
    hist = history_for_llm(turns)
    assert len(hist) == MAX_HISTORY_TURNS * 2
    assert hist[0]["text"] == f"q{2}"
    assert hist[-1]["text"] == f"a{MAX_HISTORY_TURNS + 1}"


def test_history_for_llm_skips_streaming_empty():
    turns = [
        {"role": "user", "text": "ok"},
        {"role": "assistant", "text": "", "_streaming": True},
    ]
    hist = history_for_llm(turns)
    assert hist == [{"role": "user", "text": "ok"}]
