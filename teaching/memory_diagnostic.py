#!/usr/bin/env python3
"""Run one bounded in-process memory diagnostic without retaining task input."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys
import tracemalloc
from pathlib import Path

try:
    import resource
except ImportError:  # Windows exposes the process metric through psapi below.
    resource = None


def _load_controller(root: Path):
    scripts = root / "plugins" / "deepscientist-lite-core" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import ds_lite_autonomy

    return ds_lite_autonomy


def _process_peak_bytes() -> int:
    """Return a process peak metric without retaining process details."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(ProcessMemoryCounters)
        get_counters = ctypes.windll.psapi.GetProcessMemoryInfo
        get_counters.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        get_counters.restype = wintypes.BOOL
        if not get_counters(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return 0
        return int(counters.PeakWorkingSetSize)
    if resource is None:
        return 0
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # Linux reports KiB; macOS reports bytes.
    return int(usage.ru_maxrss * (1024 if sys.platform != "darwin" else 1))


def _contract() -> dict[str, object]:
    return {
        "schema_version": "ds-lite.autonomy-contract.v1",
        "autonomy_id": "memory-diagnostic",
        "status": "prepared",
        "goals": ["release-gate"],
        "gates": [{
            "id": "diagnostic",
            "depends_on": [],
            "command": ["python", "-V"],
            "receipt_ref": "receipts/diagnostic.json",
            "retry_class": "none",
        }],
        "budget": {"max_attempts_per_gate": 3, "max_seconds": 60},
        "authorization": {"status": "approved", "authority": "user", "ref": "approval.md"},
        "release": {"authorized": True, "required_gates": ["diagnostic"]},
    }


def run(root: Path, output: Path, iterations: int, max_growth_bytes: int) -> dict[str, object]:
    if output.exists():
        raise RuntimeError("memory diagnostic receipt already exists; refusing overwrite")
    if iterations < 2 or iterations > 100 or max_growth_bytes < 0:
        raise ValueError("invalid diagnostic bounds")
    controller = _load_controller(root)
    contract = _contract()
    tracemalloc.start()
    samples: list[dict[str, int]] = []
    previous_current = 0
    try:
        for _ in range(iterations):
            controller.validate_contract(contract)
            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
            samples.append({
                "current_bytes": current,
                "peak_bytes": peak,
                "current_delta_bytes": current - previous_current if samples else 0,
                "process_peak_bytes": _process_peak_bytes(),
            })
            previous_current = current
    finally:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    first = samples[0]["current_bytes"]
    last = samples[-1]["current_bytes"]
    growth = max(0, last - first)
    receipt = {
        "schema_version": "ds-lite.memory-diagnostic.v1",
        "status": "passed" if growth <= max_growth_bytes else "blocked",
        "failure_layer": "none" if growth <= max_growth_bytes else "resource/memory-growth",
        "iterations": iterations,
        "current_bytes_final": current,
        "peak_bytes_final": peak,
        "process_peak_bytes_final": _process_peak_bytes(),
        "current_growth_bytes": growth,
        "max_growth_bytes": max_growth_bytes,
        "sample_count": len(samples),
        "samples": samples,
        "samples_sha256": hashlib.sha256(json.dumps(samples, sort_keys=True).encode("utf-8")).hexdigest(),
        "raw_input_persisted": False,
        "raw_output_persisted": False,
        "raw_error_text_persisted": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded DS Lite memory diagnostic.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--max-growth-bytes", type=int, default=1024 * 1024)
    args = parser.parse_args()
    try:
        receipt = run(args.root.resolve(), args.output.resolve(), args.iterations, args.max_growth_bytes)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "memory-diagnostic", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
