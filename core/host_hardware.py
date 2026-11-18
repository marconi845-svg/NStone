"""
Lettura metriche host (CPU, GPU, RAM) on-demand per la dashboard NStone.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _empty_result() -> Dict[str, Any]:
    return {
        "cpu": {"freq_mhz": None, "temp_c": None, "usage_pct": None},
        "gpu": {"name": None, "freq_mhz": None, "temp_c": None, "available": False},
        "ram": {"used_pct": None, "used_gb": None, "total_gb": None},
        "notes": [],
    }


def _run_powershell(script: str, timeout: float = 12.0) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, "", ""


def _kelvin_sample_to_celsius(value: float) -> float:
    if value > 1000:
        return (value / 10.0) - 273.15
    return value - 273.15


def _read_cpu_temp_psutil() -> Optional[float]:
    try:
        import psutil
    except ImportError:
        return None
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    if not temps:
        return None
    for key in ("coretemp", "cpu_thermal", "acpitz", "k10temp"):
        if key in temps and temps[key]:
            return round(temps[key][0].current, 1)
    first_group = next(iter(temps.values()), None)
    if first_group:
        return round(first_group[0].current, 1)
    return None


def _read_cpu_temp_windows_counters() -> Optional[float]:
    script = r"""
$hp = (Get-Counter '\Thermal Zone Information(*)\High Precision Temperature' -ErrorAction SilentlyContinue).CounterSamples
$plain = (Get-Counter '\Thermal Zone Information(*)\Temperature' -ErrorAction SilentlyContinue).CounterSamples
$samples = @()
if ($hp) { $samples += $hp }
if ($plain) { $samples += $plain }
if (-not $samples) { exit 2 }
$temps = foreach ($s in $samples) {
    $v = [double]$s.CookedValue
    if ($v -gt 1000) { ($v / 10.0) - 273.15 } else { $v - 273.15 }
}
[math]::Round(($temps | Measure-Object -Maximum).Maximum, 1)
"""
    code, out, _ = _run_powershell(script)
    if code != 0 or not out:
        return None
    try:
        temp = float(out.replace(",", "."))
    except ValueError:
        return None
    if temp < -40 or temp > 120:
        return None
    return round(temp, 1)


def _read_cpu_temp_wmi_sensors() -> Optional[float]:
    """LibreHardwareMonitor / OpenHardwareMonitor (richiede app in esecuzione + WMI)."""
    script = r"""
$namespaces = @('root\LibreHardwareMonitor', 'root\OpenHardwareMonitor')
$best = $null
foreach ($ns in $namespaces) {
    $sensors = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction SilentlyContinue |
        Where-Object { $_.SensorType -eq 3 -and $_.Value -ne $null }
    foreach ($s in $sensors) {
        $id = [string]$s.Identifier
        $name = [string]$s.Name
        if ($id -match 'cpu|intelcpu|amdcpu' -or $name -match 'CPU|Core|Package|Tctl|Tdie') {
            $v = [double]$s.Value
            if ($v -ge -40 -and $v -le 120 -and ($null -eq $best -or $v -gt $best)) {
                $best = $v
            }
        }
    }
}
if ($null -eq $best) { exit 2 }
[math]::Round($best, 1)
"""
    code, out, _ = _run_powershell(script)
    if code != 0 or not out:
        return None
    try:
        return round(float(out.replace(",", ".")), 1)
    except ValueError:
        return None


def _read_cpu_temp() -> Optional[float]:
    temp = _read_cpu_temp_psutil()
    if temp is not None:
        return temp
    if sys.platform == "win32":
        temp = _read_cpu_temp_windows_counters()
        if temp is not None:
            return temp
        temp = _read_cpu_temp_wmi_sensors()
        if temp is not None:
            return temp
    return None


def _read_gpu_pynvml() -> Dict[str, Any]:
    gpu = {"name": None, "freq_mhz": None, "temp_c": None, "available": False}
    try:
        import pynvml
    except ImportError:
        return gpu
    initialized = False
    try:
        pynvml.nvmlInit()
        initialized = True
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu["available"] = True
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        gpu["name"] = name
        gpu["freq_mhz"] = pynvml.nvmlDeviceGetClockInfo(
            handle, pynvml.NVML_CLOCK_GRAPHICS
        )
        gpu["temp_c"] = pynvml.nvmlDeviceGetTemperature(
            handle, pynvml.NVML_TEMPERATURE_GPU
        )
    except Exception:
        pass
    finally:
        if initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
    return gpu


def _read_gpu_nvidia_smi() -> Dict[str, Any]:
    gpu = {"name": None, "freq_mhz": None, "temp_c": None, "available": False}
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,clocks.gr",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return gpu
    if proc.returncode != 0 or not proc.stdout.strip():
        return gpu
    line = proc.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return gpu
    try:
        gpu["name"] = parts[0]
        gpu["temp_c"] = int(float(parts[1]))
        gpu["freq_mhz"] = int(float(parts[2]))
        gpu["available"] = True
    except ValueError:
        return {"name": None, "freq_mhz": None, "temp_c": None, "available": False}
    return gpu


def _read_gpu_wmi_sensors() -> Dict[str, Any]:
    gpu = {"name": None, "freq_mhz": None, "temp_c": None, "available": False}
    script = r"""
