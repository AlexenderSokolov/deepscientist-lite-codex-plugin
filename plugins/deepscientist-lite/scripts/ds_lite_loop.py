#!/usr/bin/env python3
"""Bounded, fail-closed supervisor for consecutive DS Lite iterations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any

CONTRACT_SCHEMA = "ds-lite.loop-contract.v1"
RECEIPT_SCHEMA = "ds-lite.loop-receipt.v1"
SUMMARY_SCHEMA = "ds-lite.loop-summary.v1"
ADAPTERS = {"fake", "native-codex", "codex-autoresearch"}
TERMINAL = {"completed", "blocked", "failed", "ambiguous", "cancelled"}
FROZEN_FAILURES = {"auth", "rate-limit", "network", "protocol", "timeout", "duplicate-risk", "ambiguous"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MIN_CODEX_VERSION = "0.144.5"
DEFAULT_CODEX_SHA256 = "EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A"
RESULT_PREFIX = "DS_LITE_LOOP_RESULT "
RESULT_STATUSES = {"partial", "completed", "blocked", "failed", "ambiguous"}
RECEIPT_FIELDS = frozenset({
    "schema_version", "loop_id", "round", "adapter", "frozen_goal_digest", "status",
    "session_hash", "process_started", "returncode_observed", "terminal_event_observed",
    "result_signal_observed", "completion_signal_observed", "completed_goal_ids", "goal_set_match",
    "missing_evidence", "continuation_authorized", "automatic_retry_observed", "failure_layer",
    "child_process_state", "stdout_pipe_state", "stderr_pipe_state", "raw_output_persisted", "next_action",
})


class LoopError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LoopError(f"invalid JSON input: {path.name}") from exc


def _write_fresh(path: Path, value: Any) -> None:
    if path.exists():
        raise LoopError(f"refusing to overwrite existing output: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _relative_ref(value: str, field: str, *, allow_empty: bool = False) -> str:
    if allow_empty and not value:
        return ""
    if not isinstance(value, str) or not value or "\\" in value or "<" in value or ">" in value:
        raise LoopError(f"{field} must be a project-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise LoopError(f"{field} must be a project-relative POSIX path")
    return value


def _is_within(candidate: Path, root: Path, *, allow_root: bool = True) -> bool:
    if candidate == root:
        return allow_root
    return root in candidate.parents


def _resolve_ref(root: Path, ref: str, field: str, *, require_file: bool = False) -> Path:
    normalized = _relative_ref(ref, field)
    candidate = root.joinpath(*PurePosixPath(normalized).parts).resolve(strict=False)
    if not _is_within(candidate, root):
        raise LoopError(f"{field} resolves outside the loop root")
    if require_file and not candidate.is_file():
        raise LoopError(f"{field} must reference an existing file")
    return candidate


def _resolve_output(root: Path, output: str) -> Path:
    candidate = Path(output).resolve(strict=False)
    if not _is_within(candidate, root, allow_root=False):
        raise LoopError("output_dir must be a child of the loop root")
    return candidate


def _goal_digest(goals: list[dict[str, Any]]) -> str:
    projection = [{"id": item["id"], "evidence_refs": item["evidence_refs"]} for item in goals]
    return hashlib.sha256(json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_goals(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise LoopError("goals must be a non-empty list")
    result = []
    seen = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"id", "evidence_refs"}:
            raise LoopError(f"goals[{index}] must contain exactly id and evidence_refs")
        goal_id = item["id"]
        if not isinstance(goal_id, str) or not ID_RE.fullmatch(goal_id) or goal_id in seen:
            raise LoopError(f"goals[{index}].id is invalid or duplicated")
        refs = item["evidence_refs"]
        if not isinstance(refs, list) or not refs:
            raise LoopError(f"goals[{index}].evidence_refs must be non-empty")
        refs = [_relative_ref(ref, f"goals[{index}].evidence_refs") for ref in refs]
        result.append({"id": goal_id, "evidence_refs": refs})
        seen.add(goal_id)
    return result


def validate_contract(value: Any) -> dict[str, Any]:
    required = {
        "schema_version", "loop_id", "adapter", "status", "frozen_goals", "frozen_goal_digest",
        "working_plan_ref", "prompt_ref", "allowed_paths", "budgets", "authorization", "sandbox",
        "stop_conditions", "extensions",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise LoopError("loop contract fields do not match the v1 schema")
    if value["schema_version"] != CONTRACT_SCHEMA or not ID_RE.fullmatch(str(value["loop_id"])):
        raise LoopError("loop contract identity is invalid")
    if value["adapter"] not in ADAPTERS or value["status"] not in {"prepared", "running", *TERMINAL}:
        raise LoopError("loop adapter or status is invalid")
    goals = _validate_goals(value["frozen_goals"])
    if value["frozen_goal_digest"] != _goal_digest(goals):
        raise LoopError("frozen goal digest mismatch")
    value["working_plan_ref"] = _relative_ref(value["working_plan_ref"], "working_plan_ref")
    value["prompt_ref"] = _relative_ref(value["prompt_ref"], "prompt_ref")
    if not isinstance(value["allowed_paths"], list) or not value["allowed_paths"]:
        raise LoopError("allowed_paths must be non-empty")
    value["allowed_paths"] = [_relative_ref(item, "allowed_paths") for item in value["allowed_paths"]]
    budgets = value["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != {"max_rounds", "max_seconds"}:
        raise LoopError("budgets must contain max_rounds and max_seconds")
    if not isinstance(budgets["max_rounds"], int) or not 1 <= budgets["max_rounds"] <= 20:
        raise LoopError("max_rounds must be between 1 and 20")
    if not isinstance(budgets["max_seconds"], int) or not 1 <= budgets["max_seconds"] <= 86400:
        raise LoopError("max_seconds must be between 1 and 86400")
    authorization = value["authorization"]
    if not isinstance(authorization, dict) or set(authorization) != {"status", "authority", "ref"}:
        raise LoopError("authorization fields are invalid")
    if authorization["status"] not in {"required", "approved", "denied"}:
        raise LoopError("authorization.status is invalid")
    if authorization["status"] == "approved":
        if not isinstance(authorization["authority"], str) or authorization["authority"] == "none" or not ID_RE.fullmatch(authorization["authority"]):
            raise LoopError("approved authorization requires a valid authority")
        authorization["ref"] = _relative_ref(authorization["ref"], "authorization.ref")
    elif authorization["authority"] != "none" or authorization["ref"]:
        raise LoopError("non-approved authorization must use authority none and no ref")
    if not isinstance(value["sandbox"], str) or value["sandbox"] not in {"read-only", "workspace-write"}:
        raise LoopError("sandbox must be read-only or workspace-write")
    if not isinstance(value["stop_conditions"], list) or not value["stop_conditions"]:
        raise LoopError("stop_conditions must be non-empty")
    if not isinstance(value["extensions"], dict):
        raise LoopError("extensions must be an object")
    return value


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    goals = _validate_goals(_read_json(Path(args.goals_file)))
    contract = {
        "schema_version": CONTRACT_SCHEMA,
        "loop_id": args.loop_id,
        "adapter": args.adapter,
        "status": "prepared",
        "frozen_goals": goals,
        "frozen_goal_digest": _goal_digest(goals),
        "working_plan_ref": _relative_ref(args.working_plan_ref, "working_plan_ref"),
        "prompt_ref": _relative_ref(args.prompt_ref, "prompt_ref"),
        "allowed_paths": [_relative_ref(item, "allowed_paths") for item in args.allowed_path],
        "budgets": {"max_rounds": args.max_rounds, "max_seconds": args.max_seconds},
        "authorization": {"status": args.authorization, "authority": args.authority, "ref": args.approval_ref},
        "sandbox": args.sandbox,
        "stop_conditions": ["Stop on authorization, ambiguous, timeout, transport, rate-limit, duplicate-risk, or budget blockers."],
        "extensions": {},
    }
    validate_contract(contract)
    _write_fresh(Path(args.output), contract)
    return contract


def _failure_class(text: str, returncode: int | None, timed_out: bool) -> str:
    lowered = text.lower()
    if timed_out:
        return "timeout"
    if any(token in lowered for token in ("401", "403", "unauthorized", "forbidden", "invalid api key")):
        return "auth"
    if any(token in lowered for token in ("429", "rate limit", "too many requests")):
        return "rate-limit"
    if any(token in lowered for token in ("dns", "connection refused", "connection reset", "network unreachable")):
        return "network"
    if any(token in lowered for token in ("malformed", "invalid json", "unexpected event", "protocol")):
        return "protocol"
    if returncode not in (None, 0):
        return "child-process"
    return "none"


def _validated_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != {"status", "goal_ids"}:
        return None
    goal_ids = value["goal_ids"]
    if value["status"] not in RESULT_STATUSES or not isinstance(goal_ids, list):
        return None
    if not all(isinstance(item, str) and ID_RE.fullmatch(item) for item in goal_ids):
        return None
    return {"status": value["status"], "goal_ids": goal_ids}


def _result_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "item.completed":
        return None
    item = event.get("item")
    if not isinstance(item, dict) or item.get("type") != "agent_message":
        return None
    text = item.get("text")
    if not isinstance(text, str) or not text.startswith(RESULT_PREFIX) or "\n" in text or "\r" in text:
        return None
    try:
        payload_text = text[len(RESULT_PREFIX):]
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    result = _validated_result(payload)
    if result is None or json.dumps(result, ensure_ascii=True, separators=(",", ":")) != payload_text:
        return None
    return result


def _reduce_jsonl(text: str) -> dict[str, Any]:
    session_id = ""
    candidate = None
    candidate_count = 0
    invalid_sequence = False
    terminal_count = 0
    terminal_type = "none"
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type in {"thread.started", "thread.created"}:
            session_candidate = event.get("thread_id") or event.get("threadId")
            if isinstance(session_candidate, str) and SESSION_ID_RE.fullmatch(session_candidate):
                session_id = session_candidate
        result_candidate = _result_from_event(event)
        if result_candidate is not None:
            candidate_count += 1
            if terminal_count:
                invalid_sequence = True
            if candidate_count == 1:
                candidate = result_candidate
            else:
                invalid_sequence = True
        if event_type == "turn.completed":
            terminal_count += 1
            terminal_type = "completed"
            if terminal_count > 1:
                invalid_sequence = True
        elif event_type in {"turn.failed", "error"}:
            terminal_count += 1
            terminal_type = "failed"
            invalid_sequence = True
    result = candidate if terminal_count == 1 and terminal_type == "completed" and candidate_count == 1 and not invalid_sequence else None
    completion = result if result is not None and result["status"] == "completed" else None
    return {
        "session_id": session_id,
        "result": result,
        "completion": completion,
        "terminal_event_observed": terminal_count > 0,
        "terminal_failure_observed": terminal_type == "failed",
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _parse_version(text: str) -> tuple[int, ...]:
    """Extract a numeric version tuple from a version string."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def _version_ge(actual: str, minimum: str) -> bool:
    """Check if actual version is >= minimum version using simple tuple comparison."""
    actual_parts = _parse_version(actual)
    min_parts = _parse_version(minimum)
    return actual_parts >= min_parts


