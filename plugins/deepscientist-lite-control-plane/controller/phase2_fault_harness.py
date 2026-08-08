"""External-process K4-K7/K12 fault matrix; fake host evidence only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


CASES = ("K4", "K5", "K6", "K7", "K12")


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _child(case: str, root: Path, marker: Path, action_id: str) -> int:
    state: dict[str, Any] = {
        "action_id": action_id, "thread_id": "thread-1", "turn_id": "turn-1",
        "request_count": 0, "journal": [], "archive": "active",
    }
    if case == "K4":
        marker.write_text("before-pipe-write\n", encoding="ascii")
    elif case == "K5":
        state["request_count"] = 1
        state["journal"] = ["request-written"]
        state["host"] = "active"
        _write_once(root / "state.json", state)
        marker.write_text("response-lost\n", encoding="ascii")
    elif case == "K6":
        state["request_count"] = 1
        state["journal"] = ["turn-completed-notification", "response-late"]
        state["host"] = "terminal"
        _write_once(root / "state.json", state)
        marker.write_text("notification-first\n", encoding="ascii")
    elif case == "K7":
        state["request_count"] = 1
        state["journal"] = ["acknowledged"]
        state["host"] = "terminal"
        _write_once(root / "state.json", state)
        marker.write_text("ack-before-terminal\n", encoding="ascii")
    elif case == "K12":
        state["archive"] = "archived"
        state["journal"] = ["archive-pending"]
        _write_once(root / "state.json", state)
        marker.write_text("archive-pending\n", encoding="ascii")
    while True:
        time.sleep(1)


def _recover(case: str, root: Path, action_id: str) -> bool:
    state_path = root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "action_id": action_id, "request_count": 0, "journal": [], "host": "absent",
    }
    if case == "K4":
        if state["request_count"] != 0:
            return False
        state["request_count"] = 1
        state["host"] = "active"
    elif case == "K5":
        if state["request_count"] != 1 or state.get("host") not in {"active", "terminal"}:
            return False
    elif case == "K6":
        if state["request_count"] != 1 or state["journal"] != ["turn-completed-notification", "response-late"]:
            return False
        state["host"] = "terminal"
    elif case == "K7":
        if state["request_count"] != 1 or "acknowledged" not in state["journal"]:
            return False
        state["host"] = "terminal"
    elif case == "K12":
        if state.get("archive") != "archived":
            return False
        state["archive_reconciled"] = True
    _write_once(root / "recovered.json", state)
    return True


def _trial(case: str, root: Path, action_id: str, timeout: float = 10.0) -> bool:
    root.mkdir(parents=True, exist_ok=False)
    marker = root / "barrier.marker"
    command = [sys.executable, str(Path(__file__).resolve()), "--child", case,
               "--root", str(root), "--marker", str(marker), "--action-id", action_id]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    try:
        while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.005)
        observed = marker.exists()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        return observed and _recover(case, root, action_id)
    finally:
        if process.poll() is None:
            process.kill()


def run_matrix(workdir: Path, output: Path, *, seed: int, trials: int) -> dict[str, Any]:
    if output.exists() or workdir.exists():
        raise FileExistsError("phase2 evidence paths must be new")
    if trials <= 0:
        raise ValueError("trials must be positive")
    workdir.mkdir(parents=True, exist_ok=False)
    randomizer = random.Random(seed)
    cases: dict[str, Any] = {}
    for case in CASES:
        passed = 0
        identities = []
        for trial in range(trials):
            action_id = f"phase2-{case.lower()}-{randomizer.randrange(2**63):016x}"
            identities.append(action_id)
            if _trial(case, workdir / case.lower() / f"trial-{trial:03d}", action_id):
                passed += 1
        cases[case] = {
            "passed": passed, "failed": trials - passed, "all_passed": passed == trials,
            "identity_digest": hashlib.sha256("".join(identities).encode()).hexdigest(),
            "evidence_class": "fake-host-external-process",
        }
    result = {
        "schema_version": "ds-lite.phase2-fault-matrix.v1", "seed": seed, "trials": trials,
        "cases": cases, "external_process_termination": True,
        "evidence_class": "fake-host-external-process", "release_allowed": False,
        "status": "passed" if all(case["all_passed"] for case in cases.values()) else "blocked",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_once(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--child", choices=CASES)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--action-id")
    args = parser.parse_args()
    if args.child:
        return _child(args.child, args.root.resolve(), args.marker.resolve(), args.action_id)
    if args.workdir is None or args.output is None:
        parser.error("--workdir and --output are required outside child mode")
    result = run_matrix(args.workdir.resolve(), args.output.resolve(), seed=args.seed, trials=args.trials)
    print(json.dumps({"status": result["status"], "trials": result["trials"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
