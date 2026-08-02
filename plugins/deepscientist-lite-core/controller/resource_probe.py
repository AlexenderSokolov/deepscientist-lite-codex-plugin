"""Measure the Phase 0.5 local dependency and control-store footprint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

from ds_lite_control.domain import ControlStore


def directory_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def write_once(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    dependency_root = args.dependency_root.resolve()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(dependency_root)
    started = time.perf_counter()
    process = subprocess.Popen(
        [sys.executable, "-c", "import dbos, time; time.sleep(1.5)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
    )
    inspected = psutil.Process(process.pid)
    time.sleep(0.5)
    rss_bytes = inspected.memory_info().rss
    cpu_times = inspected.cpu_times()
    returncode = process.wait(timeout=15)
    startup_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    with tempfile.TemporaryDirectory(prefix="ds-lite-control-resource-") as directory:
        db_path = Path(directory) / "control.sqlite"
        baseline = db_path.stat().st_size if db_path.exists() else 0
        store = ControlStore(db_path)
        for index in range(100):
            store.plan_action(f"action-{index}", "turn")
        store.close()
        final_bytes = db_path.stat().st_size
    payload = {
        "schema_version": "ds-lite.control-plane-resource-probe.v1",
        "status": "observed" if returncode == 0 else "blocked",
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "dbos_install_bytes": directory_bytes(dependency_root),
        "dbos_import_elapsed_ms": startup_elapsed_ms,
        "dbos_import_rss_bytes": rss_bytes,
        "dbos_import_cpu_seconds": round(cpu_times.user + cpu_times.system, 6),
        "control_sqlite_baseline_bytes": baseline,
        "control_sqlite_after_100_actions_bytes": final_bytes,
        "control_sqlite_growth_bytes": final_bytes - baseline,
        "other_platforms": "not-observed",
        "raw_process_output_persisted": False,
    }
    write_once(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "platform": payload["platform"]}))
    return 0 if returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
