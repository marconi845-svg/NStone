"""Minimal HTTP server for FreeSWITCH Lua / local voice tests."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any, Dict

from modules.voice_bridge.pipeline import process_voice_turn


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class VoiceBridgeHandler(BaseHTTPRequestHandler):
    """POST /voice/turn · GET /health"""

    server_version = "NStoneVoiceBridge/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        del format, args

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "nstone_voice_bridge",
                },
            )
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/voice/turn":
            self._send_json(404, {"error": "not_found"})
            return
        payload = self._read_json_body()
        try:
            result = process_voice_turn(payload)
            status = 200 if result.get("ok") else 422
            self._send_json(status, result)
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)[:200]})


def create_server(host: str, port: int) -> _ThreadingHTTPServer:
    return _ThreadingHTTPServer((host, port), VoiceBridgeHandler)
