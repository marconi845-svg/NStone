import json
import time
import urllib.request
from collections import deque
from datetime import datetime


METRICS_URL = "http://127.0.0.1:8000/metrics"
HEALTH_URL = "http://127.0.0.1:8000/health"
POLL_SECONDS = 10
WINDOW_SIZE = 6  # 1 minute with 10s polls
MAX_P95_SECONDS = 1.5
MAX_ERROR_RATE = 0.05


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_metric(text: str, name: str) -> float:
    for line in text.splitlines():
        if line.startswith(name + " "):
            try:
                return float(line.split(" ")[-1])
            except ValueError:
                return 0.0
    return 0.0


def emit_alert(kind: str, message: str) -> None:
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "warning",
        "service": "local-observability-watch",
        "event": kind,
        "message": message,
    }
    print(json.dumps(event, ensure_ascii=True))


def main() -> None:
    request_history = deque(maxlen=WINDOW_SIZE)
    error_history = deque(maxlen=WINDOW_SIZE)

    print(json.dumps({"event": "watcher.started", "service": "local-observability-watch"}))

    while True:
        try:
            _ = fetch_text(HEALTH_URL)
        except Exception as exc:
            emit_alert("health.down", f"Health check failed: {exc}")
            time.sleep(POLL_SECONDS)
            continue

        try:
            metrics = fetch_text(METRICS_URL)
            total = parse_metric(metrics, "http_requests_total")
            errors = parse_metric(metrics, "http_requests_total{handler=\"none\",method=\"none\",status=\"5xx\"}")
            p95 = parse_metric(metrics, "http_request_duration_seconds{quantile=\"0.95\"}")

            request_history.append(total)
            error_history.append(errors)

            if len(request_history) >= 2:
                req_delta = request_history[-1] - request_history[0]
                err_delta = error_history[-1] - error_history[0]
                error_rate = (err_delta / req_delta) if req_delta > 0 else 0.0
                if error_rate > MAX_ERROR_RATE:
                    emit_alert("api.error_rate.high", f"Error rate {error_rate:.2%} exceeds {MAX_ERROR_RATE:.2%}")

            if p95 > MAX_P95_SECONDS:
                emit_alert("api.latency.p95.high", f"P95 latency {p95:.2f}s exceeds {MAX_P95_SECONDS:.2f}s")
        except Exception as exc:
            emit_alert("metrics.unavailable", f"Metrics endpoint failed: {exc}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
