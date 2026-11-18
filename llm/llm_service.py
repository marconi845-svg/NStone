"""
Servizio LLM unificato: Ollama locale (default) o Google Gemini cloud.
"""
from __future__ import annotations

import json
import os
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

try:
    from llm.llm_contexts import (
        BusinessContext,
        get_ollama_options,
        get_system_instruction,
        resolve_llm_language,
    )
except ImportError:
    BusinessContext = str  # type: ignore[misc, assignment]
    get_system_instruction = None  # type: ignore[assignment]
    get_ollama_options = None  # type: ignore[assignment]
    resolve_llm_language = None  # type: ignore[assignment]

try:
    from core.machine_plc_config import load_config as load_app_config
except ImportError:
    load_app_config = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RequestKind = Literal["operational", "production"]

DEFAULT_LLM_CONFIG: Dict[str, Any] = {
    "provider": "ollama",
    "inference": {
        "max_concurrent": 1,
        "max_queue": 3,
    },
    "prewarm": {
        "enabled": "auto",
        "delay_seconds": 45,
        "keep_alive": "10m",
        "min_vram_gb": 4,
        "retry_seconds": 20,
        "max_retries": 3,
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5:14b-instruct-q4_0",
        "timeout_seconds": 180,
        "keep_alive_operational": "2m",
        "keep_alive_production": "5m",
    },
    "gemini": {
        "model": "gemini-1.5-flash",
    },
    "contexts": {
        "offerte": {"temperature": 0.55, "num_ctx": 4096, "num_predict": 600},
        "ordini": {"temperature": 0.25, "num_ctx": 4096, "num_predict": 400},
        "produzione": {"temperature": 0.30, "num_ctx": 4096, "num_predict": 800},
    },
}

