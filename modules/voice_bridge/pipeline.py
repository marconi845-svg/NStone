"""Voice turn pipeline: Whisper STT → NStone Ollama → Piper TTS."""
from __future__ import annotations

import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from modules.agentic_calling import (
    EXTENSION_COMMERCIAL,
    EXTENSION_MANAGEMENT,
    EXTENSION_PRODUCTION,
    append_call_log,
    load_agentic_calling_config,
)

SYSTEM_MANAGEMENT_VOICE = """Sei l'assistente vocale Management di NStone (marmo e pietre naturali).

CONTESTO: policy agenti, autonomia sistema, panoramica officina e back-office.

REGOLE VOCE
- Italiano, massimo 4 frasi brevi per risposta (telefono, no elenchi lunghi).
- Non inventare ordini, stock o stati macchina: se non sai, proponi di verificare in NStone desktop.
- Tono professionale e diretto."""

EXTENSION_TO_CONTEXT: Dict[str, Optional[str]] = {
    EXTENSION_MANAGEMENT: None,
    EXTENSION_COMMERCIAL: "offerte",
    EXTENSION_PRODUCTION: "produzione",
}

VOICE_MAX_CHARS = 320


def recordings_dir(cfg: Optional[Dict[str, Any]] = None) -> Path:
    cfg = cfg or load_agentic_calling_config()
    raw = (cfg.get("recordings_dir") or "").strip()
    if raw:
        path = Path(raw)
    else:
        path = Path(__file__).resolve().parents[2] / "logs" / "voice_bridge" / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def trim_for_voice(text: str, max_chars: int = VOICE_MAX_CHARS) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= max_chars:
        return cleaned
    cut = cleaned[:max_chars]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "…"


def _whisper_transcribe(cfg: Dict[str, Any], wav_path: Path) -> Tuple[str, str]:
    exe = (cfg.get("whisper_path") or "").strip()
    model = (cfg.get("whisper_model") or "").strip()
    if not exe or not wav_path.is_file():
        return "", "whisper_not_configured"
    if not Path(exe).is_file() and exe.lower() not in ("whisper", "whisper.exe", "main.exe"):
        return "", "whisper_path_invalid"

    out_base = wav_path.with_suffix("")
    cmd = [exe]
    if model:
        cmd.extend(["-m", model])
    cmd.extend(["-f", str(wav_path), "-otxt", "-l", "it", "-of", str(out_base)])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(cfg.get("whisper_timeout_seconds") or 90),
            check=False,
        )
        txt_path = out_base.with_suffix(".txt")
        if txt_path.is_file():
            return txt_path.read_text(encoding="utf-8", errors="replace").strip(), ""
        err = (result.stderr or result.stdout or "whisper_failed").strip()[:200]
        return "", err
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return "", str(exc)[:200]


def _piper_synthesize(cfg: Dict[str, Any], text: str, out_wav: Path) -> str:
    exe = (cfg.get("piper_path") or "").strip()
    voice = (cfg.get("piper_voice") or "").strip()
    if not exe or not voice or not text.strip():
        return "piper_not_configured"
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "--model", voice, "--output_file", str(out_wav)]
    try:
        result = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            timeout=int(cfg.get("piper_timeout_seconds") or 60),
            check=False,
        )
        if result.returncode == 0 and out_wav.is_file():
            return ""
        return (result.stderr or result.stdout or "piper_failed").strip()[:200]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return str(exc)[:200]


def _windows_sapi_synthesize(text: str, out_wav: Path) -> str:
    """Fallback TTS on Windows when Piper is not configured."""
    if sys.platform != "win32" or not text.strip():
        return "sapi_not_available"
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    txt_path = out_wav.with_suffix(".txt")
    try:
        txt_path.write_text(text, encoding="utf-8")
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            f"$t = Get-Content -Raw -Encoding UTF8 '{txt_path}'; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{out_wav}'); "
            "$s.Speak($t); $s.Dispose()"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if result.returncode == 0 and out_wav.is_file():
            return ""
        return (result.stderr or result.stdout or "sapi_failed").strip()[:200]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return str(exc)[:200]
    finally:
        if txt_path.is_file():
            try:
                txt_path.unlink()
            except OSError:
                pass


def _synthesize_voice(cfg: Dict[str, Any], text: str, out_wav: Path) -> str:
    err = _piper_synthesize(cfg, text, out_wav)
    if not err and out_wav.is_file():
        return ""
    if sys.platform == "win32":
        sapi_err = _windows_sapi_synthesize(text, out_wav)
        if not sapi_err and out_wav.is_file():
            return ""
        if err == "piper_not_configured":
            return sapi_err or err
    return err


