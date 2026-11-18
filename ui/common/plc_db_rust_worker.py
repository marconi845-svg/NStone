"""Worker QThread — motore PLC Rust on-demand (DB live)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from plc.plc_connection_diagnostics import collect_connection_stats
from plc.plc_map_loader import ResolvedDbBlock
from plc.plc_rust_bridge import build_rust_poll_plan, normalize_rust_snapshot, rust_plc_engine_available

RETRY_OFFLINE_MS = 8000
POLL_MS_DEFAULT = 400
POLL_MS_FAST = 120
POLL_MS_IDLE = 900
POLL_MS_PAUSED_SLEEP = 150
BURST_HOLD_S = 2.0
STATS_EVERY_CYCLES = 8


class PlcDbRustPollWorker(QThread):
    snapshot_ready = pyqtSignal(dict)
    conn_stats_ready = pyqtSignal(dict)
    status_message = pyqtSignal(str, bool)

    def __init__(
        self,
        machine_id: str,
        map_profile: str,
        ip: str,
        rack: int,
        slot: int,
        poll_blocks: List[ResolvedDbBlock],
        explore_db: int,
        explore_size: int,
        *,
        parallel_limit: int = 3,
        parent=None,
    ):
        super().__init__(parent)
        self._machine_id = machine_id
        self._map_profile = map_profile
        self._ip = ip
        self._rack = rack
        self._slot = slot
        self._poll_blocks = poll_blocks
        self._explore_db = explore_db
        self._explore_size = explore_size
        self._parallel_limit = parallel_limit
        self._stop_requested = False
        self._paused = False
        self._manual_once = False
        self._adaptive = True
        self._session: Any = None
        self._retry_count = 0
        self._burst_until = 0.0
        self._cycle = 0

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def set_adaptive(self, enabled: bool) -> None:
        self._adaptive = enabled

    def request_manual_poll(self) -> None:
        self._manual_once = True

    def update_explore(self, db_number: int, size: int, **_kwargs: Any) -> None:
        self._explore_db = db_number
        self._explore_size = size

    def request_stop(self) -> None:
        self._stop_requested = True

    def _cleanup(self) -> None:
        if self._session is not None:
            try:
                self._session.disconnect()
            except Exception:
                pass
            self._session = None

    def _poll_interval_ms(self, had_changes: bool) -> int:
        if had_changes:
            self._burst_until = time.monotonic() + BURST_HOLD_S
        now = time.monotonic()
        if now < self._burst_until:
            return POLL_MS_FAST
        if self._adaptive and not had_changes:
            return POLL_MS_IDLE
        return POLL_MS_DEFAULT

    def _build_plan(self) -> Dict[str, Any]:
        return build_rust_poll_plan(
            self._poll_blocks,
            self._explore_db,
            self._explore_size,
            self._map_profile,
            self._machine_id,
            parallel_limit=self._parallel_limit,
        )

    def run(self) -> None:
        if not rust_plc_engine_available():
            self.status_message.emit("Motore Rust non compilato (rust_engine)", True)
            return
        try:
            import rust_engine

            self._session = rust_engine.PlcEngineSession(
                self._ip, int(self._rack), int(self._slot)
            )
        except Exception as exc:
            self._retry_count += 1
            self.status_message.emit(
                f"Rust PLC non raggiungibile ({self._ip}) · {exc}", True
            )
            return

        self.status_message.emit(
            f"Online · Rust turbo · {self._map_profile}", False
        )
        prev_blocks: Dict[str, Any] = {}

        try:
            while not self._stop_requested:
                if self._paused and not self._manual_once:
                    self.msleep(POLL_MS_PAUSED_SLEEP)
                    continue

                try:
                    raw_payload = self._session.poll_snapshot(self._build_plan())
                    if not isinstance(raw_payload, dict):
                        raw_payload = dict(raw_payload)
                    payload = normalize_rust_snapshot(raw_payload)
                except Exception as exc:
                    self.status_message.emit(f"Errore poll Rust: {exc}", True)
                    self.msleep(RETRY_OFFLINE_MS // 2)
                    continue

                had_changes = False
                blocks = payload.get("blocks") or {}
                for key, values in blocks.items():
                    if prev_blocks.get(str(key)) != values:
                        had_changes = True
                prev_blocks = {str(k): v for k, v in blocks.items()}

                if self._stop_requested:
                    break

                self.snapshot_ready.emit(payload)
                self._cycle += 1

                if self._cycle % STATS_EVERY_CYCLES == 0 or self._manual_once:
                    stats = collect_connection_stats(
                        None,
                        self._ip,
                        retry_count=self._retry_count,
                        probe_db=self._explore_db,
                    )
                    stats.snap7_connected = bool(
                        self._session and self._session.is_connected()
                    )
                    stats.read_latency_ms = payload.get("read_latency_ms")
                    if not self._stop_requested:
                        self.conn_stats_ready.emit(stats.to_dict())

                self._manual_once = False
                if self._stop_requested:
                    break
                self.msleep(self._poll_interval_ms(had_changes))
        finally:
            self._cleanup()
