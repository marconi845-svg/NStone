"""Test coda inferenze LLM."""
import threading
import time

import pytest

from llm.llm_inference_manager import InferenceQueueFullError, LLMInferenceManager
from llm.ollama_runtime import reset_runtime_state


@pytest.fixture(autouse=True)
def _clean_runtime():
    reset_runtime_state()
    yield
    reset_runtime_state()


def test_queue_serializes_calls():
    mgr = LLMInferenceManager(max_concurrent=1, max_queue=3)
    order = []
    lock = threading.Lock()

    def job(name: str, delay: float = 0.05) -> str:
        def _run():
            with lock:
                order.append(f"start-{name}")
            time.sleep(delay)
            with lock:
                order.append(f"end-{name}")
            return name

        return mgr.run(_run, model="test-model")

    t1 = threading.Thread(target=lambda: job("a", 0.08))
    t2 = threading.Thread(target=lambda: job("b", 0.02))
    t1.start()
    time.sleep(0.01)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert order.index("start-a") < order.index("end-a")
    assert order.index("end-a") < order.index("start-b")


def test_queue_full_raises():
    mgr = LLMInferenceManager(max_concurrent=1, max_queue=1)
    started = threading.Event()
    release = threading.Event()

    def long_job():
        started.set()
        release.wait(timeout=5)
        return "ok"

    t_holder = threading.Thread(
        target=lambda: mgr.run(long_job, model="m1"),
        daemon=True,
    )
    t_holder.start()
    assert started.wait(timeout=2)

    waiters = []
    errors = []

    def waiter():
        try:
            mgr.run(lambda: "x", model="m2")
        except InferenceQueueFullError as exc:
            errors.append(str(exc))

    for _ in range(2):
        t = threading.Thread(target=waiter, daemon=True)
        waiters.append(t)
        t.start()
    time.sleep(0.2)
    for t in waiters:
        t.join(timeout=2)
    release.set()
    t_holder.join(timeout=3)
    assert errors
