"""Worker thread polling PLC per DB live dialog."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from plc.plc_connection_diagnostics import collect_connection_stats
from plc.plc_db_size_probe import resolve_db_read_size
from plc.plc_map_decoder import decode_variables
from plc.plc_map_loader import ResolvedDbBlock, find_block_spec
from plc.plc_snap7_reader import read_db_chunked

RETRY_OFFLINE_MS = 8000
POLL_MS_DEFAULT = 400
POLL_MS_FAST = 120
POLL_MS_IDLE = 900
POLL_MS_PAUSED_SLEEP = 150
BURST_HOLD_S = 2.0
STATS_EVERY_CYCLES = 8


def _apply_snap7_fast_timeouts(s7_client: Any, timeout_ms: int) -> None:
    for code in (2, 3, 4):
        try:
            s7_client.set_param(code, timeout_ms)
        except Exception:
            pass


def create_plc_client(
    machine_id: str, ip: str, rack: int, slot: int, timeout_ms: int
) -> Optional[Any]:
    try:
        if machine_id == "multifilo":
            from plc.snap7_multifilo_client import MultifiloPLCClient

            client = MultifiloPLCClient(
                ip=ip, rack=rack, slot=slot, timeout=timeout_ms
            )
        elif machine_id == "lucidatrice":
            from plc.snap7_lucidatrice_client import LucidatricePLCClient

            client = LucidatricePLCClient(
                ip=ip, rack=rack, slot=slot, timeout=timeout_ms
            )
        else:
            return None
        _apply_snap7_fast_timeouts(client.client, timeout_ms)
        return client
    except ImportError:
        return None


class PlcDbPollWorker(QThread):
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
        explore_auto_detect: bool = True,
        explore_user_size: Optional[int] = None,
        connect_timeout_ms: int = 2500,
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
        self._explore_auto = explore_auto_detect
        self._explore_user_size = explore_user_size
        self._connect_timeout_ms = connect_timeout_ms
        self._stop_requested = False
        self._paused = False
        self._manual_once = False
        self._adaptive = True
        self._plc_client: Any = None
        self._db_sizes: Dict[int, int] = {}
        self._size_sources: Dict[int, str] = {}
        self._retry_count = 0
        self._burst_until = 0.0
        self._cycle = 0

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def set_adaptive(self, enabled: bool) -> None:
        self._adaptive = enabled

    def request_manual_poll(self) -> None:
        self._manual_once = True

    def trigger_burst(self) -> None:
        self._burst_until = time.monotonic() + BURST_HOLD_S

    def update_explore(
        self,
        db_number: int,
        size: int,
        *,
        auto_detect: bool = True,
        user_size: Optional[int] = None,
    ) -> None:
        self._explore_db = db_number
        self._explore_size = size
        self._explore_auto = auto_detect
        self._explore_user_size = user_size

    def request_stop(self) -> None:
        self._stop_requested = True

    def _cleanup_client(self) -> None:
        if self._plc_client is not None:
            try:
                self._plc_client.disconnect()
            except Exception:
                pass
            self._plc_client = None

    def _resolve_block_size(self, block: ResolvedDbBlock) -> int:
        if block.number in self._db_sizes:
            return self._db_sizes[block.number]
        map_size = block.size_bytes
        user = None
        size, src = resolve_db_read_size(
            self._plc_client,
            block.number,
            map_size=map_size,
            user_size=user,
            auto_detect=True,
        )
        self._db_sizes[block.number] = size
        self._size_sources[block.number] = src
        return size

    def _explore_bytes(self) -> int:
        spec = find_block_spec(
            self._map_profile, self._machine_id, self._explore_db
        )
        map_size = spec.size_bytes if spec else None
        if self._explore_user_size and self._explore_user_size > 0:
            return int(self._explore_user_size)
        if self._explore_db in self._db_sizes and self._explore_auto:
            return self._db_sizes[self._explore_db]
        size, src = resolve_db_read_size(
            self._plc_client,
            self._explore_db,
            map_size=map_size,
            user_size=self._explore_size if not self._explore_auto else None,
            auto_detect=self._explore_auto,
        )
        self._db_sizes[self._explore_db] = size
        self._size_sources[self._explore_db] = src
        return size

    def _read_block(self, db_number: int, size: int) -> Optional[bytes]:
        if self._plc_client is None or size <= 0:
            return None
        return read_db_chunked(self._plc_client, db_number, size)

    def _poll_interval_ms(self, had_changes: bool) -> int:
        if had_changes:
            self.trigger_burst()
        now = time.monotonic()
        if now < self._burst_until:
            return POLL_MS_FAST
        if self._adaptive and not had_changes:
            return POLL_MS_IDLE
        return POLL_MS_DEFAULT

    def run(self) -> None:
        self._plc_client = create_plc_client(
            self._machine_id,
            self._ip,
            self._rack,
            self._slot,
            self._connect_timeout_ms,
        )
        if self._plc_client is None:
            self.status_message.emit("Client Snap7 non disponibile", True)
            return
        try:
            if not self._plc_client.connect():
                self._retry_count += 1
                self.status_message.emit(
                    f"PLC non raggiungibile ({self._ip}:102) · retry {self._retry_count}",
                    True,
                )
                return
            self.status_message.emit(f"Online · {self._map_profile}", False)
            prev_snapshot: Dict[str, Any] = {}

            while not self._stop_requested:
                if self._paused and not self._manual_once:
                    self.msleep(POLL_MS_PAUSED_SLEEP)
                    continue

                t0 = time.perf_counter()
                payload: Dict[str, Any] = {
                    "blocks": {},
                    "explore": None,
                    "db_sizes": dict(self._db_sizes),
                    "size_sources": dict(self._size_sources),
                }
                had_changes = False

                for block in self._poll_blocks:
                    if self._stop_requested:
                        break
                    size = self._resolve_block_size(block)
                    raw = self._read_block(block.number, size)
                    if raw is None:
                        continue
                    values = decode_variables(raw, block.variables)
                    payload["blocks"][block.number] = values
                    key = str(block.number)
                    if prev_snapshot.get(key) != values:
                        had_changes = True

                exp_size = self._explore_bytes()
                if not self._stop_requested and exp_size > 0:
                    raw = self._read_block(self._explore_db, exp_size)
                    if raw is not None:
                        spec = find_block_spec(
                            self._map_profile,
                            self._machine_id,
                            self._explore_db,
                        )
                        decoded = (
                            decode_variables(raw, spec.variables) if spec else {}
                        )
                        payload["explore"] = (
                            self._explore_db,
                            raw,
                            decoded,
                            exp_size,
                            self._size_sources.get(self._explore_db, "?"),
                        )

                payload["read_latency_ms"] = round(
                    (time.perf_counter() - t0) * 1000.0, 2
                )
                payload["engine"] = "python"
                prev_snapshot = {
                    str(k): v for k, v in payload.get("blocks", {}).items()
                }

                if self._stop_requested:
                    break

                self.snapshot_ready.emit(payload)
                self._cycle += 1
                if (
                    not self._stop_requested
                    and (self._cycle % STATS_EVERY_CYCLES == 0 or self._manual_once)
                ):
                    stats = collect_connection_stats(
                        self._plc_client,
                        self._ip,
                        retry_count=self._retry_count,
                        probe_db=self._explore_db,
                    )
                    stats.read_latency_ms = payload["read_latency_ms"]
                    if not self._stop_requested:
                        self.conn_stats_ready.emit(stats.to_dict())

                self._manual_once = False
                if self._stop_requested:
                    break
                self.msleep(self._poll_interval_ms(had_changes))
        finally:
            self._cleanup_client()
