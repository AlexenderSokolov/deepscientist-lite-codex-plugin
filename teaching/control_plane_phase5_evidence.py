from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
SCHEMA_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "schemas"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.dbos_bridge import DBOSBridge  # noqa: E402
from ds_lite_control.runtime_pin import verify_runtime_selection  # noqa: E402
from ds_lite_control.store import ControlStore  # noqa: E402


MIB = 1024 * 1024
RESOURCE_THRESHOLDS = {
    "controller-schema": 8 * MIB,
    "install-delta": 100 * MIB,
    "rss-p95": 150 * MIB,
    "empty-databases": 2 * MIB,
    "action-growth": 25 * MIB,
}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def write_once(path: Path, payload: dict[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def evaluate_resource_samples(
    samples: list[dict[str, Any]], *, controller_schema_bytes: int,
    install_delta_bytes: int, empty_databases_bytes: int,
    action_growth_bytes: int,
) -> dict[str, Any]:
    rss_p95 = int(_p95([float(sample["rss_bytes"]) for sample in samples]))
    startup_p95 = round(_p95([float(sample["startup_ms"]) for sample in samples]), 3)
    failed: list[str] = []
    observed = {
        "controller-schema": controller_schema_bytes,
        "install-delta": install_delta_bytes,
        "rss-p95": rss_p95,
        "empty-databases": empty_databases_bytes,
        "action-growth": action_growth_bytes,
    }
    if len(samples) < 30:
        failed.append("sample-count")
    failed.extend(
        name for name, limit in RESOURCE_THRESHOLDS.items()
        if observed[name] > limit
    )
    return {
        "status": "passed" if not failed else "failed",
        "sample_count": len(samples),
        "startup_p95_ms": startup_p95,
        "rss_p95_bytes": rss_p95,
        "controller_schema_bytes": controller_schema_bytes,
        "install_delta_bytes": install_delta_bytes,
        "empty_databases_bytes": empty_databases_bytes,
        "action_growth_bytes": action_growth_bytes,
        "failed_thresholds": failed,
        "thresholds": RESOURCE_THRESHOLDS,
    }


def _wait_for_file(path: Path, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.01)
    raise TimeoutError(path.name)


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _process_observation(pid: int) -> tuple[int, float]:
    if os.name != "nt":
        status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
        rss_kib = int(next(
            line.split()[1] for line in status.splitlines() if line.startswith("VmRSS:")
        ))
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
        ticks = os.sysconf("SC_CLK_TCK")
        return rss_kib * 1024, (int(fields[13]) + int(fields[14])) / ticks
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), ctypes.sizeof(counters)
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
        return int(counters.WorkingSetSize), (kernel.value + user.value) / 10_000_000
    finally:
        kernel32.CloseHandle(handle)


def runtime_probe(
    *, codex_bin: Path, schema_root: Path, expected_version: str,
    expected_platform: str, dependency_root: Path, dependency_lock: Path,
    output: Path,
) -> dict[str, Any]:
    runtime = verify_runtime_selection(
        codex_bin, schema_root, expected_version=expected_version,
        expected_platform=expected_platform,
    )
    try:
        dbos_version = importlib.metadata.version("dbos")
    except importlib.metadata.PackageNotFoundError:
        dbos_version = "not-installed"
    expected_python = "3.13.5" if expected_platform == "windows-x86_64" else "3.12.3"
    checks = {
        "runtime_pin": bool(runtime["valid"]),
        "python": platform.python_version() == expected_python,
        "dbos": dbos_version == "2.29.0",
        "dependency_root": dependency_root.resolve().is_dir(),
        "dependency_lock": dependency_lock.resolve().is_file(),
    }
    result = {
        "schema_version": "ds-lite.runtime-compatibility.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "platform": expected_platform,
        "python_version": platform.python_version(),
        "dbos_version": dbos_version,
        "codex_version": runtime["codex_binary_version"],
        "codex_binary_sha256": file_hash(codex_bin),
        "schema_manifest_sha256": runtime["schema"]["manifest_digest"],
        "schema_bundle_sha256": runtime["schema"]["observed_bundle_digest"],
        "dependency_lock_sha256": file_hash(dependency_lock),
        "dependency_bytes": directory_bytes(dependency_root),
        "release_allowed": False,
    }
    write_once(output, result)
    return result


def resource_probe(
    *, dependency_root: Path, output: Path, expected_platform: str,
    sample_count: int = 30,
) -> dict[str, Any]:
    if sample_count < 1:
        raise ValueError("sample count must be positive")
    output = output.resolve()
    runtime = output.parent / f"{output.stem}-runtime"
    runtime.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    paths = [str(dependency_root.resolve()), str(CONTROLLER_ROOT)]
    if environment.get("PYTHONPATH"):
        paths.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    samples: list[dict[str, Any]] = []
    code = (
        "import json,os,sys,time; import dbos,ds_lite_control; "
        "p=sys.argv[1]; f=open(p,'x',encoding='ascii'); "
        "json.dump({'pid':os.getpid()},f); f.write('\\n'); f.flush(); os.fsync(f.fileno()); "
        "f.close(); time.sleep(30)"
    )
    for index in range(sample_count):
        ready = runtime / f"ready-{index:03d}.json"
        started = time.perf_counter()
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(ready)], env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_file(ready)
            startup_ms = (time.perf_counter() - started) * 1000
            rss, cpu = _process_observation(process.pid)
            samples.append({
                "index": index, "startup_ms": round(startup_ms, 3),
                "rss_bytes": rss, "cpu_seconds": round(cpu, 6),
            })
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    domain = runtime / "control.sqlite3"
    runtime_db = runtime / "runtime.sqlite3"
    store = ControlStore(domain)
    store.connection.execute("PRAGMA wal_checkpoint(FULL)")
    store.close()
    bridge = DBOSBridge(runtime_db)
    bridge.close()
    empty_bytes = sum(
        path.stat().st_size for path in (domain, runtime_db) if path.is_file()
    )
    store = ControlStore(domain)
    try:
        for index in range(100):
            store.plan_action(f"phase5-resource-{index:03d}", "turn")
        store.connection.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        store.close()
    after_bytes = sum(
        path.stat().st_size for path in runtime.glob("*.sqlite3*") if path.is_file()
    )
    controller_schema_bytes = directory_bytes(CONTROLLER_ROOT) + directory_bytes(SCHEMA_ROOT)
    install_delta = dependency_root.resolve()
    package_bytes = directory_bytes(ROOT / "plugins" / "deepscientist-lite-core")
    evaluation = evaluate_resource_samples(
        samples, controller_schema_bytes=controller_schema_bytes,
        install_delta_bytes=directory_bytes(install_delta) + package_bytes,
        empty_databases_bytes=empty_bytes,
        action_growth_bytes=max(0, after_bytes - empty_bytes),
    )
    result = {
        "schema_version": "ds-lite.phase5-resource.v1",
        **evaluation,
        "platform": expected_platform,
        "python_version": platform.python_version(),
        "samples": samples,
        "raw_samples_persisted": True,
        "release_allowed": False,
    }
    write_once(output, result)
    return result


