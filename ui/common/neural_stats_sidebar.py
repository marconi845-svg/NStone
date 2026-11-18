"""
Metriche NEURAL STATS per sidebar Quotations / Orders (motore LLM + pipeline locale).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Mapping, Optional

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QLabel


class NeuralStatsPollWorker(QThread):
    """Poll Ollama + snapshot runtime LLM (non blocca UI)."""

    # Mai chiamarlo "finished": oscurerebbe QThread.finished (crash deleteLater)
    result_ready = pyqtSignal(dict)

    def __init__(self, pipeline_counts: dict, parent=None):
        super().__init__(parent)
        self.pipeline_counts = dict(pipeline_counts or {})

    def run(self):
        if self.isInterruptionRequested():
            return
        from llm.llm_inference_manager import get_inference_manager
        from llm.llm_service import load_llm_config, ui_model_label_from_config
        from llm.ollama_runtime import get_snapshot, update_poll

        cfg = load_llm_config()
        provider = str(cfg.get("provider") or "ollama")

        if provider == "ollama":
            ollama = cfg.get("ollama") or {}
            base = str(ollama.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
            try:
                req = urllib.request.Request(f"{base}/api/ps", method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                models = [
                    str(item["name"])
                    for item in (data.get("models") or [])
                    if isinstance(item, dict) and item.get("name")
                ]
                update_poll(reachable=True, loaded_models=models)
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
                update_poll(reachable=False, loaded_models=[])

        snap = get_snapshot()
        queue = get_inference_manager().queue_stats()
        tps = snap.live_tokens_per_sec if snap.live_tokens_per_sec is not None else snap.tokens_per_sec

        if self.isInterruptionRequested():
            return
        self.result_ready.emit(
            {
                "model": ui_model_label_from_config(cfg),
                "provider": provider,
                "status": snap.status,
                "ollama_reachable": snap.ollama_reachable,
                "cloud_api_ok": snap.cloud_api_ok,
                "tps": tps,
                "latency_ms": snap.last_latency_ms,
                "queue_active": queue.get("active", 0),
                "queue_waiting": queue.get("waiting", 0),
                "vram_models": list(snap.loaded_in_vram or []),
                "pipeline_counts": self.pipeline_counts,
            }
        )


def pipeline_summary_line(counts: Mapping[str, int], *, kind: str = "quotations") -> tuple[str, str]:
    total = int(counts.get("total") or 0)
    new_c = int(counts.get("new") or 0)
    done_c = int(counts.get("done") or 0)
    if kind == "orders":
        text = f"Ordini: {new_c} in coda · {done_c} inviati · {total} in DB"
    else:
        text = f"Pipeline: {new_c} nuove · {done_c} elaborate · {total} totali"
    color = "#FFD93D" if new_c > 0 else "#00FF00" if done_c else "#888899"
    return text, color


def apply_neural_stats_to_labels(labels: Dict[str, QLabel], stats: dict, *, pipeline_kind: str = "quotations") -> None:
    model = stats.get("model") or "—"
    provider = stats.get("provider") or "ollama"
    status = str(stats.get("status") or "idle")
    status_it = {"idle": "Idle", "waiting": "In attesa", "running": "In esecuzione"}.get(
        status, status
    )

    if provider == "gemini":
        online = stats.get("cloud_api_ok")
        engine_color = "#00FF00" if online else "#FF6666"
        engine_text = f"Motore: Gemini · {status_it}"
    else:
        online = stats.get("ollama_reachable")
        engine_color = "#00FF00" if online else "#FF6666"
        vram = stats.get("vram_models") or []
        vram_hint = ""
        if vram:
            short = vram[0][:22] + "…" if len(vram[0]) > 22 else vram[0]
            vram_hint = f" · VRAM: {short}"
        engine_text = f"Motore: Ollama · {status_it}{vram_hint}"

    tps = stats.get("tps")
    if tps is not None:
        tps_text = f"Tokens/s: {float(tps):.1f}"
        tps_color = "#00FF00" if status == "running" else "#8B5CF6"
    else:
        latency = stats.get("latency_ms")
        if latency is not None and provider == "gemini":
            tps_text = f"Ultima risposta: {float(latency):.0f} ms"
            tps_color = "#8B5CF6"
        else:
            tps_text = "Tokens/s: —"
            tps_color = "#888899"

    active = int(stats.get("queue_active") or 0)
    waiting = int(stats.get("queue_waiting") or 0)
    queue_color = "#e6a817" if waiting or active else "#888899"

    counts = stats.get("pipeline_counts") or {}
    pipeline_text, pipeline_color = pipeline_summary_line(counts, kind=pipeline_kind)

    labels["model"].setText(f"Modello: {model}")
    labels["model"].setStyleSheet("color: #8B5CF6; font-size: 11px;")

    labels["engine"].setText(engine_text)
    labels["engine"].setStyleSheet(f"color: {engine_color}; font-size: 11px;")

    labels["tps"].setText(tps_text)
    labels["tps"].setStyleSheet(f"color: {tps_color}; font-size: 11px;")

    labels["queue"].setText(
        f"Coda inferenze: {active} attiv{'a' if active == 1 else 'e'} · {waiting} in attesa"
    )
    labels["queue"].setStyleSheet(f"color: {queue_color}; font-size: 11px;")

    labels["pipeline"].setText(pipeline_text)
    labels["pipeline"].setStyleSheet(f"color: {pipeline_color}; font-size: 11px;")
