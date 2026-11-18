"""
Stato runtime Ollama condiviso tra llm_service e UI (thread-safe).
"""
from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OllamaRuntimeSnapshot:
    status: str = "idle"  # idle | waiting | running
    model: str = ""
    tokens_per_sec: Optional[float] = None
    jitter_ms: Optional[float] = None
    live_tokens_per_sec: Optional[float] = None
    ollama_reachable: bool = False
    loaded_in_vram: List[str] = field(default_factory=list)
    provider: str = "ollama"
    cloud_api_ok: bool = False
    last_latency_ms: Optional[float] = None
    warm_state: str = "cold"  # off | cold | warming | ready | skipped | failed
    warm_detail: str = ""


_lock = threading.Lock()
_snapshot = OllamaRuntimeSnapshot()
_pending_requests = 0
_active_requests = 0


def get_snapshot() -> OllamaRuntimeSnapshot:
    with _lock:
        return OllamaRuntimeSnapshot(
            status=_snapshot.status,
            model=_snapshot.model,
            tokens_per_sec=_snapshot.tokens_per_sec,
            jitter_ms=_snapshot.jitter_ms,
            live_tokens_per_sec=_snapshot.live_tokens_per_sec,
            ollama_reachable=_snapshot.ollama_reachable,
            loaded_in_vram=list(_snapshot.loaded_in_vram),
            provider=_snapshot.provider,
            cloud_api_ok=_snapshot.cloud_api_ok,
            last_latency_ms=_snapshot.last_latency_ms,
            warm_state=_snapshot.warm_state,
            warm_detail=_snapshot.warm_detail,
        )


def set_provider(provider: str) -> None:
    with _lock:
        _snapshot.provider = provider or "ollama"


def update_poll(*, reachable: bool, loaded_models: List[str]) -> None:
    with _lock:
        _snapshot.ollama_reachable = reachable
        _snapshot.loaded_in_vram = list(loaded_models)
        _recompute_status_locked()


def update_cloud_poll(*, reachable: bool, model: str = "") -> None:
    with _lock:
        _snapshot.cloud_api_ok = reachable
        if model:
            _snapshot.model = model
        _recompute_status_locked()


def record_cloud_inference(*, model: str, latency_ms: float, output_chars: int) -> None:
    """Aggiorna metriche dopo una risposta Gemini (stima tok/s da lunghezza testo)."""
    with _lock:
        _snapshot.provider = "gemini"
        _snapshot.model = model
        _snapshot.cloud_api_ok = True
        _snapshot.last_latency_ms = round(latency_ms, 1)
        est_tokens = max(1, output_chars // 4)
        if latency_ms > 0:
            _snapshot.tokens_per_sec = round(est_tokens / (latency_ms / 1000.0), 1)
        _recompute_status_locked()


def request_queued(model: str) -> None:
    global _pending_requests
    with _lock:
        _pending_requests += 1
        _snapshot.model = model or _snapshot.model
        _recompute_status_locked()


def request_dequeued() -> None:
    """Annulla un request_queued quando il thread ottiene lo slot."""
    global _pending_requests
    with _lock:
        _pending_requests = max(0, _pending_requests - 1)
        _recompute_status_locked()


def set_warm_state(state: str, detail: str = "") -> None:
    with _lock:
        _snapshot.warm_state = state or "cold"
        _snapshot.warm_detail = detail or ""


def reset_runtime_state() -> None:
    """Solo test / reset diagnostico."""
    global _pending_requests, _active_requests
    with _lock:
        _pending_requests = 0
        _active_requests = 0
        _snapshot.status = "idle"
        _snapshot.live_tokens_per_sec = None
        _snapshot.warm_state = "cold"
        _snapshot.warm_detail = ""


def request_started(model: str) -> "InferenceSession":
    global _pending_requests, _active_requests
    with _lock:
        if _pending_requests > 0:
            _pending_requests -= 1
        _active_requests += 1
        _snapshot.model = model
        _snapshot.live_tokens_per_sec = None
        _recompute_status_locked()
    return InferenceSession(model)


def request_finished(
    *,
    final_tokens_per_sec: Optional[float] = None,
    jitter_ms: Optional[float] = None,
) -> None:
    global _active_requests
    with _lock:
        _active_requests = max(0, _active_requests - 1)
        if final_tokens_per_sec is not None:
            _snapshot.tokens_per_sec = final_tokens_per_sec
        if jitter_ms is not None:
            _snapshot.jitter_ms = jitter_ms
        _snapshot.live_tokens_per_sec = None
        _recompute_status_locked()


class InferenceSession:
    """Traccia chunk streaming per tok/s live e jitter."""

    def __init__(self, model: str):
        self.model = model
        self._start = time.perf_counter()
        self._last_chunk_at: Optional[float] = None
        self._chunk_gaps_ms: List[float] = []
        self._content_chars = 0

    def on_chunk(self, content_delta: str, eval_count: Optional[int] = None) -> None:
        now = time.perf_counter()
        if self._last_chunk_at is not None:
            gap_ms = (now - self._last_chunk_at) * 1000.0
            if gap_ms >= 0:
                self._chunk_gaps_ms.append(gap_ms)
        self._last_chunk_at = now

        if content_delta:
            self._content_chars += len(content_delta)

        elapsed = max(now - self._start, 1e-6)
        tokens = eval_count if eval_count is not None else max(1, self._content_chars // 4)
        live_tps = tokens / elapsed

        with _lock:
            _snapshot.live_tokens_per_sec = round(live_tps, 1)

    def finish(self, eval_count: Optional[int], eval_duration_ns: Optional[int]) -> None:
        final_tps = None
        if eval_count and eval_duration_ns and eval_duration_ns > 0:
            final_tps = round((eval_count / eval_duration_ns) * 1e9, 1)

        jitter = None
        if len(self._chunk_gaps_ms) >= 2:
            jitter = round(statistics.pstdev(self._chunk_gaps_ms), 1)
        elif len(self._chunk_gaps_ms) == 1:
            jitter = round(self._chunk_gaps_ms[0], 1)

        request_finished(final_tokens_per_sec=final_tps, jitter_ms=jitter)


def _recompute_status_locked() -> None:
    if _active_requests > 0:
        _snapshot.status = "running"
    elif _pending_requests > 0:
        _snapshot.status = "waiting"
    else:
        _snapshot.status = "idle"