def aggregate_real_host_chaos(
    controller_paths: list[Path], app_server_paths: list[Path], both_paths: list[Path],
    failed_paths: list[Path], *, output: Path,
) -> dict[str, Any]:
    groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for name, paths in (
        ("controller", controller_paths), ("app-server", app_server_paths),
        ("controller-and-app-server", both_paths),
    ):
        groups[name] = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    failures = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in failed_paths]

    controller = [item for _, item in groups["controller"]]
    app_server = [item for _, item in groups["app-server"]]
    both = [item for _, item in groups["controller-and-app-server"]]
    identities = {
        name: [str(item.get("sample_id") or path.stem) for path, item in rows]
        for name, rows in groups.items()
    }
    checks = {
        "controller_ten_passed": len(controller) == 10 and all(item.get("status") == "passed" for item in controller),
        "app_server_ten_passed": len(app_server) == 10 and all(item.get("status") == "passed" for item in app_server),
        "both_ten_passed": len(both) == 10 and all(item.get("status") == "passed" for item in both),
        "unique_identities": all(len(set(values)) == 10 for values in identities.values()),
        "controller_response_loss_reconciled": all(
            item.get("checks", {}).get("response_loss_injected") is True
            and item.get("checks", {}).get("response_loss_reconciled") is True
            and item.get("turn_start_count") == 3
            for item in controller
        ),
        "app_server_no_redispatch": all(
            item.get("checks", {}).get("no_recovery_redispatch") is True
            and item.get("checks", {}).get("terminal_recovered") is True
            and item.get("checks", {}).get("workspace_unchanged") is True
            for item in app_server
        ),
        "both_no_redispatch": all(
            item.get("checks", {}).get("no_recovery_redispatch") is True
            and item.get("checks", {}).get("terminal_recovered") is True
            and item.get("checks", {}).get("workspace_unchanged") is True
            for item in both
        ),
        "negative_run_preserved": bool(failures) and all(
            item.get("status") != "passed" for _, item in failures
        ),
    }
    result = {
        "schema_version": "ds-lite.phase5-real-host-chaos.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "evidence_class": "real-codex-ambient-provider",
        "sample_counts": {name: len(rows) for name, rows in groups.items()},
        "receipt_sha256": {
            name: [file_hash(path) for path, _ in rows] for name, rows in groups.items()
        },
        "preserved_failure_receipts": [
            {"name": path.name, "sha256": file_hash(path)} for path, _ in failures
        ],
        "raw_model_output_persisted": False,
        "release_allowed": False,
    }
    write_once(output, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    runtime = sub.add_parser("runtime")
    runtime.add_argument("--codex-bin", required=True, type=Path)
    runtime.add_argument("--schema-root", required=True, type=Path)
    runtime.add_argument("--codex-version", required=True)
    runtime.add_argument("--platform", required=True)
    runtime.add_argument("--dependency-root", required=True, type=Path)
    runtime.add_argument("--dependency-lock", required=True, type=Path)
    runtime.add_argument("--output", required=True, type=Path)
    resource = sub.add_parser("resource")
    resource.add_argument("--dependency-root", required=True, type=Path)
    resource.add_argument("--platform", required=True)
    resource.add_argument("--samples", type=int, default=30)
    resource.add_argument("--output", required=True, type=Path)
    chaos = sub.add_parser("chaos")
    chaos.add_argument("--controller", action="append", type=Path, default=[])
    chaos.add_argument("--app-server", action="append", type=Path, default=[])
    chaos.add_argument("--both", action="append", type=Path, default=[])
    chaos.add_argument("--failed", action="append", type=Path, default=[])
    chaos.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "runtime":
        result = runtime_probe(
            codex_bin=args.codex_bin, schema_root=args.schema_root,
            expected_version=args.codex_version, expected_platform=args.platform,
            dependency_root=args.dependency_root, dependency_lock=args.dependency_lock,
            output=args.output,
        )
    elif args.command == "resource":
        result = resource_probe(
            dependency_root=args.dependency_root, output=args.output,
            expected_platform=args.platform, sample_count=args.samples,
        )
    else:
        result = aggregate_real_host_chaos(
            args.controller, args.app_server, args.both, args.failed, output=args.output,
        )
    print(json.dumps({"status": result["status"], "platform": result.get("platform", "not-applicable")}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
