"""
Avvio/arresto stack backend web (FastAPI :8000 + ngrok) da Quotations.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

import requests

FASTAPI_HEALTH_URL = "http://127.0.0.1:8000/health"
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
FASTAPI_PORT = 8000
_HEALTH_TIMEOUT = 2.0

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def backend_web_bat_path(project_root: Path) -> Path:
    return project_root / "avvia_backend_web.bat"


def is_fastapi_online() -> bool:
    try:
        resp = requests.get(FASTAPI_HEALTH_URL, timeout=_HEALTH_TIMEOUT)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def is_ngrok_online() -> bool:
    try:
        resp = requests.get(NGROK_API_URL, timeout=_HEALTH_TIMEOUT)
        if resp.status_code != 200:
            return False
        return bool(resp.json().get("tunnels"))
    except (requests.RequestException, ValueError):
        return False


def _run_hidden(args: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return subprocess.run(args, **kwargs)


def pids_listening_on_port(port: int) -> set[int]:
    if sys.platform != "win32":
        return set()
    result = _run_hidden(["netstat", "-ano"])
    pids: set[int] = set()
    token = f":{port}"
    for line in result.stdout.splitlines():
        if token not in line or "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return pids


def _kill_pids(pids: Iterable[int]) -> list[str]:
    lines: list[str] = []
    for pid in sorted(set(pids)):
        proc = _run_hidden(["taskkill", "/F", "/PID", str(pid)])
        if proc.returncode == 0:
            lines.append(f"Processo PID {pid} terminato.")
        else:
            err = (proc.stderr or proc.stdout or "").strip()
            lines.append(f"PID {pid}: {err or 'impossibile terminare'}")
    return lines


def _kill_by_image(image_name: str) -> list[str]:
    proc = _run_hidden(["taskkill", "/F", "/IM", image_name])
    if proc.returncode == 0:
        return [f"{image_name} terminato."]
    out = (proc.stderr or proc.stdout or "").strip()
    if "non trovato" in out.lower() or "not found" in out.lower():
        return [f"{image_name}: non in esecuzione."]
    return [f"{image_name}: {out or 'errore taskkill'}"]


def start_backend_web(project_root: Path) -> tuple[bool, str]:
    """Avvia avvia_backend_web.bat in una nuova finestra cmd."""
    bat = backend_web_bat_path(project_root)
    if not bat.is_file():
        return False, f"Script non trovato:\n{bat}"

    subprocess.Popen(
        ["cmd.exe", "/c", "start", "", str(bat)],
        cwd=str(project_root),
        shell=False,
    )

    parts = [
        "Avvio avvia_backend_web.bat in corso.",
        "Si apriranno finestre cmd per FastAPI e ngrok.",
        "Al termine verrà eseguito l'aggiornamento URL ngrok (push Git).",
    ]
    if is_fastapi_online():
        parts.insert(0, "Nota: FastAPI risulta già ONLINE sulla porta 8000.")
    if is_ngrok_online():
        parts.insert(0, "Nota: ngrok risulta già attivo.")

    parts.append("\nUsa «Verifica pipeline» tra qualche secondo per controllare lo stack.")
    return True, "\n".join(parts)


def stop_backend_web() -> tuple[bool, str]:
    """Arresta FastAPI (:8000) e ngrok."""
    if sys.platform != "win32":
        return False, "Arresto stack supportato solo su Windows."

    lines: list[str] = []
    port_pids = pids_listening_on_port(FASTAPI_PORT)
    if port_pids:
        lines.extend(_kill_pids(port_pids))
    else:
        lines.append(f"Nessun processo in ascolto sulla porta {FASTAPI_PORT}.")

    lines.extend(_kill_by_image("ngrok.exe"))

    fastapi_still = is_fastapi_online()
    ngrok_still = is_ngrok_online()
    if fastapi_still or ngrok_still:
        still = []
        if fastapi_still:
            still.append("FastAPI ancora online")
        if ngrok_still:
            still.append("ngrok ancora attivo")
        lines.append("Attenzione: " + ", ".join(still) + ".")
    else:
        lines.append("Stack backend web arrestato.")

    return True, "\n".join(lines)
