import importlib

import pytest

from plc.rust_bridge import run_heavy_task


def _binding_ready() -> bool:
    module = importlib.import_module("rust_engine")
    return hasattr(module, "run_heavy_task")


def test_python_rust_bridge_precheck() -> None:
    if not _binding_ready():
        # Diagnostic test: bridge should fail gracefully when extension is missing.
        result = run_heavy_task("test_parallel", {"values": [1, 2, 3]})
        assert result.get("status") == "error"
        assert "run_heavy_task" in result.get("error", "")
        return

    result = run_heavy_task("test_parallel", {"values": [1, 2, 3]})
    assert result.get("status") == "ok"


def test_run_heavy_task_parallel_returns_valid_payload() -> None:
    if not _binding_ready():
        pytest.skip("Rust binding non compilato/caricato in questo ambiente")
    result = run_heavy_task("test_parallel", {"values": [1, 2, 3, 4, 5]})

    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert result.get("task_type") == "test_parallel"
    assert isinstance(result.get("data"), dict)
    assert "metrics" in result


def test_run_heavy_task_handles_invalid_payload_without_crash() -> None:
    if not _binding_ready():
        pytest.skip("Rust binding non compilato/caricato in questo ambiente")
    # Missing required field 'values' should return an error object, not crash Python.
    result = run_heavy_task("test_parallel", {"wrong_key": [1, 2, 3]})

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert result.get("task_type") == "test_parallel"
    assert "error" in result


@pytest.mark.parametrize("iteration", range(10))
def test_repeated_calls_are_stable(iteration: int) -> None:
    if not _binding_ready():
        pytest.skip("Rust binding non compilato/caricato in questo ambiente")
    # Repeated calls help catch silent crashes in Python<->Rust boundary.
    result = run_heavy_task("fake_simulation", {"steps": 250, "intensity": 2})

    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert result.get("task_type") == "fake_simulation"
    assert isinstance(result.get("data"), dict)