def _validate_codex_binary(path: Path) -> Path:
    try:
        binary = path.resolve(strict=True)
    except OSError as exc:
        raise LoopError("codex_bin must reference an existing pinned binary") from exc
    if not binary.is_file():
        raise LoopError("codex_bin must reference a file")
    skip_sha256 = os.environ.get("DS_LITE_SKIP_SHA256_CHECK", "").strip().lower() in ("1", "true", "yes")
    if not skip_sha256:
        expected_sha = os.environ.get("DS_LITE_CODEX_SHA256", DEFAULT_CODEX_SHA256)
        if _file_sha256(binary) != expected_sha:
            if os.environ.get("DS_LITE_STRICT_SHA256", "").strip().lower() in ("1", "true", "yes"):
                raise LoopError("codex_bin SHA-256 does not match the pinned binary")
    try:
        probe = subprocess.run(
            [str(binary), "--version"],
            cwd=str(binary.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LoopError("codex_bin version probe failed") from exc
    version_text = (probe.stdout or "") + "\n" + (probe.stderr or "")
    if probe.returncode != 0:
        raise LoopError("codex_bin version probe returned non-zero exit")
    if not _version_ge(version_text, MIN_CODEX_VERSION):
        raise LoopError(f"codex_bin version must be >= {MIN_CODEX_VERSION}")
    return binary


def _run_process(command: list[str], cwd: Path, timeout: int, input_text: str | None = None) -> dict[str, Any]:
    started = False
    timed_out = False
    returncode: int | None = None
    text = ""
    protocol_text = ""
    child_state = "not-started"
    stdout_pipe_state = "not-opened"
    stderr_pipe_state = "not-opened"
    try:
        process = subprocess.Popen(command, cwd=str(cwd), text=True, encoding="utf-8", errors="replace",
                                   stdin=subprocess.PIPE if input_text is not None else None,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        started = True
        child_state = "running"
        stdout_pipe_state = "open" if process.stdout is not None else "missing"
        stderr_pipe_state = "open" if process.stderr is not None else "missing"
        if input_text is None:
            stdout, stderr = process.communicate(timeout=timeout)
        else:
            stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        returncode = process.returncode
        protocol_text = stdout or ""
        text = (stdout or "") + "\n" + (stderr or "")
        stdout_pipe_state = "closed"
        stderr_pipe_state = "closed"
        child_state = "exited" if returncode == 0 else "early-exit"
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
        returncode = process.returncode
        protocol_text = stdout or ""
        text = (stdout or "") + "\n" + (stderr or "")
        stdout_pipe_state = "closed"
        stderr_pipe_state = "closed"
        child_state = "timed-out"
    except (OSError, ValueError, subprocess.SubprocessError):
        child_state = "spawn-failed" if not started else "pipe-failed"
        stdout_pipe_state = "not-opened" if not started else "error"
        stderr_pipe_state = "not-opened" if not started else "error"
    reduced = _reduce_jsonl(protocol_text)
    failure = _failure_class(text, returncode, timed_out)
    if child_state in {"spawn-failed", "pipe-failed"}:
        failure = "child-process"
    elif returncode == 0 and (not reduced["terminal_event_observed"] or reduced["result"] is None):
        failure = "protocol"
    elif reduced["terminal_failure_observed"] and failure in {"none", "child-process"}:
        failure = "protocol"
    return {
        "process_started": started,
        "returncode_observed": returncode is not None,
        "returncode": returncode,
        "timed_out": timed_out,
        "session_id": reduced["session_id"],
        "result": reduced["result"],
        "completion": reduced["completion"],
        "terminal_event_observed": reduced["terminal_event_observed"],
        "failure_layer": failure,
        "child_process_state": child_state,
        "stdout_pipe_state": stdout_pipe_state,
        "stderr_pipe_state": stderr_pipe_state,
        "diagnostic_sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
        "diagnostic_line_count": len(text.splitlines()),
        "raw_output_persisted": False,
    }


def _fake_rounds(path: Path) -> list[dict[str, Any]]:
    value = _read_json(path)
    if not isinstance(value, list) or not value:
        raise LoopError("fake sequence must be a non-empty list")
    return value


def _evidence_gate(root: Path, goals: list[dict[str, Any]], completed_ids: list[str],
                   allowed_roots: list[Path]) -> tuple[bool, list[str], bool]:
    frozen_ids = [goal["id"] for goal in goals]
    goal_set_match = len(completed_ids) == len(frozen_ids) and set(completed_ids) == set(frozen_ids)
    completed = set(completed_ids)
    missing = []
    if not goal_set_match:
        missing.append("frozen-goal-set-mismatch")
    for goal in goals:
        if goal["id"] not in completed:
            missing.append(f"goal:{goal['id']}")
        for ref in goal["evidence_refs"]:
            evidence = _resolve_ref(root, ref, "evidence_ref")
            if not any(_is_within(evidence, allowed_root) for allowed_root in allowed_roots):
                missing.append(f"outside-allowed-path:{ref}")
            elif not evidence.is_file():
                missing.append(ref)
    return not missing, missing, goal_set_match


def _receipt(contract: dict[str, Any], round_index: int, observation: dict[str, Any], status: str,
             failure_layer: str, completed_ids: list[str], missing: list[str], continuation: bool,
             goal_set_match: bool) -> dict[str, Any]:
    session_id = str(observation.get("session_id", ""))
    frozen_ids = {item["id"] for item in contract["frozen_goals"]}
    return {
        "schema_version": RECEIPT_SCHEMA,
        "loop_id": contract["loop_id"],
        "round": round_index,
        "adapter": contract["adapter"],
        "frozen_goal_digest": contract["frozen_goal_digest"],
        "status": status,
        "session_hash": hashlib.sha256(session_id.encode("utf-8")).hexdigest() if session_id else "none",
        "process_started": bool(observation.get("process_started", False)),
        "returncode_observed": bool(observation.get("returncode_observed", False)),
        "terminal_event_observed": bool(observation.get("terminal_event_observed", False)),
        "result_signal_observed": bool(observation.get("result")),
        "completion_signal_observed": bool(observation.get("completion")),
        "completed_goal_ids": sorted({item for item in completed_ids if item in frozen_ids}),
        "goal_set_match": goal_set_match,
        "missing_evidence": missing,
        "continuation_authorized": continuation,
        "automatic_retry_observed": False,
        "failure_layer": failure_layer,
        "child_process_state": str(observation.get("child_process_state", "not-observed")),
        "stdout_pipe_state": str(observation.get("stdout_pipe_state", "not-observed")),
        "stderr_pipe_state": str(observation.get("stderr_pipe_state", "not-observed")),
        "raw_output_persisted": False,
        "next_action": "continue-next-bounded-iteration" if continuation else "stop-and-report",
    }


def _protocol_prompt(contract: dict[str, Any], task_text: str, phase: str) -> str:
    goal_ids = [item["id"] for item in contract["frozen_goals"]]
    protocol = (
        "\n\nDS Lite bounded-loop result protocol (mandatory):\n"
        f"phase={phase}\n"
        f"frozen_goal_ids={json.dumps(goal_ids, ensure_ascii=True, separators=(',', ':'))}\n"
        f"frozen_goal_digest={contract['frozen_goal_digest']}\n"
        "Allowed status values: partial, completed, blocked, failed, ambiguous.\n"
        "Your final agent_message must be exactly one single line: DS_LITE_LOOP_RESULT followed by one space "
        "and compact JSON with exactly status and goal_ids. Do not emit a template or surrounding text.\n"
        "Use one allowed status value and only frozen goal IDs. Emit this carrier exactly once.\n"
    )
    return task_text + protocol


def run_loop(args: argparse.Namespace) -> dict[str, Any]:
    contract_path = Path(args.contract)
    contract = validate_contract(_read_json(contract_path))
    try:
        root = Path(args.root).resolve(strict=True)
    except OSError as exc:
        raise LoopError("root must be an existing directory") from exc
    if not root.is_dir():
        raise LoopError("root must be an existing directory")
    output = _resolve_output(root, args.output_dir)
    if output.exists():
        raise LoopError("loop output directory already exists; refusing overwrite")
    _resolve_ref(root, contract["working_plan_ref"], "working_plan_ref", require_file=True)
    prompt_path = _resolve_ref(root, contract["prompt_ref"], "prompt_ref", require_file=True)
    allowed_roots = [_resolve_ref(root, item, "allowed_paths") for item in contract["allowed_paths"]]
    if contract["authorization"]["status"] == "approved":
        _resolve_ref(root, contract["authorization"]["ref"], "authorization.ref", require_file=True)
    if contract["authorization"]["status"] != "approved" and contract["adapter"] != "fake":
        raise LoopError("real loop execution requires approved authorization")
    if contract["adapter"] != "fake" and not args.execute:
        raise LoopError("real adapter requires --execute")
    if contract["adapter"] == "codex-autoresearch":
        raise LoopError("external-policy-unverified: upstream loop does not expose bounded one-attempt controls")
    fake_rounds = _fake_rounds(Path(args.fake_sequence)) if contract["adapter"] == "fake" else []
    codex: Path | None = None
    if contract["adapter"] == "native-codex":
        if not args.codex_bin:
            raise LoopError("native-codex requires an explicit pinned --codex-bin")
        codex = _validate_codex_binary(Path(args.codex_bin))
    start = time.monotonic()
    receipts = []
    session_id = ""
    final_status = "blocked"
    for round_index in range(1, contract["budgets"]["max_rounds"] + 1):
        remaining = contract["budgets"]["max_seconds"] - (time.monotonic() - start)
        if remaining <= 0:
            observation = {
                "process_started": False,
                "returncode_observed": False,
                "session_id": session_id,
                "result": None,
                "completion": None,
                "terminal_event_observed": False,
                "failure_layer": "time-budget",
                "child_process_state": "not-started",
                "stdout_pipe_state": "not-opened",
                "stderr_pipe_state": "not-opened",
            }
            _, missing, goal_set_match = _evidence_gate(root, contract["frozen_goals"], [], allowed_roots)
            receipt = _receipt(contract, round_index, observation, "blocked", "time-budget", [], missing, False,
                               goal_set_match)
            receipts.append(receipt)
            _write_fresh(output / f"round-{round_index:03d}.json", receipt)
            final_status = "blocked"
            break
        if contract["adapter"] == "fake":
            if round_index > len(fake_rounds):
                observation = {"process_started": False, "returncode_observed": False, "session_id": "",
                               "result": None, "completion": None, "failure_layer": "ambiguous"}
                declared = "ambiguous"
                completed_ids = []
            else:
                item = fake_rounds[round_index - 1]
                declared = str(item.get("status", "ambiguous"))
                completed_ids = list(item.get("completed_goal_ids", []))
                fake_result = {"status": declared, "goal_ids": completed_ids} if declared in RESULT_STATUSES else None
                observation = {"process_started": True, "returncode_observed": True,
                               "session_id": str(item.get("session_id", "fake-session")),
                               "result": fake_result,
                               "completion": {"status": "completed", "goal_ids": completed_ids} if item.get("completion") else None,
                               "failure_layer": str(item.get("failure_layer", "none"))}
        elif contract["adapter"] == "native-codex":
            assert codex is not None
            if round_index == 1:
                prompt = prompt_path.read_text(encoding="utf-8")
                input_text = _protocol_prompt(contract, prompt, "initial")
                command = [str(codex), "exec", "-C", str(root), "--json", "--sandbox", contract["sandbox"],
                           "--skip-git-repo-check", "-"]
            else:
                if not session_id:
                    raise LoopError("native-codex continuation requires an observed session id")
                sandbox_config = f'sandbox_mode="{contract["sandbox"]}"'
                input_text = _protocol_prompt(
                    contract,
                    "Continue one bounded DS Lite iteration. Verify artifacts and stop on any blocker.",
                    "continuation",
                )
                command = [str(codex), "exec", "-C", str(root), "resume", "--json", "--skip-git-repo-check",
                           "-c", sandbox_config, session_id, "-"]
            observation = _run_process(command, root, remaining, input_text=input_text)
            session_id = observation.get("session_id") or session_id
            result = observation.get("result")
            completed_ids = list(result.get("goal_ids", [])) if isinstance(result, dict) else []
            declared = str(result.get("status")) if isinstance(result, dict) else "blocked"
        else:
            raise LoopError("external-policy-unverified: external adapter execution is disabled")
        failure = str(observation.get("failure_layer", "unknown"))
        if contract["adapter"] == "native-codex" and declared == "partial" and not session_id:
            failure = "protocol"
        evidence_ok, missing, goal_set_match = _evidence_gate(root, contract["frozen_goals"], completed_ids,
                                                               allowed_roots)
        if declared == "completed" and evidence_ok and observation.get("completion"):
            status = "completed"
            continuation = False
        elif declared == "completed":
            status = "blocked"
            continuation = False
        elif declared == "partial" and failure == "none":
            status = "partial"
            continuation = True
        else:
            status = declared if declared in TERMINAL else "blocked"
            continuation = False
        if failure in FROZEN_FAILURES or failure != "none" or status in {"blocked", "failed", "ambiguous", "cancelled"}:
            continuation = False
        if status == "partial" and round_index == contract["budgets"]["max_rounds"]:
            status = "blocked"
            failure = "round-budget"
            continuation = False
        receipt = _receipt(contract, round_index, observation, status, failure, completed_ids, missing, continuation,
                           goal_set_match)
        receipts.append(receipt)
        _write_fresh(output / f"round-{round_index:03d}.json", receipt)
        final_status = status
        if not continuation:
            break
    if receipts and receipts[-1]["continuation_authorized"]:
        final_status = "blocked"
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "loop_id": contract["loop_id"],
        "status": final_status,
        "round_count": len(receipts),
        "frozen_goal_digest": contract["frozen_goal_digest"],
        "automatic_retry_observed": False,
        "raw_output_persisted": False,
        "unverified": [] if final_status == "completed" else ["remaining frozen goals", "real provider/host effect"],
        "next_action": "acceptance-review" if final_status == "completed" else "inspect-terminal-receipt",
    }
    _write_fresh(output / "summary.json", summary)
    return summary


def verify(args: argparse.Namespace) -> dict[str, Any]:
    contract = validate_contract(_read_json(Path(args.contract)))
    summary_path = Path(args.summary)
    summary = _read_json(summary_path)
    expected_summary_fields = {
        "schema_version", "loop_id", "status", "round_count", "frozen_goal_digest",
        "automatic_retry_observed", "raw_output_persisted", "unverified", "next_action",
    }
    if not isinstance(summary, dict) or set(summary) != expected_summary_fields or summary.get("schema_version") != SUMMARY_SCHEMA:
        raise LoopError("loop summary schema is invalid")
    round_count = summary.get("round_count")
    valid = (
        summary.get("loop_id") == contract["loop_id"]
        and summary.get("frozen_goal_digest") == contract["frozen_goal_digest"]
        and summary.get("status") == "completed"
        and isinstance(round_count, int)
        and 1 <= round_count <= contract["budgets"]["max_rounds"]
        and summary.get("unverified") == []
        and summary.get("automatic_retry_observed") is False
        and summary.get("raw_output_persisted") is False
        and summary.get("next_action") == "acceptance-review"
    )
    receipt_dir = summary_path.parent
    receipt_paths = sorted(receipt_dir.glob("round-*.json"))
    expected_names = [f"round-{index:03d}.json" for index in range(1, round_count + 1)] if isinstance(round_count, int) and round_count >= 1 else []
    if [path.name for path in receipt_paths] != expected_names:
        valid = False
    session_hashes = set()
    frozen_ids = sorted(item["id"] for item in contract["frozen_goals"])
    for index, receipt_path in enumerate(receipt_paths, 1):
        try:
            receipt = _read_json(receipt_path)
        except LoopError:
            valid = False
            continue
        if not isinstance(receipt, dict):
            valid = False
            continue
        common_valid = (
            set(receipt) == RECEIPT_FIELDS
            and
            receipt.get("schema_version") == RECEIPT_SCHEMA
            and receipt.get("loop_id") == contract["loop_id"]
            and receipt.get("adapter") == contract["adapter"]
            and receipt.get("frozen_goal_digest") == contract["frozen_goal_digest"]
            and receipt.get("round") == index
            and receipt.get("automatic_retry_observed") is False
            and receipt.get("raw_output_persisted") is False
        )
        valid = valid and common_valid
        session_hash = receipt.get("session_hash")
        if isinstance(session_hash, str) and session_hash != "none":
            session_hashes.add(session_hash)
        if index < len(receipt_paths):
            valid = valid and receipt.get("status") == "partial" and receipt.get("continuation_authorized") is True
            valid = valid and receipt.get("failure_layer") == "none"
            valid = valid and receipt.get("result_signal_observed") is True
        else:
            valid = valid and receipt.get("status") == "completed" and receipt.get("continuation_authorized") is False
            valid = valid and receipt.get("failure_layer") == "none"
            valid = valid and receipt.get("completion_signal_observed") is True
            valid = valid and receipt.get("result_signal_observed") is True
            valid = valid and receipt.get("goal_set_match") is True
            valid = valid and receipt.get("completed_goal_ids") == frozen_ids
            valid = valid and receipt.get("missing_evidence") == []
    if len(session_hashes) > 1:
        valid = False
    if contract["adapter"] == "native-codex":
        valid = valid and len(session_hashes) == 1
        valid = valid and all(receipt.get("session_hash") != "none" for receipt in (
            _read_json(path) for path in receipt_paths
        ))
    result = {"schema_version": "ds-lite.loop-verification.v1", "status": "passed" if valid else "blocked",
              "loop_id": contract["loop_id"], "raw_output_persisted": False}
    return result


def status(args: argparse.Namespace) -> dict[str, Any]:
    value = _read_json(Path(args.summary))
    if not isinstance(value, dict) or value.get("schema_version") != SUMMARY_SCHEMA:
        raise LoopError("loop summary schema is invalid")
    loop_id = value.get("loop_id")
    state = value.get("status")
    round_count = value.get("round_count")
    if not isinstance(loop_id, str) or not ID_RE.fullmatch(loop_id):
        raise LoopError("loop summary identity is invalid")
    if state not in {"completed", "blocked", "failed", "ambiguous", "cancelled", "partial"}:
        raise LoopError("loop summary status is invalid")
    if not isinstance(round_count, int) or round_count < 0:
        raise LoopError("loop summary round_count is invalid")
    next_action = "acceptance-review" if state == "completed" else "inspect-terminal-receipt"
    return {"schema_version": SUMMARY_SCHEMA, "loop_id": loop_id,
            "status": state, "round_count": round_count,
            "next_action": next_action}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded DS Lite continuation loops.")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--loop-id", required=True)
    prepare_parser.add_argument("--goals-file", required=True)
    prepare_parser.add_argument("--working-plan-ref", required=True)
    prepare_parser.add_argument("--prompt-ref", required=True)
    prepare_parser.add_argument("--allowed-path", action="append", required=True)
    prepare_parser.add_argument("--adapter", choices=sorted(ADAPTERS), default="fake")
    prepare_parser.add_argument("--max-rounds", type=int, default=3)
    prepare_parser.add_argument("--max-seconds", type=int, default=1800)
    prepare_parser.add_argument("--authorization", choices=("required", "approved", "denied"), default="required")
    prepare_parser.add_argument("--authority", default="none")
    prepare_parser.add_argument("--approval-ref", default="")
    prepare_parser.add_argument("--sandbox", choices=("read-only", "workspace-write"), default="read-only")
    prepare_parser.add_argument("--output", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--contract", required=True)
    run_parser.add_argument("--root", required=True)
    run_parser.add_argument("--output-dir", required=True)
    run_parser.add_argument("--fake-sequence")
    run_parser.add_argument("--codex-bin")
    run_parser.add_argument("--autoresearch-bin")
    run_parser.add_argument("--execute", action="store_true")
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--summary", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--contract", required=True)
    verify_parser.add_argument("--summary", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args)
        elif args.command == "run":
            if args.adapter if hasattr(args, "adapter") else False:
                raise LoopError("adapter is contract-controlled")
            if not args.fake_sequence and validate_contract(_read_json(Path(args.contract)))["adapter"] == "fake":
                raise LoopError("fake adapter requires --fake-sequence")
            result = run_loop(args)
        elif args.command == "verify":
            result = verify(args)
        else:
            result = status(args)
    except LoopError as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "loop-protocol", "message": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result.get("status") in {"prepared", "passed", "completed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