VOICE_STT_FALLBACK = (
    "Chiamata telefonica in arrivo sull'interno commerciale. "
    "Il cliente ha parlato al microfono dopo il segnale acustico."
)


def _stt_or_fallback(cfg: Dict[str, Any], wav_path: Path) -> Tuple[str, str]:
    text_in, stt_err = _whisper_transcribe(cfg, wav_path)
    if text_in.strip():
        return text_in, ""
    if stt_err in ("whisper_not_configured", "whisper_path_invalid"):
        return VOICE_STT_FALLBACK, stt_err
    return "", stt_err


def _build_extra_context(extension_key: str, user_text: str) -> str:
    if extension_key != EXTENSION_COMMERCIAL or not user_text.strip():
        return ""
    try:
        from modules.catalog_db import (
            find_catalog_matches_for_message,
            format_catalog_context_for_offerte,
        )

        matches = find_catalog_matches_for_message(user_text)
        block = format_catalog_context_for_offerte(matches)
        if block:
            return f"\n\n{block}"
    except Exception:
        pass
    return ""


def _llm_reply(extension_key: str, user_text: str, cfg: Dict[str, Any]) -> Tuple[str, str]:
    from llm.llm_contexts import BusinessContext, get_system_instruction
    from llm.llm_service import get_llm_service

    llm = get_llm_service()
    if not llm.is_configured():
        return "", llm.configuration_error_message()

    business_context: Optional[BusinessContext] = EXTENSION_TO_CONTEXT.get(extension_key)  # type: ignore[assignment]
    if business_context:
        system = get_system_instruction(business_context)
    else:
        system = SYSTEM_MANAGEMENT_VOICE

    system += (
        "\n\nMODALITÀ VOCE: risposta breve per telefono (max 4 frasi). "
        "Niente markdown, niente JSON, niente elenchi numerati lunghi."
    )
    system += _build_extra_context(extension_key, user_text)

    try:
        voice_model = str(cfg.get("voice_ollama_model") or "").strip() or None
        reply = llm.send_message(
            user_text,
            system_instruction=system,
            business_context=business_context,
            request_kind="operational",
            model_override=voice_model,
        )
        return trim_for_voice(reply), ""
    except Exception as exc:
        return "", str(exc)[:200]


def process_voice_turn(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run one voice turn. Used by HTTP handler and optional CLI tests."""
    cfg = load_agentic_calling_config()
    extension_key = str(payload.get("extension_key") or EXTENSION_COMMERCIAL)
    call_uuid = str(payload.get("call_uuid") or uuid.uuid4())
    text_in = str(payload.get("text_in") or "").strip()
    wav_in_raw = str(payload.get("wav_in") or "").strip()

    errors: Dict[str, str] = {}
    wav_in_path: Optional[Path] = Path(wav_in_raw) if wav_in_raw else None

    if not text_in and wav_in_path and wav_in_path.is_file():
        text_in, stt_err = _stt_or_fallback(cfg, wav_in_path)
        if stt_err:
            errors["stt"] = stt_err
    elif not text_in:
        if wav_in_raw:
            errors["stt"] = "wav_in file not found"
        else:
            errors["stt"] = "no wav_in or text_in"

    if not text_in:
        return {
            "ok": False,
            "call_uuid": call_uuid,
            "extension_key": extension_key,
            "text_in": "",
            "text_out": "",
            "wav_out": "",
            "errors": errors,
        }

    text_out, llm_err = _llm_reply(extension_key, text_in, cfg)
    if llm_err:
        errors["llm"] = llm_err

    rec_dir = recordings_dir(cfg)
    wav_out_path = rec_dir / f"{call_uuid}_out.wav"
    wav_out = ""
    if text_out:
        tts_err = _synthesize_voice(cfg, text_out, wav_out_path)
        if tts_err:
            errors["tts"] = tts_err
        elif wav_out_path.is_file():
            wav_out = str(wav_out_path)

    ext_cfg = (cfg.get("extensions") or {}).get(extension_key) or {}
    number = str(ext_cfg.get("number") or "?")

    append_call_log(
        {
            "extension_key": extension_key,
            "number": number,
            "call_uuid": call_uuid,
            "summary": f"Voice: {text_in[:80]} → {text_out[:80]}",
            "text_in": text_in,
            "text_out": text_out,
            "source": payload.get("source") or "voice_bridge",
        }
    )

    ok = bool(text_out) and "llm" not in errors
    return {
        "ok": ok,
        "call_uuid": call_uuid,
        "extension_key": extension_key,
        "text_in": text_in,
        "text_out": text_out,
        "wav_out": wav_out,
        "errors": errors,
    }