$namespaces = @('root\LibreHardwareMonitor', 'root\OpenHardwareMonitor')
$best = $null
$gpuName = $null
foreach ($ns in $namespaces) {
    $sensors = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction SilentlyContinue |
        Where-Object { $_.SensorType -eq 3 -and $_.Value -ne $null }
    foreach ($s in $sensors) {
        $id = [string]$s.Identifier
        if ($id -match 'gpu|nvidia|ati|amd') {
            $v = [double]$s.Value
            if ($v -ge -40 -and $v -le 120 -and ($null -eq $best -or $v -gt $best)) {
                $best = $v
                if ($s.Parent) { $gpuName = [string]$s.Parent }
            }
        }
    }
}
if ($null -eq $best) { exit 2 }
Write-Output ($best.ToString() + '|' + $(if ($gpuName) { $gpuName } else { 'GPU' }))
"""
    code, out, _ = _run_powershell(script)
    if code != 0 or not out or "|" not in out:
        return gpu
    temp_str, name = out.split("|", 1)
    try:
        gpu["temp_c"] = round(float(temp_str.replace(",", ".")), 1)
        gpu["name"] = name.strip() or "GPU"
        gpu["available"] = True
    except ValueError:
        pass
    return gpu


def _read_gpu() -> Dict[str, Any]:
    gpu = _read_gpu_pynvml()
    if gpu["available"]:
        return gpu
    gpu = _read_gpu_nvidia_smi()
    if gpu["available"]:
        return gpu
    return _read_gpu_wmi_sensors()


def detect_nvidia_gpu_info() -> Dict[str, Any]:
    """
    Info GPU NVIDIA per policy pre-warm Ollama.
    Ritorna: available, name, vram_gb (float|None).
    """
    info: Dict[str, Any] = {"available": False, "name": None, "vram_gb": None}
    try:
        import pynvml
    except ImportError:
        pynvml = None  # type: ignore[assignment]

    if pynvml is not None:
        initialized = False
        try:
            pynvml.nvmlInit()
            initialized = True
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            info["available"] = True
            info["name"] = name
            info["vram_gb"] = round(mem.total / (1024**3), 1)
            return info
        except Exception:
            pass
        finally:
            if initialized:
                try:
                    pynvml.nvmlShutdown()
                except Exception:
                    pass

    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return info
    if proc.returncode != 0 or not proc.stdout.strip():
        return info
    line = proc.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 2:
        return info
    try:
        info["name"] = parts[0]
        info["vram_gb"] = round(float(parts[1]) / 1024.0, 1)
        info["available"] = True
    except ValueError:
        pass
    return info


def get_hw_info() -> Dict[str, Any]:
    """Raccoglie metriche host. Chiamare da thread secondario (cpu_percent blocca brevemente)."""
    result = _empty_result()
    notes: List[str] = result["notes"]

    try:
        import psutil
    except ImportError:
        notes.append("Installa psutil: pip install psutil")
        return result

    try:
        result["cpu"]["usage_pct"] = round(psutil.cpu_percent(interval=0.2), 1)
    except Exception as exc:
        notes.append(f"CPU: {exc}")

    try:
        freq = psutil.cpu_freq()
        if freq and freq.current:
            result["cpu"]["freq_mhz"] = round(freq.current, 0)
    except Exception:
        pass

    result["cpu"]["temp_c"] = _read_cpu_temp()
    if result["cpu"]["temp_c"] is None:
        if sys.platform == "win32":
            notes.append(
                "Temp CPU: contatori Windows non disponibili; "
                "opzionale LibreHardwareMonitor (WMI) in esecuzione"
            )
        else:
            notes.append("Temperatura CPU non disponibile su questo sistema")

    try:
        vm = psutil.virtual_memory()
        result["ram"]["used_pct"] = round(vm.percent, 1)
        result["ram"]["used_gb"] = round(vm.used / (1024**3), 2)
        result["ram"]["total_gb"] = round(vm.total / (1024**3), 2)
    except Exception as exc:
        notes.append(f"RAM: {exc}")

    result["gpu"] = _read_gpu()
    if not result["gpu"]["available"]:
        if sys.platform == "win32":
            notes.append(
                "GPU: driver NVIDIA/AMD non rilevati; "
                "opzionale LibreHardwareMonitor (WMI) in esecuzione"
            )
        else:
            notes.append("GPU non rilevata (NVIDIA: pip install nvidia-ml-py)")

    return result


def get_hw_snapshot() -> Dict[str, Any]:
    """Lettura veloce psutil per telemetria live (no PowerShell / nvidia-smi)."""
    snap = {
        "cpu_usage_pct": None,
        "ram_used_pct": None,
        "ram_used_gb": None,
        "ram_total_gb": None,
        "ok": False,
    }
    try:
        import psutil
    except ImportError:
        return snap

    try:
        snap["cpu_usage_pct"] = round(psutil.cpu_percent(interval=None), 1)
        vm = psutil.virtual_memory()
        snap["ram_used_pct"] = round(vm.percent, 1)
        snap["ram_used_gb"] = round(vm.used / (1024**3), 2)
        snap["ram_total_gb"] = round(vm.total / (1024**3), 2)
        snap["ok"] = True
    except Exception:
        pass
    return snap
