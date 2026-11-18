"""
Pre-warm Ollama in background — lazy, non blocca GUI né coda inferenze attive.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from llm.llm_service import DEFAULT_LLM_CONFIG, load_llm_config
from llm.ollama_runtime import set_warm_state

# Sezioni hub che usano Ollama (locale o via gemini_service → LLMService)
OLLAMA_SECTION_CLASSES = frozenset(
    {
        "GestioneMultifiloWindow",
        "GestioneLucidatriceWindow",
        "GestioneCNCWindow",
        "GestioneFanghiWindow",
        "WasteManagementWindow",
        "QuotationsWindow",
        "QuotationsHubWindow",
        "RetrievalFabricWindow",
        "AgentsCommandCenterWindow",
        "OrdersWindow",
        "AgenticCallingWindow",
        "RAGEngineWindow",
        "SuggerimentiMultifiloWindow",
        "SuggerimentiCNCWindow",
        "SuggerimentiLucidatriceWindow",
    }
)

PRODUCTION_AGENT_MACHINES = frozenset(
    {"multifilo", "lucidatrice", "cnc", "fanghi", "waste"}
)

_lock = threading.Lock()
_warm_thread: Optional[threading.Thread] = None
_session_ready = False
_cancel = threading.Event()
_idle_timer: Optional[threading.Timer] = None
_retry_timer: Optional[threading.Timer] = None


def section_uses_ollama(window: object) -> bool:
    """True se la finestra/sezione usa inferenza LLM locale."""
    if window is None:
        return False
    if getattr(type(window), "_ollama_section", False):
        return True
    return type(window).__name__ in OLLAMA_SECTION_CLASSES


def prewarm_for_section(window: object) -> None:
    """Pre-warm quando una sezione Ollama viene mostrata."""
    if not section_uses_ollama(window):
        return
    request_lazy_prewarm(reason=type(window).__name__)


def request_production_agent_prewarm(machine: str) -> None:
    """Pre-warm prima di Agent Analysis (multifilo, CNC, lucidatrice, …)."""
    key = (machine or "").strip().lower()
    if key not in PRODUCTION_AGENT_MACHINES:
        key = "production_agent"
    request_lazy_prewarm(reason=f"production_agent_{key}")


def _prewarm_cfg(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_llm_config()
    block = cfg.get("prewarm") if isinstance(cfg.get("prewarm"), dict) else {}
    defaults = {
        "enabled": "auto",
        "delay_seconds": 45,
        "keep_alive": "10m",
        "min_vram_gb": 4,
        "retry_seconds": 20,
        "max_retries": 3,
    }
    return {**defaults, **block}


def should_prewarm(cfg: Optional[Dict[str, Any]] = None) -> tuple[bool, str]:
    """Ritorna (abilitato, motivo)."""
    cfg = cfg or load_llm_config()
    if cfg.get("provider", "ollama") != "ollama":
        return False, "cloud provider"

    pre = _prewarm_cfg(cfg)
    enabled = pre.get("enabled", "auto")
    if enabled is False or str(enabled).lower() == "false":
        return False, "disabled in config"

    if enabled is True or str(enabled).lower() == "true":
        return True, "forced on"

    from core.host_hardware import detect_nvidia_gpu_info

    gpu = detect_nvidia_gpu_info()
    if not gpu.get("available"):
        return False, "no dedicated NVIDIA GPU"

    name = str(gpu.get("name") or "").lower()
    if any(k in name for k in ("intel", "iris", "uhd graphics")):
        return False, "integrated GPU profile"

    min_vram = float(pre.get("min_vram_gb", 4))
    vram = gpu.get("vram_gb")
    if vram is not None and float(vram) < min_vram:
        return False, f"VRAM {vram} GB < min {min_vram} GB"

    if vram is not None:
        return True, f"NVIDIA {gpu.get('name')} · {vram} GB"
    return True, f"NVIDIA {gpu.get('name')}"


def _ollama_base_and_model(cfg: Dict[str, Any]) -> tuple[str, str]:
    ollama = cfg.get("ollama") or {}
    base = str(
        ollama.get("base_url", DEFAULT_LLM_CONFIG["ollama"]["base_url"])
    ).rstrip("/")
    model = str(ollama.get("model", DEFAULT_LLM_CONFIG["ollama"]["model"]))
    return base, model


def _model_loaded(base_url: str, model: str) -> bool:
    try:
        req = urllib.request.Request(f"{base_url}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [
            str(item.get("name") or "")
            for item in (data.get("models") or [])
            if isinstance(item, dict)
        ]
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return False

    base = model.split(":")[0]
    for name in names:
        if not name:
            continue
        if name == model or name.startswith(f"{model}:") or name.split(":")[0] == base:
            return True
    return False


def _inference_idle() -> bool:
    try:
        from llm.llm_inference_manager import get_inference_manager

        q = get_inference_manager().queue_stats()
        return int(q.get("active") or 0) == 0 and int(q.get("waiting") or 0) == 0
    except Exception:
        return True


def _run_prewarm(reason: str, attempt: int = 0) -> None:
    global _session_ready

    if _cancel.is_set():
        return

    cfg = load_llm_config()
    ok, why = should_prewarm(cfg)
    if not ok:
        set_warm_state("off", why)
        return

    base, model = _ollama_base_and_model(cfg)
    pre = _prewarm_cfg(cfg)

    if _model_loaded(base, model):
        _session_ready = True
        set_warm_state("ready", "model loaded")
        return

    if not _inference_idle():
        max_retries = int(pre.get("max_retries", 3))
        if attempt < max_retries and not _cancel.is_set():
            set_warm_state("cold", "waiting for idle inference queue")
            delay = float(pre.get("retry_seconds", 20))
            _schedule_retry(reason, attempt + 1, delay)
        return

    set_warm_state("warming", f"loading {model.split(':')[0]}…")
    keep_alive = str(pre.get("keep_alive", "10m"))
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "keep_alive": keep_alive,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{base}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        if not _cancel.is_set():
            set_warm_state("failed", str(exc)[:120])
        return

    if _cancel.is_set():
        return

    if _model_loaded(base, model):
        _session_ready = True
        set_warm_state("ready", f"warm ({reason})")
    else:
        set_warm_state("ready", "model ping sent")


def _warm_worker(reason: str, attempt: int) -> None:
    global _warm_thread
    try:
        _run_prewarm(reason, attempt)
    finally:
        with _lock:
            _warm_thread = None


def _schedule_retry(reason: str, attempt: int, delay: float) -> None:
    global _retry_timer

    def _fire() -> None:
        request_lazy_prewarm(reason=reason, attempt=attempt)

    with _lock:
        if _retry_timer is not None:
            _retry_timer.cancel()
        _retry_timer = threading.Timer(max(1.0, delay), _fire)
        _retry_timer.daemon = True
        _retry_timer.start()


def request_lazy_prewarm(*, reason: str = "lazy", attempt: int = 0) -> None:
    """Avvia pre-warm in background se abilitato e non già pronto."""
    global _warm_thread, _session_ready

    if _cancel.is_set():
        return

    cfg = load_llm_config()
    ok, why = should_prewarm(cfg)
    if not ok:
        set_warm_state("off", why)
        return

    if _session_ready:
        base, model = _ollama_base_and_model(cfg)
        if _model_loaded(base, model):
            set_warm_state("ready", "model loaded")
            return
        _session_ready = False

    with _lock:
        if _warm_thread is not None and _warm_thread.is_alive():
            return
        _warm_thread = threading.Thread(
            target=_warm_worker,
            args=(reason, attempt),
            name="ollama-prewarm",
            daemon=True,
        )
        _warm_thread.start()


def schedule_idle_prewarm(delay_seconds: Optional[float] = None) -> None:
    """Pre-warm ritardato dopo avvio hub (non blocca GUI)."""
    global _idle_timer

    cfg = load_llm_config()
    pre = _prewarm_cfg(cfg)
    delay = float(delay_seconds if delay_seconds is not None else pre.get("delay_seconds", 45))

    def _fire() -> None:
        request_lazy_prewarm(reason="idle")

    with _lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
        _idle_timer = threading.Timer(max(5.0, delay), _fire)
        _idle_timer.daemon = True
        _idle_timer.start()


def cancel_prewarm() -> None:
    """Annulla timer/thread di pre-warm (chiusura app)."""
    global _idle_timer, _retry_timer, _warm_thread

    _cancel.set()
    with _lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None
        if _retry_timer is not None:
            _retry_timer.cancel()
            _retry_timer = None
    if _warm_thread is not None and _warm_thread.is_alive():
        _warm_thread.join(timeout=0.5)


def reset_prewarm_session() -> None:
    """Solo test."""
    global _session_ready, _warm_thread, _idle_timer, _retry_timer
    cancel_prewarm()
    _cancel.clear()
    _session_ready = False
    with _lock:
        _warm_thread = None
        _idle_timer = None
        _retry_timer = None
