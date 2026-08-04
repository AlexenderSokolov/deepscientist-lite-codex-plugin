from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import os
import platform
import re
import subprocess
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.backup import backup_control_plane, restore_control_plane, verify_backup
from ds_lite_control.broker import DurableWireJournal
from ds_lite_control.scheduler import DagScheduler
from ds_lite_control.store import ControlStore
from ds_lite_control.supervisor import RepoSupervisor


PHASE2_DECISION_SHA256 = "9b867e230f4edcafd35750fc0b0fd115da642b8cb86ae649aa83b4e2ed66eb4e"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_test_log(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8", errors="replace")


def test_log_passed(text: str) -> bool:
    return bool(re.search(r"(?m)^OK\s*$", text)) and not bool(
        re.search(r"(?m)^(?:FAILED|ERROR)\b", text)
    )


def write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _wait(path: Path, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                pass
        time.sleep(0.05)
    raise TimeoutError(path.name)


def supervised_probe(project: Path, runtime: Path, output: Path) -> dict[str, Any]:
    project = project.resolve()
    runtime = runtime.resolve()
    output = output.resolve()
    if project.exists() or runtime.exists() or output.exists():
        raise FileExistsError("supervised probe paths must be new")
    state = project / ".ds-lite"
    state.mkdir(parents=True, exist_ok=False)
    runtime.mkdir(parents=True, exist_ok=False)
    job_id = "phase3-supervised"
    store = ControlStore(state / "control.sqlite3")
    scheduler = DagScheduler(store, FailureClassifier(seed=20260731))
    scheduler.register_job(job_id, [
        {"id": f"{job_id}-gate-a", "type": "experiment", "priority": 2},
        {"id": f"{job_id}-gate-b", "type": "analysis", "priority": 1},
    ], [])
    command = [
        sys.executable, str(ROOT / "teaching" / "controller_phase3_supervised_worker.py"),
        "--project", str(project), "--runtime", str(runtime), "--job-id", job_id,
        "--owner-id", "phase3-supervised-owner",
    ]
    supervisor = RepoSupervisor(
        store, runtime_root=state / "supervisor", supervisor_id="phase3-supervisor",
        owner_id="phase3-supervised-owner", worker_command=command,
    )
    try:
        first = supervisor.tick()
        barrier = _wait(runtime / "crash-barrier.json", 20)
        if supervisor.process is None:
            raise RuntimeError("controller process missing")
        supervisor.process.terminate()
        supervisor.process.wait(timeout=10)
        time.sleep(2.2)
        second = supervisor.tick()
        completed = _wait(runtime / "completed.json", 20)
        status = store.project_job_status(job_id, supervisor_id="phase3-supervisor")
        supervisor.request_stop()
        stopped = supervisor.tick()
        all_terminal = all(gate["state"] == "terminal" for gate in status["gates"])
        job_terminal = status["job_state"] == "terminal"
        same_action = barrier["interrupted_action_id"] == completed["recovered_action_id"]
        sqlite3.connect(state / "runtime.sqlite3").close()
        receipts = state / "receipts"
        receipts.mkdir()
        write_once(receipts / "terminal.json", {
            "job_id": job_id, "status": "completed", "release_allowed": False,
        })
        journal = DurableWireJournal(state / "protocol-journal.jsonl")
        journal.append("inbound", {"method": "phase3/probe", "params": {}})
        write_once(state / "broker-metadata.json", {
            "schema_version": "ds-lite.fault-broker-metadata.v1",
            "broker_id": "phase3-managed-probe", "app_server_pid": 0,
        })
        backup = runtime / "backup"
        restore = runtime / "restore"
        manifest = backup_control_plane(
            state, backup, require_protocol=True, require_broker=True,
            require_supervisor=True,
        )
        restored = restore_control_plane(backup, restore)
        restored_store = ControlStore(restore / "control.sqlite3")
        try:
            restored_terminal = all(
                gate["state"] == "terminal"
                for gate in restored_store.project_job_status(job_id)["gates"]
            )
        finally:
            restored_store.close()
        backup_valid = bool(
            verify_backup(backup)["valid"] and restored["valid"] and restored_terminal
            and manifest["schema_version"] == "ds-lite.control-backup.v4"
        )
        journal_valid = bool(journal.verify()["valid"])
        result = {
            "schema_version": "ds-lite.phase3-supervised-probe.v1",
            "status": "passed" if (
                all_terminal and job_terminal and same_action and second["generation"] == 2
                and backup_valid and journal_valid
            ) else "failed",
            "supervisor_generations": second["generation"],
            "controller_pids": [first["controller_pid"], second["controller_pid"]],
            "same_action_recovered": same_action,
            "fence_epoch_advanced": int(completed["fence_epoch"]) > int(barrier["fence_epoch"]),
            "all_gates_terminal": all_terminal,
            "job_terminal": job_terminal,
            "peak_concurrency": int(barrier["peak_concurrency"]),
            "supervisor_stopped": stopped["state"] == "stopped",
            "backup_restore_valid": backup_valid,
            "broker_journal_valid": journal_valid,
            "evidence_class": "sqlite-domain-external-controller-processes",
            "release_allowed": False,
        }
        write_once(output, result)
        return result
    finally:
        if supervisor.process is not None and supervisor.process.poll() is None:
            supervisor.process.terminate()
            supervisor.process.wait(timeout=10)
        store.close()


def resource_probe(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    runtime = output.parent / f"{output.stem}-runtime"
    runtime.mkdir(parents=True, exist_ok=False)
    ready = runtime / "ready.json"
    code = (
        "import json,os,sys,time; import ds_lite_control; "
        "p=sys.argv[1]; f=open(p,'x',encoding='utf-8'); "
        "json.dump({'pid':os.getpid()},f); f.write('\\n'); f.flush(); os.fsync(f.fileno()); f.close(); "
        "time.sleep(30)"
    )
    env = {**os.environ, "PYTHONPATH": str(CONTROLLER_ROOT) + (
        os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""
    )}
    started = time.perf_counter()
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(ready)], env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait(ready, 15)
        startup_ms = (time.perf_counter() - started) * 1000
        def observe_process() -> dict[str, float]:
            if os.name == "nt":
                script = (
                    f"$p=Get-Process -Id {process.pid}; "
                    "[pscustomobject]@{rss=[int64]$p.WorkingSet64;cpu=[double]$p.CPU} "
                    "| ConvertTo-Json -Compress"
                )
                completed = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", script],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    check=True, timeout=30,
                )
                return json.loads(completed.stdout)
            proc_status = Path(f"/proc/{process.pid}/status")
            proc_stat = Path(f"/proc/{process.pid}/stat")
            if proc_status.is_file() and proc_stat.is_file():
                rss = 0
                for line in proc_status.read_text(encoding="ascii", errors="replace").splitlines():
                    if line.startswith("VmRSS:"):
                        rss = int(line.split()[1]) * 1024
                        break
                fields = proc_stat.read_text(encoding="ascii", errors="replace").split()
                ticks = int(fields[13]) + int(fields[14])
                return {"rss": rss, "cpu": ticks / os.sysconf("SC_CLK_TCK")}
            completed = subprocess.run(
                ["ps", "-o", "rss=,time=", "-p", str(process.pid)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=True, timeout=10,
            )
            parts = completed.stdout.strip().split()
            if len(parts) < 2:
                raise RuntimeError("process-resource-observation-unavailable")
            hours, minutes, seconds = parts[1].split(":")
            return {"rss": int(parts[0]) * 1024, "cpu": int(hours) * 3600 + int(minutes) * 60 + float(seconds)}

        before = observe_process()
        peak_rss = int(before["rss"])
        time.sleep(0.5)
        after = observe_process()
        peak_rss = max(peak_rss, int(after["rss"]))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    database = runtime / "control.sqlite3"
    store = ControlStore(database)
    try:
        DagScheduler(store, FailureClassifier(seed=20260731)).register_job(
            "resource-job", [
                {"id": "resource-gate-a", "type": "analysis"},
                {"id": "resource-gate-b", "type": "experiment"},
            ], [],
        )
        store.connection.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        store.close()
    controller_bytes = sum(
        path.stat().st_size for path in CONTROLLER_ROOT.rglob("*.py") if path.is_file()
    )
    result = {
        "schema_version": "ds-lite.phase3-resource.v1",
        "status": "passed",
        "platform": platform.system().lower(),
        "python": platform.python_version(),
        "startup_ms": round(startup_ms, 3),
        "peak_rss_bytes": int(peak_rss),
        "cpu_seconds_observed": round(max(0.0, float(after["cpu"]) - float(before["cpu"])), 6),
        "control_data_growth_bytes": database.stat().st_size,
        "controller_source_bytes": controller_bytes,
        "other_platforms_observed": [],
        "release_allowed": False,
    }
    write_once(output, result)
    return result


def decide(
    *, previous: Path, fault: Path, real_smoke: Path, supervised: Path,
    resource: Path, tests: Path, support_tests: Path, core: Path, output: Path,
) -> dict[str, Any]:
    inputs = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in (
            ("previous", previous), ("fault", fault), ("real_smoke", real_smoke),
            ("supervised", supervised), ("resource", resource), ("core", core),
        )
    }
    tests_text = read_test_log(tests)
    support_text = read_test_log(support_tests)
    fault_data = inputs["fault"]
    real = inputs["real_smoke"]
    supervised_data = inputs["supervised"]
    checks = {
        "phase2_receipt_unchanged": file_hash(previous) == PHASE2_DECISION_SHA256,
        "k10_k11_100_trials": (
            fault_data.get("status") == "passed" and fault_data.get("trials") == 100
            and all(fault_data.get("cases", {}).get(case, {}).get("all_passed") is True
                    for case in ("K10", "K11"))
        ),
        "real_multigate": (
            real.get("status") == "passed"
            and real.get("evidence_class") == "real-app-server-external-controller-processes"
            and all(real.get("checks", {}).get(name) is True for name in (
                "exactly_two_turn_starts", "single_tool_side_effect",
                "ttl_owner_takeover", "domain_terminal",
            ))
        ),
        "real_schema_pinned": (
            isinstance(real.get("codex_version"), str)
            and bool(real.get("codex_version"))
            and isinstance(real.get("schema_sha256"), str)
            and len(real.get("schema_sha256")) == 64
            and isinstance(real.get("model_catalog_sha256"), str)
            and len(real.get("model_catalog_sha256")) == 64
        ),
        "supervised_recovery": (
            supervised_data.get("status") == "passed"
            and all(supervised_data.get(name) is True for name in (
                "same_action_recovered", "all_gates_terminal", "job_terminal",
                "backup_restore_valid", "broker_journal_valid",
            ))
        ),
        "windows_resources": inputs["resource"].get("status") == "passed"
            and inputs["resource"].get("platform") == "windows",
        "phase_tests": all(test_log_passed(text) for text in (tests_text, support_text)),
        "core_validation": inputs["core"].get("status") == "passed",
    }
    go = all(checks.values())
    decision = "go" if go else "pending-external-observation"
    result = {
        "schema_version": "ds-lite.phase3-decision.v2",
        "phase3_decision": decision,
        "phase4_goal_allowed": go,
        "release_allowed": False,
        "checks": checks,
        "versions": {
            "python": platform.python_version(), "dbos": "2.29.0",
            "codex_cli": real.get("codex_version"),
        },
        "fault_seed": fault_data.get("seed"),
        "fault_trials": fault_data.get("trials"),
        "evidence_classes": {
            "fault": "external-process-sqlite+real-dbos",
            "real_codex": real.get("evidence_class"),
            "supervised": supervised_data.get("evidence_class"),
        },
        "identities": {
            "controller_pids": real.get("controller_pids"),
            "supervisor_controller_pids": supervised_data.get("controller_pids"),
        },
        "digests": {
            "codex_schema_sha256": real.get("schema_sha256"),
            "codex_model_catalog_sha256": real.get("model_catalog_sha256"),
            "phase2_decision_sha256": file_hash(previous),
        },
        "artifacts": {
            name: {"name": path.name, "sha256": file_hash(path)}
            for name, path in (
                ("previous", previous), ("fault", fault), ("real_smoke", real_smoke),
                ("supervised", supervised), ("resource", resource),
                ("tests", tests), ("support_tests", support_tests), ("core", core),
            )
        },
        "unresolved_risks": [
            "release_allowed remains false",
            "Phase 4 independent reviewer/release aggregate is not implemented",
            "non-Windows host acceptance remains Phase 5 work",
        ],
    }
    write_once(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    supervised = sub.add_parser("supervised")
    supervised.add_argument("--project", type=Path, required=True)
    supervised.add_argument("--runtime", type=Path, required=True)
    supervised.add_argument("--output", type=Path, required=True)
    resource = sub.add_parser("resource")
    resource.add_argument("--output", type=Path, required=True)
    decision = sub.add_parser("decision")
    for name in ("previous", "fault", "real-smoke", "supervised", "resource", "tests", "support-tests", "core", "output"):
        decision.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "supervised":
        result = supervised_probe(args.project, args.runtime, args.output)
    elif args.command == "resource":
        result = resource_probe(args.output)
    else:
        result = decide(
            previous=args.previous, fault=args.fault, real_smoke=args.real_smoke,
            supervised=args.supervised, resource=args.resource, tests=args.tests,
            support_tests=args.support_tests, core=args.core, output=args.output,
        )
    status = result.get("status", result.get("phase3_decision"))
    print(json.dumps({"status": status}, sort_keys=True))
    return 0 if status in {"passed", "go"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
