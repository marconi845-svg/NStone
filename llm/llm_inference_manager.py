"""
Coda inferenze LLM: max 1 attiva, max N in attesa, abort stream, unload VRAM.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Callable, Optional


class InferenceQueueFullError(Exception):
    """Coda inferenze piena."""


class LLMInferenceManager:
    """Serializza le chiamate Ollama e permette abort/unload."""

    def __init__(self, max_concurrent: int = 1, max_queue: int = 3):
        self.max_concurrent = max(1, int(max_concurrent))
        self.max_queue = max(0, int(max_queue))
        self._cond = threading.Condition()
        self._active = 0
        self._waiting = 0
        self._abort = threading.Event()
        self._http_resp = None
        self._http_lock = threading.Lock()

    def queue_stats(self) -> dict:
        with self._cond:
            return {
                "active": self._active,
                "waiting": self._waiting,
                "max_queue": self.max_queue,
            }

    def is_abort_requested(self) -> bool:
        return self._abort.is_set()

    def abort_current(self) -> bool:
        """Interrompe lo stream HTTP in corso (se presente)."""
        self._abort.set()
        with self._http_lock:
            resp = self._http_resp
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
            return True
        return self._abort.is_set()

    def _register_response(self, resp) -> None:
        with self._http_lock:
            self._http_resp = resp

    def _clear_response(self) -> None:
        with self._http_lock:
            self._http_resp = None

    def run(self, fn: Callable[[], str], *, model: str) -> str:
        from llm.ollama_runtime import request_dequeued, request_queued

        was_waiting = False
        with self._cond:
            while self._active >= self.max_concurrent:
                if self._waiting >= self.max_queue:
                    raise InferenceQueueFullError(
                        f"Coda inferenze piena (max {self.max_queue} in attesa). "
                        "Usa «Ferma risposta» o attendi."
                    )
                self._waiting += 1
                was_waiting = True
                request_queued(model)
                self._cond.wait()
                self._waiting -= 1
            self._active += 1

        if was_waiting:
            request_dequeued()

        self._abort.clear()
        try:
            return fn()
        finally:
            self._clear_response()
            with self._cond:
                self._active = max(0, self._active - 1)
                self._cond.notify_all()

    def unload_models(self, base_url: str, models: list[str]) -> list[str]:
        """Scarica modelli dalla VRAM (keep_alive=0)."""
        base = base_url.rstrip("/")
        unloaded: list[str] = []
        seen = set()
        for model in models:
            name = (model or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                payload = json.dumps(
                    {"model": name, "messages": [], "keep_alive": 0},
                    ensure_ascii=False,
                ).encode("utf-8")
                req = urllib.request.Request(
                    f"{base}/api/chat",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp.read()
                unloaded.append(name)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
                print(f"Unload modello {name} fallito: {exc}")
        return unloaded


_manager: Optional[LLMInferenceManager] = None


def get_inference_manager() -> LLMInferenceManager:
    global _manager
    from llm.llm_service import load_llm_config

    cfg = load_llm_config()
    inf = cfg.get("inference") if isinstance(cfg.get("inference"), dict) else {}
    max_concurrent = int(inf.get("max_concurrent", 1))
    max_queue = int(inf.get("max_queue", 3))
    if _manager is None:
        _manager = LLMInferenceManager(max_concurrent, max_queue)
    else:
        _manager.max_concurrent = max_concurrent
        _manager.max_queue = max_queue
    return _manager


def reset_inference_manager() -> None:
    global _manager
    _manager = None
