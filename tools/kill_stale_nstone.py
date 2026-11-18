"""Termina processi Python zombie con nstone_main_window.py (dopo chiusura anomala)."""
from __future__ import annotations

import os
import sys


def main() -> int:
    try:
        import psutil
    except ImportError:
        return 0

    me = os.getpid()
    killed = 0
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            pid = proc.info.get("pid")
            if not pid or pid == me:
                continue
            cmdline = proc.info.get("cmdline") or []
            text = " ".join(str(part) for part in cmdline).lower()
            if "nstone_main_window.py" not in text:
                continue
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            killed += 1
            print(f"Terminato processo zombie PID {pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        print(f"Puliti {killed} processi NSTONELLM residui.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
