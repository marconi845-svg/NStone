"""Keep NStone Voice Bridge running (for MicroSIP / FreeSWITCH tests)."""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.voice_bridge.manager import (  # noqa: E402
    check_voice_bridge_health,
    start_voice_bridge,
    stop_voice_bridge,
)


def main() -> int:
    result = start_voice_bridge(force=True)
    print(result.message)
    if not result.started:
        return 1

    ok, detail = check_voice_bridge_health(result.host, result.port)
    print(f"Health: {'OK' if ok else 'FAIL'} ({detail})")
    print(f"Test: curl.exe http://{result.host}:{result.port}/health")
    print("Lascia questa finestra aperta durante le chiamate al 2000. Ctrl+C per uscire.")

    def _shutdown(_signum=None, _frame=None) -> None:
        stop_voice_bridge()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