_MODEL_LABEL_TO_LLM: Dict[str, Dict[str, str]] = {
    "NStone Marmo (Ollama locale)": {
        "provider": "ollama",
        "model": "nstone-marmo:latest",
    },
    "Qwen 2.5 14B (Ollama locale)": {
        "provider": "ollama",
        "model": "qwen2.5:14b-instruct-q4_0",
    },
    "Qwen 2.5 14B (local Ollama)": {
        "provider": "ollama",
        "model": "qwen2.5:14b-instruct-q4_0",
    },
    "Gemini 2.5 Flash": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "Gemini 2.0 Pro": {"provider": "gemini", "model": "gemini-2.0-pro"},
    "Gemini 1.5 Pro": {"provider": "gemini", "model": "gemini-1.5-pro"},
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_llm_config() -> Dict[str, Any]:
    """Carica sezione llm da config.json con default per fork locale."""
    data: Dict[str, Any] = {}
    config_path = PROJECT_ROOT / "config.json"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data = raw
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Errore lettura config.json per LLM: {exc}")

    llm_section = data.get("llm") if isinstance(data.get("llm"), dict) else {}
    cfg = _deep_merge(DEFAULT_LLM_CONFIG, llm_section)

    provider = (
        os.getenv("LLM_PROVIDER")
        or cfg.get("provider")
        or DEFAULT_LLM_CONFIG["provider"]
    )
    cfg["provider"] = str(provider).strip().lower()

    if cfg["provider"] == "gemini" and not (data.get("api_key") or "").strip():
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key:
            cfg["_api_key"] = api_key
    elif (data.get("api_key") or "").strip():
        cfg["_api_key"] = str(data.get("api_key")).strip()

    return cfg


def llm_settings_from_ui_model(model_label: str) -> Dict[str, Any]:
    """Mappa etichetta combo Impostazioni → sezione llm per config.json."""
    mapping = _MODEL_LABEL_TO_LLM.get(model_label)
    if not mapping:
        return {"provider": "ollama", "ollama": {"model": DEFAULT_LLM_CONFIG["ollama"]["model"]}}
    provider = mapping["provider"]
    if provider == "ollama":
        return {
            "provider": "ollama",
            "ollama": {"model": mapping["model"]},
        }
    return {
        "provider": "gemini",
        "gemini": {"model": mapping["model"]},
    }


def merge_llm_settings_from_ui(
    model_label: str,
    *,
    contexts: Dict[str, Dict[str, Any]],
    prewarm_enabled: Any,
    existing_llm: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Unisce provider/modello, profili per contesto e pre-warm nel blocco llm."""
    base = dict(existing_llm) if isinstance(existing_llm, dict) else {}
    patch = llm_settings_from_ui_model(model_label)
    if isinstance(contexts, dict) and contexts:
        patch["contexts"] = contexts
    prewarm_base = base.get("prewarm") if isinstance(base.get("prewarm"), dict) else {}
    patch["prewarm"] = _deep_merge(prewarm_base, {"enabled": prewarm_enabled})
    return _deep_merge(base, patch)


def ui_model_label_from_config(cfg: Optional[Dict[str, Any]] = None) -> str:
    cfg = cfg or load_llm_config()
    provider = cfg.get("provider", "ollama")
    if provider == "ollama":
        model = (cfg.get("ollama") or {}).get("model", "")
        if "qwen2.5" in model:
            return "Qwen 2.5 14B (local Ollama)"
        return "Qwen 2.5 14B (local Ollama)"
    gemini_model = (cfg.get("gemini") or {}).get("model", "")
    for label, spec in _MODEL_LABEL_TO_LLM.items():
        if spec.get("provider") == "gemini" and spec.get("model") in gemini_model:
            return label
    return "Gemini 2.5 Flash"


def abort_llm_inference() -> bool:
    from llm.llm_inference_manager import get_inference_manager

    return get_inference_manager().abort_current()


def unload_ollama_models() -> tuple[list[str], str]:
    """Scarica modelli Ollama dalla VRAM. Ritorna (modelli, messaggio)."""
    cfg = load_llm_config()
    if cfg.get("provider") != "ollama":
        return [], "Provider non Ollama."
    ollama_cfg = cfg.get("ollama") or {}
    base_url = str(ollama_cfg.get("base_url", DEFAULT_LLM_CONFIG["ollama"]["base_url"]))
    primary = str(ollama_cfg.get("model", DEFAULT_LLM_CONFIG["ollama"]["model"]))
    models = [primary]
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("models") or []:
            if isinstance(item, dict) and item.get("name"):
                models.append(str(item["name"]))
    except Exception:
        pass
    from llm.llm_inference_manager import get_inference_manager

    unloaded = get_inference_manager().unload_models(base_url, models)
    if unloaded:
        return unloaded, f"Scaricati dalla VRAM: {', '.join(unloaded)}"
    return [], "Nessun modello scaricato (Ollama non raggiungibile o già libero)."


class LLMService:
    """Invio prompt testuali via Ollama o Gemini."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or load_llm_config()
        self.provider = self._config.get("provider", "ollama")
        try:
            from llm.ollama_runtime import set_provider

            set_provider(self.provider)
        except ImportError:
            pass

    def is_configured(self) -> bool:
        if self.provider == "ollama":
            return self._ollama_is_available()
        if self.provider == "gemini":
            return bool(self._gemini_api_key())
        return False

    def configuration_error_message(self) -> str:
        if self.provider == "ollama":
            ollama = self._config.get("ollama") or {}
            model = ollama.get("model", DEFAULT_LLM_CONFIG["ollama"]["model"])
            base = ollama.get("base_url", DEFAULT_LLM_CONFIG["ollama"]["base_url"])
            reachable, model_ok = self._probe_ollama()
            if not reachable:
                return (
                    f"Ollama non è in esecuzione su {base}. "
                    "Apri l'app Ollama dalla barra delle applicazioni (icona llama) "
                    "oppure esegui in PowerShell: ollama list"
                )
            if not model_ok:
                return (
                    f"Modello '{model}' non trovato in Ollama. "
                    f"Esegui: ollama pull {model}"
                )
            return f"Ollama non disponibile su {base}."
        return (
            "API Key Gemini non configurata. Inserisci la chiave in Impostazioni "
            "oppure imposta GEMINI_API_KEY."
        )

    def send_message(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        system_instruction: str = "",
        fast: bool = False,
        request_kind: RequestKind = "production",
        business_context: Optional[BusinessContext] = None,
        model_override: Optional[str] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        del fast  # produzione: sempre modello principale (Qwen 14B)
        if not prompt or not str(prompt).strip():
            return "Per favore, inserisci un messaggio valido."

        if not self.is_configured():
            return f"Errore: {self.configuration_error_message()}"

        if business_context == "produzione" or business_context == "ordini":
            request_kind = "operational"
        if business_context and get_system_instruction and not (system_instruction or "").strip():
            lang = "it"
            if resolve_llm_language and load_app_config:
                lang = resolve_llm_language(load_app_config())
            system_instruction = get_system_instruction(business_context, language=lang)

        if self.provider == "ollama":
            model = (model_override or "").strip() or self._resolve_ollama_model()
            from llm.llm_inference_manager import InferenceQueueFullError, get_inference_manager

            mgr = get_inference_manager()
            ollama_options = (
                get_ollama_options(business_context, self._config)
                if get_ollama_options
                else {}
            )
            try:
                return mgr.run(
                    lambda: self._send_ollama(
                        prompt,
                        history,
                        system_instruction,
                        model_override=model,
                        request_kind=request_kind,
                        manager=mgr,
                        ollama_options=ollama_options,
                        on_chunk=on_chunk,
                    ),
                    model=model,
                )
            except InferenceQueueFullError as exc:
                return f"Errore: {exc}"
        if self.provider == "gemini":
            return self._send_gemini(prompt, history, system_instruction)
        return f"Errore: Provider LLM non supportato: {self.provider}"

    def _resolve_ollama_model(self) -> str:
        ollama_cfg = self._config.get("ollama") or {}
        return str(ollama_cfg.get("model", DEFAULT_LLM_CONFIG["ollama"]["model"]))

    def _resolve_keep_alive(self, request_kind: RequestKind) -> str:
        ollama_cfg = self._config.get("ollama") or {}
        if request_kind == "operational":
            return str(
                ollama_cfg.get(
                    "keep_alive_operational",
                    DEFAULT_LLM_CONFIG["ollama"]["keep_alive_operational"],
                )
            )
        return str(
            ollama_cfg.get(
                "keep_alive_production",
                DEFAULT_LLM_CONFIG["ollama"]["keep_alive_production"],
            )
        )

    def _gemini_api_key(self) -> Optional[str]:
        key = self._config.get("_api_key") or os.getenv("GEMINI_API_KEY")
        if key and str(key).strip():
            return str(key).strip()
        config_path = PROJECT_ROOT / "config.json"
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                api_key = data.get("api_key")
                if api_key and str(api_key).strip():
                    return str(api_key).strip()
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _probe_ollama(self) -> tuple[bool, bool]:
        """Ritorna (server_raggiungibile, modello_presente)."""
        ollama_cfg = self._config.get("ollama") or {}
        base_url = str(ollama_cfg.get("base_url", DEFAULT_LLM_CONFIG["ollama"]["base_url"])).rstrip("/")
        model = str(ollama_cfg.get("model", DEFAULT_LLM_CONFIG["ollama"]["model"]))
        try:
            req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            names = {
                m.get("name", "")
                for m in (body.get("models") or [])
                if isinstance(m, dict)
            }
            base_model = model.split(":")[0]
            for name in names:
                n_base = (name or "").split(":")[0]
                if name == model or name.startswith(f"{model}:") or n_base == base_model:
                    return True, True
            return True, False
        except Exception:
            return False, False

    def _ollama_is_available(self) -> bool:
        reachable, model_ok = self._probe_ollama()
        return reachable and model_ok

    def _send_ollama(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]],
        system_instruction: str,
        model_override: Optional[str] = None,
        request_kind: RequestKind = "production",
        manager=None,
        ollama_options: Optional[Dict[str, Any]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        from llm.ollama_runtime import request_finished, request_started

        ollama_cfg = self._config.get("ollama") or {}
        base_url = str(ollama_cfg.get("base_url", DEFAULT_LLM_CONFIG["ollama"]["base_url"])).rstrip("/")
        model = model_override or self._resolve_ollama_model()
        timeout = int(ollama_cfg.get("timeout_seconds", 180))
        keep_alive = self._resolve_keep_alive(request_kind)

        if manager is None:
            from llm.llm_inference_manager import get_inference_manager

            manager = get_inference_manager()

        messages: List[Dict[str, str]] = []
        if system_instruction and str(system_instruction).strip():
            messages.append({"role": "system", "content": str(system_instruction).strip()})
        if history:
            for msg in history:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "user")
                if role not in ("user", "assistant", "system"):
                    role = "user"
                text = msg.get("text") or msg.get("content") or ""
                if text:
                    messages.append({"role": role, "content": str(text)})
        messages.append({"role": "user", "content": str(prompt).strip()})

        payload_obj: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
        }
        if ollama_options:
            payload_obj["options"] = ollama_options

        payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")

        session = None
        try:
            print(f"Chiamata Ollama ({model}, keep_alive={keep_alive})")
            req = urllib.request.Request(
                f"{base_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            session = request_started(model)
            parts: List[str] = []
            done_payload: Optional[Dict[str, Any]] = None

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                manager._register_response(resp)
                for raw_line in resp:
                    if manager.is_abort_requested():
                        return "Errore: Inferenza interrotta dall'operatore."
                    line = raw_line.strip()
                    if not line:
                        continue
                    data = json.loads(line.decode("utf-8"))
                    message = data.get("message") or {}
                    content = ""
                    if isinstance(message, dict):
                        content = message.get("content") or ""
                    if content:
                        chunk = str(content)
                        parts.append(chunk)
                        session.on_chunk(chunk, data.get("eval_count"))
                        if on_chunk is not None:
                            on_chunk(chunk)
                    if data.get("done"):
                        done_payload = data
                        break

            print("Risposta Ollama ricevuta")
            if session is not None and done_payload:
                session.finish(
                    done_payload.get("eval_count"),
                    done_payload.get("eval_duration"),
                )
                session = None

            text = "".join(parts).strip()
            if not text:
                if manager.is_abort_requested():
                    return "Errore: Inferenza interrotta dall'operatore."
                return "Errore: Nessuna risposta ricevuta da Ollama."
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            print(f"Errore HTTP Ollama: {exc.code} {detail}")
            if exc.code == 404:
                return (
                    f"Errore: Modello '{model}' non trovato. Esegui: ollama pull {model}"
                )
            return f"Errore Ollama (HTTP {exc.code}): {detail}"
        except urllib.error.URLError as exc:
            print(f"Errore connessione Ollama: {exc}")
            return (
                "Errore: Ollama non raggiungibile. Verifica che sia avviato "
                f"su {base_url}."
            )
        except Exception as exc:
            traceback.print_exc()
            if manager.is_abort_requested():
                return "Errore: Inferenza interrotta dall'operatore."
            if "timed out" in str(exc).lower():
                return "Errore: Timeout richiesta Ollama. Il modello può richiedere più tempo al primo avvio."
            return f"Errore Ollama: {type(exc).__name__}: {str(exc)[:120]}"
        finally:
            manager._clear_response()
            if session is not None:
                request_finished()

    def _send_gemini(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]],
        system_instruction: str,
    ) -> str:
        api_key = self._gemini_api_key()
        if not api_key:
            return f"Errore: {self.configuration_error_message()}"

        try:
            from google import genai
            from llm.gemini_model_registry import get_model, initialize_registry
        except ImportError as exc:
            return f"Errore: SDK Gemini non installato ({exc})."

        client = genai.Client(api_key=api_key)
        initialize_registry(api_key)

        contents: List[Dict[str, Any]] = []
        if history:
            for msg in history:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "user")
                text = msg.get("text") or msg.get("content") or ""
                if text:
                    contents.append({"role": role, "parts": [{"text": str(text)}]})
        contents.append({"role": "user", "parts": [{"text": str(prompt).strip()}]})

        gemini_cfg = self._config.get("gemini") or {}
        preferred = str(gemini_cfg.get("model", "gemini-1.5-flash"))
        model_name = get_model(preferred, api_key)

        from llm.ollama_runtime import record_cloud_inference, request_finished, request_started

        request_started(model_name)
        t0 = time.perf_counter()
        try:
            print("Chiamata Gemini eseguita")
            response = client.models.generate_content(model=model_name, contents=contents)
            print("Risposta Gemini ricevuta")
        except Exception as exc:
            request_finished()
            traceback.print_exc()
            error_msg = str(exc)
            if "API_KEY_INVALID" in error_msg or "401" in error_msg:
                return "Errore: API Key non valida o scaduta. Verifica le impostazioni."
            if "QUOTA_EXCEEDED" in error_msg or "429" in error_msg:
                return "Errore: Quota API superata. Riprova più tardi."
            if "timeout" in error_msg.lower():
                return "Errore: Timeout della richiesta Gemini."
            return f"Errore Gemini: {error_msg[:120]}"

        text = None
        if hasattr(response, "text") and response.text:
            text = response.text
        elif hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and candidate.content:
                parts = getattr(candidate.content, "parts", None) or []
                if parts and hasattr(parts[0], "text"):
                    text = parts[0].text
        if not text:
            request_finished()
            return "Errore: Impossibile estrarre il testo dalla risposta Gemini."
        text = str(text).strip()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        record_cloud_inference(
            model=model_name,
            latency_ms=latency_ms,
            output_chars=len(text),
        )
        request_finished()
        return text


_llm_singleton: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLMService()
    else:
        _llm_singleton._config = load_llm_config()
        _llm_singleton.provider = _llm_singleton._config.get("provider", "ollama")
    return _llm_singleton


def reset_llm_service() -> None:
    """Utile dopo salvataggio Impostazioni."""
    global _llm_singleton
    _llm_singleton = None
    from llm.llm_inference_manager import reset_inference_manager

    reset_inference_manager()


def probe_gemini_api(config: Optional[Dict[str, Any]] = None) -> tuple[bool, str]:
    """
    Verifica reachability API Gemini (lista modelli).
    Ritorna (ok, messaggio breve).
    """
    cfg = config or load_llm_config()
    service = LLMService(cfg)
    if not service._gemini_api_key():
        return False, "API key missing"
    api_key = service._gemini_api_key()
    url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                return True, "Online"
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "Invalid API key"
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)[:80]
