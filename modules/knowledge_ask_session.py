"""
Sessione Ask multi-turno per Retrieval Fabric (retrieval + LLM).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MAX_HISTORY_TURNS = 4
RETRIEVE_LIMIT = 3


def history_for_llm(completed_turns: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Ultimi N scambi completati, formato per LLMService.send_message."""
    pairs: List[Dict[str, str]] = []
    for turn in completed_turns:
        role = turn.get("role")
        text = str(turn.get("text") or "").strip()
        if role not in ("user", "assistant") or not text:
            continue
        pairs.append({"role": role, "text": text})
    max_messages = MAX_HISTORY_TURNS * 2
    if len(pairs) > max_messages:
        pairs = pairs[-max_messages:]
    return pairs


def build_user_prompt(question: str, context_block: str) -> str:
    """Prompt utente corrente con chunk knowledge freschi."""
    q = (question or "").strip()
    ctx = (context_block or "").strip()
    if ctx:
        return f"{ctx}\n\n[USER QUESTION]\n{q}"
    return q
