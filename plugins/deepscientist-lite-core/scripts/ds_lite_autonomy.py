#!/usr/bin/env python3
"""Foreground, bounded automation controller for DS Lite release experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from ds_lite_recovery import classify_failure, retry_schedule


CONTRACT_SCHEMA = "ds-lite.autonomy-contract.v1"
SUMMARY_SCHEMA = "ds-lite.autonomy-summary.v1"
PROGRESS_SCHEMA = "ds-lite.progress-report.v1"
ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,79}$")
TRANSIENT_FAILURES = {"network", "rate-limit", "timeout", "provider-unavailable", "external-transient"}
USER_ACTION_FAILURES = {"auth", "authorization", "duplicate-risk", "hook-trust", "user-action", "provider-user-action"}
DEFAULT_CONTINUITY = {
    "quiet_receipt_polls": 3,
    "quiet_poll_seconds": 2,
    "retry_delays_seconds": [2, 4, 8, 16, 32],
}
HEARTBEAT_INTERVAL_SECONDS = 60


class AutonomyError(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rel(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AutonomyError(f"{field} must be a non-empty project-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AutonomyError(f"{field} must be a non-empty project-relative POSIX path")
    return value


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _resolve(root: Path, ref: str, field: str) -> Path:
    value = _rel(ref, field)
    result = root.joinpath(*PurePosixPath(value).parts).resolve(strict=False)
    if not _within(result, root):
        raise AutonomyError(f"{field} escapes root")
    return result


def _digest_goals(goals: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(goals), separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_contract(value: Any) -> dict[str, Any]:
    required = {"schema_version", "autonomy_id", "status", "goals", "gates", "budget", "authorization", "release"}
    allowed = required | {"continuity"}
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - allowed:
        raise AutonomyError("autonomy contract fields do not match v1")
    if value["schema_version"] != CONTRACT_SCHEMA or not ID_RE.fullmatch(str(value["autonomy_id"])):
        raise AutonomyError("autonomy contract identity is invalid")
    if value["status"] not in {"prepared", "running", "completed", "blocked"}:
        raise AutonomyError("autonomy contract status is invalid")
    goals = value["goals"]
    if not isinstance(goals, list) or not goals or not all(isinstance(goal, str) and ID_RE.fullmatch(goal) for goal in goals):
        raise AutonomyError("goals must be a non-empty list of identifiers")
    if len(set(goals)) != len(goals):
        raise AutonomyError("goals must be unique")
    budget = value["budget"]
    if not isinstance(budget, dict) or set(budget) != {"max_attempts_per_gate", "max_seconds"}:
        raise AutonomyError("budget fields are invalid")
    if not isinstance(budget["max_attempts_per_gate"], int) or not 3 <= budget["max_attempts_per_gate"] <= 6 or not isinstance(budget["max_seconds"], int) or not 1 <= budget["max_seconds"] <= 86400:
        raise AutonomyError("budget must use three to six attempts and a bounded duration")
    continuity = value.get("continuity", DEFAULT_CONTINUITY)
    if not isinstance(continuity, dict) or set(continuity) != set(DEFAULT_CONTINUITY):
        raise AutonomyError("continuity fields are invalid")
    if not isinstance(continuity["quiet_receipt_polls"], int) or not 0 <= continuity["quiet_receipt_polls"] <= 12:
        raise AutonomyError("continuity.quiet_receipt_polls is invalid")
    if not isinstance(continuity["quiet_poll_seconds"], int) or not 0 <= continuity["quiet_poll_seconds"] <= 60:
        raise AutonomyError("continuity.quiet_poll_seconds is invalid")
    delays = continuity["retry_delays_seconds"]
    if not isinstance(delays, list) or len(delays) < budget["max_attempts_per_gate"] - 1 or not all(isinstance(item, int) and 0 <= item <= 300 for item in delays):
        raise AutonomyError("continuity.retry_delays_seconds is invalid")
    authorization = value["authorization"]
    if not isinstance(authorization, dict) or set(authorization) != {"status", "authority", "ref"}:
        raise AutonomyError("authorization fields are invalid")
    if authorization["status"] != "approved" or not ID_RE.fullmatch(str(authorization["authority"])):
        raise AutonomyError("autonomy execution requires approved authorization")
    _rel(authorization["ref"], "authorization.ref")
    gates = value["gates"]
    if not isinstance(gates, list) or not gates:
        raise AutonomyError("gates must be a non-empty list")
    ids: set[str] = set()
    for index, gate in enumerate(gates):
        required_gate = {"id", "depends_on", "command", "receipt_ref", "retry_class"}
        optional_gate = {"continuation_command", "continuation_receipt_ref"}
        if not isinstance(gate, dict) or not required_gate.issubset(gate) or set(gate) - required_gate - optional_gate or not ID_RE.fullmatch(str(gate.get("id", ""))):
            raise AutonomyError(f"gates[{index}] is invalid")
        if gate["id"] in ids:
            raise AutonomyError("gate ids must be unique")
        ids.add(gate["id"])
        if not isinstance(gate["depends_on"], list) or not all(isinstance(item, str) and ID_RE.fullmatch(item) for item in gate["depends_on"]):
            raise AutonomyError(f"gates[{index}].depends_on is invalid")
        if not isinstance(gate["command"], list) or not gate["command"] or not all(isinstance(item, str) and item for item in gate["command"]):
            raise AutonomyError(f"gates[{index}].command is invalid")
        _rel(gate["receipt_ref"], f"gates[{index}].receipt_ref")
        if gate["retry_class"] not in {"none", "transient"}:
            raise AutonomyError(f"gates[{index}].retry_class is invalid")
        continuation_fields = {"continuation_command", "continuation_receipt_ref"}
        if continuation_fields & set(gate) and not continuation_fields.issubset(gate):
            raise AutonomyError(f"gates[{index}] continuation fields must be supplied together")
        if continuation_fields.issubset(gate):
            if not isinstance(gate["continuation_command"], list) or not gate["continuation_command"] or not all(isinstance(item, str) and item for item in gate["continuation_command"]):
                raise AutonomyError(f"gates[{index}].continuation_command is invalid")
            _rel(gate["continuation_receipt_ref"], f"gates[{index}].continuation_receipt_ref")
    if any(dep not in ids for gate in gates for dep in gate["depends_on"]):
        raise AutonomyError("gate dependency is unknown")
    release = value["release"]
    if not isinstance(release, dict) or set(release) != {"authorized", "required_gates"} or release["authorized"] is not True:
        raise AutonomyError("release authorization is invalid")
    if sorted(release["required_gates"]) != sorted(ids):
        raise AutonomyError("release must require every declared gate")
    normalized = dict(value)
    normalized["continuity"] = continuity
    return normalized


def _load_receipt(root: Path, ref: str) -> tuple[str, str]:
    path = _resolve(root, ref, "receipt_ref")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "not-observed", "receipt-missing"
    if not isinstance(payload, dict):
        return "not-observed", "receipt-invalid"
    return str(payload.get("status", "not-observed")), str(payload.get("failure_layer", "none"))


def _recovery_for_receipt(root: Path, ref: str, failure_layer: str, attempt: int) -> dict[str, Any]:
    try:
        payload = json.loads(_resolve(root, ref, "receipt_ref").read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError, AutonomyError):
        payload = {}
    recovery = payload.get("recovery") if isinstance(payload, dict) else None
    if isinstance(recovery, dict) and isinstance(recovery.get("recovery_class"), str):
        return dict(recovery)
    result = classify_failure(failure_layer, http_status=payload.get("http_status") if isinstance(payload, dict) else None)
    return {**result, **retry_schedule(attempt, retry_after_seconds=payload.get("retry_after_seconds") if isinstance(payload, dict) else None)}


def _write_fresh(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise AutonomyError(f"refusing to overwrite autonomy output: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _latest_summary_path(output: Path) -> Path | None:
    candidates = []
    initial = output / "summary.json"
    if initial.is_file():
        candidates.append(initial)
    candidates.extend(sorted(output.glob("summary-resume-*.json")))
    return candidates[-1] if candidates else None


def _progress(contract: dict[str, Any], index: int, gate_id: str, status: str, completed: list[str], blocked: list[str], next_action: str, *, failure_layer: str, attempts: int, receipt_ref: str, quiet_polls: int, automatic_retry_observed: bool = False) -> dict[str, Any]:
    return {
        "schema_version": PROGRESS_SCHEMA,
        "autonomy_id": contract["autonomy_id"],
        "sequence": index,
        "recorded_at": _stamp(),
        "active_gate": gate_id,
        "status": status,
        "failure_layer": failure_layer,
        "evidence_ref": receipt_ref,
        "attempts": attempts,
        "automatic_retry_observed": automatic_retry_observed,
        "next_automatic_action": next_action,
        "completed_gates": sorted(completed),
        "blocked_gates": sorted(blocked),
        "next_action": next_action,
        "explanation": {
            "why": "Advance the approved project gate DAG without abandoning independent ready gates.",
            "what_happened": f"Gate {gate_id} ended as {status} after {attempts} attempt(s).",
            "evidence_ref": receipt_ref,
            "failure_layer": failure_layer,
            "quiet_receipt_polls": quiet_polls,
        },
        "report_due_seconds": 60,
        "raw_output_persisted": False,
    }


def _heartbeat_payload(*, contract: dict[str, Any], completed: list[str],
                       running: list[str], blocked: list[str],
                       evidence_refs: list[str], next_action: str) -> dict[str, Any]:
    return {
        "schema_version": "ds-lite.autonomy-heartbeat.v1",
        "autonomy_id": contract["autonomy_id"],
        "observed_at": _stamp(),
        "report_due_seconds": HEARTBEAT_INTERVAL_SECONDS,
        "completed_gates": sorted(set(completed)),
        "running_gates": sorted(set(running)),
        "blocked_gates": sorted(set(blocked)),
        "frozen_goals": list(contract["goals"]),
        "evidence_refs": sorted(set(evidence_refs)),
        "next_automatic_action": next_action,
        "raw_output_persisted": False,
    }


def _append_heartbeat(output: Path, payload: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "heartbeat.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


class _Heartbeat:
    """Persist redacted status while a gate subprocess is running."""

    def __init__(self, output: Path, contract: dict[str, Any], *, gate_id: str,
                 completed: list[str], blocked: list[str], evidence_refs: list[str]) -> None:
        self.output = output
        self.contract = contract
        self.gate_id = gate_id
        self.completed = list(completed)
        self.blocked = list(blocked)
        self.evidence_refs = list(evidence_refs)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ds-lite-autonomy-heartbeat", daemon=True)

    def start(self) -> None:
        self._write()
        self._thread.start()

    def stop(self, *, next_action: str) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        _append_heartbeat(
            self.output,
            _heartbeat_payload(
                contract=self.contract,
                completed=self.completed,
                running=[],
                blocked=self.blocked,
                evidence_refs=self.evidence_refs,
                next_action=next_action,
            ),
        )

    def _write(self) -> None:
        _append_heartbeat(
            self.output,
            _heartbeat_payload(
                contract=self.contract,
                completed=self.completed,
                running=[self.gate_id],
                blocked=self.blocked,
                evidence_refs=self.evidence_refs,
                next_action=f"run-gate:{self.gate_id}",
            ),
        )

    def _run(self) -> None:
        while not self._stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            self._write()


def _run_gate_with_heartbeat(root: Path, output: Path, contract: dict[str, Any],
                             gate: dict[str, Any], attempt: int, timeout: int,
                             continuity: dict[str, Any], *, completed: list[str],
                             blocked: list[str], evidence_refs: list[str],
                             next_action: str, continuation: int = 0) -> tuple[str, str, int | None, str, int]:
    heartbeat = _Heartbeat(
        output,
        contract,
        gate_id=str(gate["id"]),
        completed=completed,
        blocked=blocked,
        evidence_refs=evidence_refs,
    )
    heartbeat.start()
    try:
        return _run_gate(root, gate, attempt, timeout, continuity, continuation=continuation)
    finally:
        heartbeat.stop(next_action=next_action)


def _run_gate(root: Path, gate: dict[str, Any], attempt: int, timeout: int, continuity: dict[str, Any], *, continuation: int = 0) -> tuple[str, str, int | None, str, int]:
    command_template = gate["continuation_command"] if continuation else gate["command"]
    receipt_template = gate["continuation_receipt_ref"] if continuation else gate["receipt_ref"]
    command = [item.replace("{attempt}", str(attempt)).replace("{continuation}", str(continuation)) for item in command_template]
    receipt_ref = receipt_template.replace("{attempt}", str(attempt)).replace("{continuation}", str(continuation))
    try:
        result = subprocess.run(command, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
        code = result.returncode
        diagnostic = (result.stdout or "") + "\n" + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return "blocked", "timeout", None, receipt_ref, 0
    except OSError:
        return "blocked", "execution", None, receipt_ref, 0
    status, failure = _load_receipt(root, receipt_ref)
    quiet_polls = 0
    while status == "not-observed" and quiet_polls < continuity["quiet_receipt_polls"]:
        quiet_polls += 1
        if continuity["quiet_poll_seconds"]:
            time.sleep(continuity["quiet_poll_seconds"])
        status, failure = _load_receipt(root, receipt_ref)
    if code == 0 and status == "passed":
        return "passed", "none", code, receipt_ref, quiet_polls
    return status if status != "passed" else "blocked", failure if failure != "none" else "execution", code, receipt_ref, quiet_polls


def _resume_state(output: Path, contract: dict[str, Any], gates: dict[str, dict[str, Any]]) -> tuple[list[str], list[str], dict[str, dict[str, Any]], int]:
    def classify(gate_id: str, status: str, failure_layer: str) -> str:
        if status == "passed":
            return "completed"
        if status == "awaiting_user_action":
            return "blocked"
        gate = gates[gate_id]
        recovery = classify_failure(failure_layer)
        if gate.get("retry_class") == "transient" and (failure_layer in TRANSIENT_FAILURES or recovery["recovery_class"] in {"retryable", "diagnose-once"}):
            return "pending"
        return "blocked"

    summary_path = _latest_summary_path(output)
    if summary_path is not None:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("autonomy_id") != contract["autonomy_id"]:
            raise AutonomyError("autonomy summary identity does not match contract")
        results = dict(summary.get("gates", {}))
        completed = list(summary.get("completed_gates", []))
        blocked = list(summary.get("awaiting_user_action_gates", []))
        for gate_id, value in results.items():
            if gate_id in completed or gate_id in blocked:
                continue
            if classify(gate_id, str(value.get("status", "blocked")), str(value.get("failure_layer", ""))) == "blocked":
                blocked.append(gate_id)
        return completed, blocked, results, len(list(output.glob("progress-*.json")))
    completed: list[str] = []
    blocked: list[str] = []
    results: dict[str, dict[str, Any]] = {}
    progress = sorted(output.glob("progress-*.json"))
    for path in progress:
        payload = json.loads(path.read_text(encoding="utf-8"))
        gate_id = payload.get("active_gate")
        if payload.get("autonomy_id") != contract["autonomy_id"] or gate_id not in gates:
            raise AutonomyError("autonomy progress identity does not match contract")
        payload_status = str(payload.get("status", "blocked"))
        failure_layer = payload.get("explanation", {}).get("failure_layer", "resume-reconstructed")
        classification = classify(gate_id, payload_status, str(failure_layer))
        if classification == "completed":
            completed.append(gate_id)
        elif classification == "blocked":
            blocked.append(gate_id)
        results[gate_id] = {"status": payload_status, "failure_layer": failure_layer, "attempts": 0, "automatic_retry_observed": False, "receipt_ref": payload.get("explanation", {}).get("evidence_ref", "")}
    return sorted(set(completed)), sorted(set(blocked)), results, len(progress)


def run(root: Path, contract_path: Path | dict[str, Any], output: Path, *, resume: bool = False) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if isinstance(contract_path, dict):
        contract_payload = contract_path
    else:
        contract_payload = json.loads(contract_path.read_text(encoding="utf-8"))
    contract = validate_contract(contract_payload)
    if not _resolve(root, contract["authorization"]["ref"], "authorization.ref").is_file():
        raise AutonomyError("authorization receipt is missing")
    gates = {gate["id"]: gate for gate in contract["gates"]}
    if output.exists():
        # A v2 adapter may pre-create an empty run directory before handing
        # execution to the legacy bounded engine; only non-empty output is a
        # replay/overwrite hazard.
        if not resume and any(output.iterdir()):
            raise AutonomyError("autonomy output already exists")
        if resume:
            completed, blocked, gate_results, progress_index = _resume_state(output, contract, gates)
            latest_summary = _latest_summary_path(output)
            if latest_summary is not None:
                latest_payload = json.loads(latest_summary.read_text(encoding="utf-8"))
                if latest_payload.get("status") == "completed":
                    return latest_payload
        else:
            completed, blocked, gate_results, progress_index = [], [], {}, 0
    else:
        output.mkdir(parents=True)
        completed, blocked, gate_results, progress_index = [], [], {}, 0
    started = time.monotonic()
    pending = set(gates) - set(completed) - set(blocked)
    while pending:
        ready = sorted(gate_id for gate_id in pending if set(gates[gate_id]["depends_on"]).issubset(completed))
        if not ready:
            for dependency_blocked in sorted(pending):
                blocked.append(dependency_blocked)
                gate = gates[dependency_blocked]
                progress_index += 1
                dependency_receipt = str(gate["receipt_ref"]).replace("{attempt}", "0").replace("{continuation}", "0")
                _write_fresh(
                    output / f"progress-{progress_index:03d}.json",
                    _progress(
                        contract,
                        progress_index,
                        dependency_blocked,
                        "blocked",
                        completed,
                        blocked,
                        "awaiting-dependency-resolution",
                        failure_layer="dependency-blocked",
                        attempts=0,
                        receipt_ref=dependency_receipt,
                        quiet_polls=0,
                    ),
                )
                gate_results[dependency_blocked] = {
                    "status": "blocked",
                    "failure_layer": "dependency-blocked",
                    "attempts": 0,
                    "automatic_retry_observed": False,
                    "evidence_ref": dependency_receipt,
                    "receipt_ref": dependency_receipt,
                    "next_automatic_action": "awaiting-dependency-resolution",
                }
            break
        gate_id = ready[0]
        gate = gates[gate_id]
        pending.remove(gate_id)
        attempts = 0
        previous_attempts = int(gate_results.get(gate_id, {}).get("attempts", 0))
        status = "blocked"
        failure = "execution"
        receipt_ref = ""
        quiet_polls = 0
        recovery: dict[str, Any] = {}
        while attempts < contract["budget"]["max_attempts_per_gate"]:
            if time.monotonic() - started >= contract["budget"]["max_seconds"]:
                failure = "time-budget"
                break
            attempts += 1
            remaining = max(1, int(contract["budget"]["max_seconds"] - (time.monotonic() - started)))
            status, failure, _, receipt_ref, quiet_polls = _run_gate_with_heartbeat(
                root,
                output,
                contract,
                gate,
                previous_attempts + attempts,
                remaining,
                contract["continuity"],
                completed=completed,
                blocked=blocked,
                evidence_refs=[receipt_ref] if receipt_ref else [],
                next_action=f"retry-gate:{gate_id}",
            )
            recovery = _recovery_for_receipt(root, receipt_ref, failure, previous_attempts + attempts) if receipt_ref else classify_failure(failure)
            if status == "passed":
                break
            if gate["retry_class"] != "transient" or recovery["recovery_class"] not in {"retryable", "diagnose-once"} or attempts >= contract["budget"]["max_attempts_per_gate"]:
                break
            time.sleep(min(contract["continuity"]["retry_delays_seconds"][attempts - 1], int(recovery.get("retry_delay_seconds", 300))))
        frozen_attempt = None
        if status != "passed" and "continuation_command" in gate:
            frozen_attempt = {"status": status, "failure_layer": failure, "attempts": attempts, "receipt_ref": receipt_ref}
            remaining = max(1, int(contract["budget"]["max_seconds"] - (time.monotonic() - started)))
            status, failure, _, receipt_ref, quiet_polls = _run_gate_with_heartbeat(
                root,
                output,
                contract,
                gate,
                1,
                remaining,
                contract["continuity"],
                completed=completed,
                blocked=blocked,
                evidence_refs=[receipt_ref] if receipt_ref else [],
                next_action=f"continuation-gate:{gate_id}",
                continuation=1,
            )
        if status != "passed" and (failure in USER_ACTION_FAILURES or recovery.get("recovery_class") == "awaiting-user-action"):
            status = "awaiting_user_action"
        retried = attempts > 1
        if status == "passed":
            completed.append(gate_id)
            next_action = "run-next-ready-gate" if pending else "final-report"
        else:
            blocked.append(gate_id)
            next_action = "run-independent-ready-gate" if any(set(gates[item]["depends_on"]).issubset(completed) for item in pending) else "final-report"
        gate_results[gate_id] = {
            "status": status,
            "failure_layer": failure,
            "attempts": attempts,
            "automatic_retry_observed": retried,
            "automatic_fresh_continuation_observed": frozen_attempt is not None,
            "frozen_attempt": frozen_attempt,
            "evidence_ref": receipt_ref,
            "receipt_ref": receipt_ref,
            "quiet_receipt_polls": quiet_polls,
            "next_automatic_action": next_action,
            "recovery": recovery,
        }
        progress_index += 1
        _write_fresh(output / f"progress-{progress_index:03d}.json", _progress(contract, progress_index, gate_id, status, completed, blocked, next_action, failure_layer=failure, attempts=attempts, receipt_ref=receipt_ref, quiet_polls=quiet_polls, automatic_retry_observed=retried))
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "autonomy_id": contract["autonomy_id"],
        "status": "completed" if not pending and not blocked and len(completed) == len(gates) else "blocked",
        "completed_gates": sorted(completed),
        "blocked_gates": sorted(set(blocked) | pending),
        "awaiting_user_action_gates": sorted(gate_id for gate_id, value in gate_results.items() if value.get("status") == "awaiting_user_action"),
        "gates": gate_results,
        "goal_digest": _digest_goals(contract["goals"]),
        "release_authorized": True,
        "next_action": "release" if not pending and not blocked and len(completed) == len(gates) else ("awaiting-user-action" if any(value.get("status") == "awaiting_user_action" for value in gate_results.values()) else "resume-independent-gate"),
        "raw_output_persisted": False,
    }
    summary_path = output / "summary.json"
    if summary_path.exists():
        summary_path = output / f"summary-resume-{progress_index:03d}.json"
    summary["summary_ref"] = summary_path.relative_to(output).as_posix()
    _write_fresh(summary_path, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a bounded DS Lite autonomy contract in the foreground.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted output directory without rerunning terminal gates.")
    args = parser.parse_args(argv)
    try:
        result = run(Path(args.root), Path(args.contract), Path(args.output), resume=args.resume)
    except (OSError, UnicodeError, json.JSONDecodeError, AutonomyError) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "autonomy-controller", "message": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({"status": result["status"], "next_action": result["next_action"]}, ensure_ascii=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
