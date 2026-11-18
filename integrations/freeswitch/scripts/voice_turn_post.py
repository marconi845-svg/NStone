"""POST JSON to NStone Voice Bridge (called from FreeSWITCH Lua on Windows)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: voice_turn_post.py request.json response.json", file=sys.stderr)
        return 2

    req_path, resp_path = sys.argv[1], sys.argv[2]
    tmp_path = resp_path + ".part"
    payload = json.loads(open(req_path, encoding="utf-8-sig").read())
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8765/voice/turn",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        open(resp_path, "w", encoding="utf-8").write("")
        print(str(exc), file=sys.stderr)
        return 1

    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(raw)
    try:
        import os

        os.replace(tmp_path, resp_path)
    except OSError:
        open(resp_path, "w", encoding="utf-8").write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
