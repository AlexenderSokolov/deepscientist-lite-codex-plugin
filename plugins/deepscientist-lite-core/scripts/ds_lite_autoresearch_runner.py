#!/usr/bin/env python3
"""Persistent DS Lite session runner derived from codex-autoresearch semantics."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ds_lite_recovery import classify_failure, retry_schedule


SCHEMA = "ds-lite.autoresearch-job.v1"
COMPLETION_FAILURE_SCHEMA = "ds-lite.completion-failure.v1"
PROGRESS_SCHEMA = "ds-lite.autoresearch-progress.v1"
STATES = {"pending", "running", "needs_resume", "awaiting_user_action", "completed", "failed"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
GOAL_RE = re.compile(r"^-\s*\[x\]\s+(.+?)\s*$", re.IGNORECASE)


class RunnerError(RuntimeError):
    pass


@contextlib.contextmanager
def _owner_lock(state_dir: Path):
    """Serialize lease inspection and renewal without deleting lock files."""
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "owner.lock"
    handle = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _write_json(path: Path, payload: dict[str, Any], *, fresh: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh and path.exists():
        raise RunnerError(f"refusing to overwrite receipt: {path.name}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_text(path: Path, value: str, *, fresh: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh and path.exists():
        raise RunnerError(f"refusing to overwrite receipt: {path.name}")
    path.write_text(value, encoding="utf-8", newline="\n")


def _append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"invalid runner state: {path.name}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"runner state must be an object: {path.name}")
    return value


def _read_session_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return _validate_session_id(value) if value else None


def _validate_session_id(value: str | None) -> str:
    if not value or not ID_RE.fullmatch(value) or value.startswith("-"):
        raise RunnerError("observed session id is invalid")
    return value


def _job_dir(root: Path, job_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", job_id):
        raise RunnerError("job id is invalid")
    return root.resolve() / job_id


def claim_owner(state_dir: Path, owner_id: str, *, now: float | None = None, lease_seconds: int = 120) -> bool:
    """Claim a persistent owner record without deleting or replacing receipts."""
    if not owner_id or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", owner_id):
        raise RunnerError("owner id is invalid")
    current_time = time.time() if now is None else now
    path = state_dir / "owner.json"
    with _owner_lock(state_dir):
        if path.is_file():
            current = _read_json(path)
            if (
                current.get("active") is True
                and float(current.get("lease_until", 0)) > current_time
                and current.get("owner_id") != owner_id
            ):
                return False
        record = {
            "schema_version": "ds-lite.runner-owner.v1",
            "owner_id": owner_id,
            "owner_token": uuid.uuid4().hex,
            "active": True,
            "lease_until": current_time + lease_seconds,
        }
        _write_json(path, record)
        return True


def _owner_token(state_dir: Path, owner_id: str) -> str:
    """Return the current lease token without exposing it in event receipts."""
    path = state_dir / "owner.json"
    if not path.is_file():
        return ""
    record = _read_json(path)
    if record.get("owner_id") != owner_id:
        return ""
    token = record.get("owner_token")
    return token if isinstance(token, str) else ""


def release_owner(state_dir: Path, owner_id: str) -> None:
    path = state_dir / "owner.json"
    with _owner_lock(state_dir):
        if not path.is_file():
            return
        try:
            record = _read_json(path)
        except RunnerError:
            return
        if record.get("owner_id") != owner_id:
            return
        record["active"] = False
        record["released_at"] = time.time()
        _write_json(path, record)


def inspect_completion(message: str, frozen_goals: list[str]) -> dict[str, Any]:
    """Validate the upstream completion token plus every frozen goal line."""
    report_match = re.search(r"<completion_report>\s*([\s\S]*?)\s*</completion_report>", message or "", re.IGNORECASE)
    checked: list[str] = []
    if report_match:
        for line in report_match.group(1).splitlines():
            match = GOAL_RE.match(line.strip())
            if match:
                checked.append(" ".join(match.group(1).split()))
    normalized = {" ".join(goal.split()): goal for goal in frozen_goals}
    missing = [original for key, original in normalized.items() if key not in checked]
    if "CONFIRMED: all tasks completed" not in (message or ""):
        return {"status": "blocked", "failure_layer": "completion-token-missing", "missing_goals": missing, "report_observed": bool(report_match)}
    if missing or not report_match:
        return {"status": "blocked", "failure_layer": "completion-report-incomplete", "missing_goals": missing, "report_observed": bool(report_match)}
    return {"status": "passed", "failure_layer": "none", "missing_goals": [], "report_observed": True}


def build_completion_failure_prompt(result: dict[str, Any]) -> str:
    missing = result.get("missing_goals") or []
    lines = [
        "The previous completion attempt did not satisfy the frozen DS Lite completion contract.",
        f"Failure layer: {result.get('failure_layer', 'completion')}",
    ]
    if missing:
        lines.append("Missing frozen goals:")
        lines.extend(f"- {goal}" for goal in missing)
    lines.append("Continue the same session, complete the missing evidence, then emit a complete <completion_report> and the exact completion token.")
    return "\n".join(lines)


def _safe_last_message(*, completion: dict[str, Any], message: str) -> str:
    """Persist only a semantic summary; never persist the child response itself."""
    missing = completion.get("missing_goals") or []
    lines = [
        f"status: {completion.get('status', 'blocked')}",
        f"failure_layer: {completion.get('failure_layer', 'completion')}",
        f"report_observed: {bool(completion.get('report_observed'))}",
        f"message_sha256: {hashlib.sha256((message or '').encode('utf-8', 'replace')).hexdigest()}",
        "missing_goals:",
    ]
    lines.extend(f"- {goal}" for goal in missing)
    return "\n".join(lines) + "\n"


def build_codex_command(codex_bin: str, root: Path, prompt: str, session_id: str | None, sandbox: str) -> list[str]:
    if sandbox not in {"read-only", "workspace-write"}:
        raise RunnerError("sandbox is invalid")
    base = [codex_bin, "exec"]
    if session_id:
        base.append("resume")
    base.extend(["--json", "-C", str(root), "--sandbox", sandbox, "--skip-git-repo-check"])
    if session_id:
        base.append(_validate_session_id(session_id))
    base.append(prompt)
    return base


def _reduce_output(output: str) -> tuple[str | None, str]:
    session_id: str | None = None
    message = ""
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for key in ("session_id", "conversation_id", "thread_id"):
            value = event.get(key)
            if isinstance(value, str) and ID_RE.fullmatch(value):
                session_id = value
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") in {"agent_message", "message"} and isinstance(item.get("text"), str):
            message = item["text"]
        if isinstance(event.get("last_message"), str):
            message = event["last_message"]
    return session_id, message


def execute_codex(command: list[str], prompt: str, *, cwd: Path, timeout: int = 900) -> dict[str, Any]:
    try:
        env = os.environ.copy()
        env["DS_LITE_AUTORESEARCH_CHILD"] = "1"
        completed = subprocess.run(command, input=None, cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"session_id": None, "message": "", "failure_layer": "timeout"}
    except OSError:
        return {"session_id": None, "message": "", "failure_layer": "spawn"}
    session_id, message = _reduce_output(completed.stdout or "")
    failure = "none" if completed.returncode == 0 else "child-process"
    return {"session_id": session_id, "message": message, "failure_layer": failure}


def _meta(state_dir: Path, job_id: str, status: str, session_id: str | None, attempt_count: int, frozen_goals: list[str], **extra: Any) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA,
        "job_id": job_id,
        "status": status,
        "session_id": session_id or "",
        "attempt_count": attempt_count,
        "frozen_goals": list(frozen_goals),
        "updated_at": time.time(),
        "raw_output_persisted": False,
        "events_file": str(state_dir / "events.jsonl"),
        "session_id_file": str(state_dir / "session-id.txt"),
        "last_message_file": str(state_dir / "last-message.txt"),
        "allowed_statuses": sorted(STATES),
    }
    result.update(extra)
    return result


def run_job(*, root: Path, job_id: str, initial_prompt: str, frozen_goals: list[str], executor: Callable[[list[str], str], dict[str, Any]] | None = None, codex_bin: str = "codex", sandbox: str = "workspace-write", max_attempts: int = 3, lease_seconds: int = 120, owner_id: str | None = None, timeout: int = 900, state_dir: Path | None = None) -> dict[str, Any]:
    state_dir = state_dir.resolve() if state_dir is not None else _job_dir(root, job_id)
    existing = _read_json(state_dir / "meta.json") if (state_dir / "meta.json").is_file() else {}
    if not frozen_goals:
        frozen_goals = [str(item) for item in existing.get("frozen_goals", []) if isinstance(item, str)]
    if not frozen_goals:
        raise RunnerError("frozen goals must not be empty")
    if max_attempts < 1:
        raise RunnerError("max_attempts must be positive")
    if existing.get("status") == "completed":
        return existing
    if existing.get("status") in {"awaiting_user_action", "failed"}:
        return existing
    owner = owner_id or f"runner-{uuid.uuid4().hex}"
    # A child Codex process may use the whole timeout. Keep the lease alive
    # for that bounded interval so a second runner cannot claim the same job.
    lease_seconds = max(lease_seconds, timeout + 60)
    if not claim_owner(state_dir, owner, lease_seconds=lease_seconds):
        return {"status": "failed", "failure_layer": "runner-owner-busy", "job_id": job_id}
    meta_path = state_dir / "meta.json"
    existing = _read_json(meta_path) if meta_path.is_file() else {}
    session_id = existing.get("session_id") or _read_session_file(state_dir / "session-id.txt")
    attempt_start = int(existing.get("attempt_count", 0))
    runner = executor or (lambda command, prompt: execute_codex(command, prompt, cwd=root, timeout=timeout))
    last_completion = existing.get("last_completion") or {"failure_layer": "needs-resume", "missing_goals": frozen_goals}
    owner_token = _owner_token(state_dir, owner)
    try:
        for offset in range(max_attempts):
            attempt = attempt_start + offset + 1
            prompt = initial_prompt if not session_id and attempt == 1 else build_completion_failure_prompt(last_completion)
            command = build_codex_command(codex_bin, root, prompt, session_id, sandbox)
            _write_json(meta_path, _meta(state_dir, job_id, "running", session_id, attempt, frozen_goals, owner_id=owner, owner_token=owner_token, last_completion=last_completion))
            try:
                observation = runner(command, prompt)
            except Exception as exc:
                observation = {"failure_layer": "runner-exception", "status": "failed", "message": ""}
                last_completion = {"status": "failed", "failure_layer": "runner-exception", "missing_goals": frozen_goals, "report_observed": False, "error_type": type(exc).__name__}
            observed_session = observation.get("session_id")
            if observed_session:
                try:
                    observed_session = _validate_session_id(str(observed_session))
                except RunnerError:
                    observed_session = None
                    last_completion = {"status": "failed", "failure_layer": "session-id-invalid", "missing_goals": frozen_goals, "report_observed": False}
                    observation = {"status": "failed", "failure_layer": "session-id-invalid", "message": ""}
                if observed_session is None:
                    pass
                elif session_id and observed_session != session_id:
                    last_completion = {"status": "failed", "failure_layer": "session-drift", "missing_goals": frozen_goals, "report_observed": False}
                    observation = {"status": "failed", "failure_layer": "session-drift", "message": ""}
                else:
                    session_id = observed_session
                    _write_text(state_dir / "session-id.txt", session_id + "\n")
            elif not session_id and str(observation.get("status", "")) not in {"awaiting_user_action", "failed"}:
                # A resumable task must not silently restart as a new session.
                observation = {"status": "failed", "failure_layer": "session-id-not-observed", "message": ""}
            message = str(observation.get("message", ""))
            failure_layer = str(observation.get("failure_layer", "none"))
            requested_status = str(observation.get("status", ""))
            if failure_layer == "none" and requested_status not in {"awaiting_user_action", "failed"}:
                completion = inspect_completion(message, frozen_goals)
            else:
                completion = {
                    "status": requested_status if requested_status in {"awaiting_user_action", "failed"} else "blocked",
                    "failure_layer": failure_layer,
                    "missing_goals": frozen_goals,
                    "report_observed": False,
                }
            if completion["status"] == "blocked" and failure_layer == "none":
                failure_layer = completion["failure_layer"]
            _write_text(state_dir / "last-message.txt", _safe_last_message(completion=completion, message=message))
            last_completion = completion
            recovery = classify_failure(failure_layer, http_status=observation.get("http_status"), message=observation.get("message", ""))
            if failure_layer == "none":
                recovery = {"recovery_class": "retryable", "failure_layer": "none", "http_status": None, "next_automatic_action": "resume-same-session"}
            retryable = bool(observation.get("retryable", recovery["recovery_class"] in {"retryable", "diagnose-once"}))
            terminal_status = completion["status"]
            if terminal_status == "passed":
                status = "completed"
                next_action = "stop-allow"
            elif terminal_status == "awaiting_user_action" or recovery["recovery_class"] == "awaiting-user-action":
                status = "awaiting_user_action"
                next_action = str(observation.get("next_automatic_action", recovery["next_automatic_action"]))
            elif terminal_status == "failed" or not retryable:
                status = "failed"
                next_action = recovery["next_automatic_action"]
            else:
                status = "needs_resume"
                next_action = "resume-same-session"
            progress = {
                "schema_version": PROGRESS_SCHEMA,
                "job_id": job_id,
                "attempt": attempt,
                "status": status,
                "session_id": session_id or "",
                "failure_layer": completion["failure_layer"],
                "evidence_ref": f"attempt-{attempt:04d}.json",
                "next_automatic_action": next_action,
                "raw_output_persisted": False,
                "message_sha256": hashlib.sha256(message.encode("utf-8", "replace")).hexdigest(),
                "recovery": {**recovery, **retry_schedule(attempt, retry_after_seconds=observation.get("retry_after_seconds"))},
            }
            _write_json(state_dir / f"attempt-{attempt:04d}.json", progress, fresh=True)
            _append_event(state_dir / "events.jsonl", {"schema_version": "ds-lite.autoresearch-event.v1", "job_id": job_id, "attempt": attempt, "status": status, "failure_layer": completion["failure_layer"], "session_id": session_id or "", "message_sha256": progress["message_sha256"], "raw_output_persisted": False})
            failure_prompt = build_completion_failure_prompt(completion)
            failure = dict(completion)
            failure.update({"schema_version": COMPLETION_FAILURE_SCHEMA, "job_id": job_id, "attempt": attempt, "next_automatic_action": next_action, "completion_failure_prompt": failure_prompt, "raw_output_persisted": False})
            if status != "completed":
                _write_json(state_dir / f"completion-failure-{attempt:04d}.json", failure, fresh=True)
            if status == "completed":
                result = _meta(state_dir, job_id, "completed", session_id, attempt, frozen_goals, owner_id=owner, owner_token=owner_token, completion_report=True, next_automatic_action=next_action, last_completion=completion)
                _write_json(meta_path, result)
                _write_json(state_dir / "summary.json", result, fresh=True)
                return result
            if status in {"awaiting_user_action", "failed"}:
                result = _meta(state_dir, job_id, status, session_id, attempt, frozen_goals, owner_id=owner, owner_token=owner_token, completion_report=False, next_automatic_action=next_action, last_completion=completion)
                _write_json(meta_path, result)
                return result
        result = _meta(state_dir, job_id, "needs_resume", session_id, attempt_start + max_attempts, frozen_goals, owner_id=owner, owner_token=owner_token, completion_report=False, next_automatic_action="resume-same-session", last_completion=last_completion, completion_failure_prompt=build_completion_failure_prompt(last_completion))
        _write_json(meta_path, result)
        return result
    finally:
        release_owner(state_dir, owner)


def status(root: Path, job_id: str) -> dict[str, Any]:
    return _read_json(_job_dir(root, job_id) / "meta.json")


def watch_job(*, root: Path, job_id: str, initial_prompt: str,
              frozen_goals: list[str], executor: Callable[[list[str], str], dict[str, Any]] | None = None,
              codex_bin: str = "codex", sandbox: str = "workspace-write", max_attempts: int = 3,
              lease_seconds: int = 120, owner_id: str | None = None, timeout: int = 900,
              state_dir: Path | None = None, poll_seconds: float = 0.0,
              max_batches: int | None = None) -> dict[str, Any]:
    """Keep resuming the same job until it reaches a terminal state.

    ``run_job`` is deliberately bounded so a Hook can make one observable
    continuation without holding the host forever.  ``watch_job`` is the
    external persistent-runner mode modeled on vendor ``runLoop``: a budget
    boundary produces ``needs_resume`` and the next batch resumes the same
    session.  ``max_batches`` exists only for deterministic tests and
    supervised operators; omitting it keeps the runner alive until completion,
    user action, or an unrecoverable failure.
    """
    if max_batches is not None and max_batches < 1:
        raise RunnerError("max_batches must be positive when supplied")
    batches = 0
    first_prompt = initial_prompt
    goals = list(frozen_goals)
    while True:
        result = run_job(
            root=root,
            job_id=job_id,
            initial_prompt=first_prompt,
            frozen_goals=goals,
            executor=executor,
            codex_bin=codex_bin,
            sandbox=sandbox,
            max_attempts=max_attempts,
            lease_seconds=lease_seconds,
            owner_id=owner_id,
            timeout=timeout,
            state_dir=state_dir,
        )
        batches += 1
        if result.get("status") != "needs_resume":
            return result
        if max_batches is not None and batches >= max_batches:
            return result
        if poll_seconds > 0:
            time.sleep(poll_seconds)
        first_prompt = "Continue the same DS Lite session and satisfy the remaining completion contract."
        goals = []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or resume a persistent DS Lite autoresearch session.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--root", required=True, type=Path)
    run.add_argument("--job-id", required=True)
    run.add_argument("--prompt", required=True)
    run.add_argument("--goal", action="append", required=True)
    run.add_argument("--codex-bin", default="codex")
    run.add_argument("--max-attempts", type=int, default=3)
    run.add_argument("--state-dir", type=Path)
    resume = sub.add_parser("resume")
    resume.add_argument("--root", required=True, type=Path)
    resume.add_argument("--job-id", required=True)
    resume.add_argument("--codex-bin", default="codex")
    resume.add_argument("--max-attempts", type=int, default=3)
    resume.add_argument("--state-dir", type=Path)
    watch = sub.add_parser("watch")
    watch.add_argument("--root", required=True, type=Path)
    watch.add_argument("--job-id", required=True)
    watch.add_argument("--prompt", required=True)
    watch.add_argument("--goal", action="append", required=True)
    watch.add_argument("--codex-bin", default="codex")
    watch.add_argument("--max-attempts", type=int, default=3)
    watch.add_argument("--max-batches", type=int)
    watch.add_argument("--poll-seconds", type=float, default=0.0)
    watch.add_argument("--state-dir", type=Path)
    view = sub.add_parser("status")
    view.add_argument("--root", required=True, type=Path)
    view.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = status(args.root, args.job_id)
        elif args.command == "resume":
            result = run_job(root=args.root, job_id=args.job_id, initial_prompt="Continue the same DS Lite session and satisfy the remaining completion contract.", frozen_goals=[], codex_bin=args.codex_bin, max_attempts=args.max_attempts, state_dir=args.state_dir)
        elif args.command == "watch":
            result = watch_job(root=args.root, job_id=args.job_id, initial_prompt=args.prompt, frozen_goals=args.goal, codex_bin=args.codex_bin, max_attempts=args.max_attempts, max_batches=args.max_batches, poll_seconds=args.poll_seconds, state_dir=args.state_dir)
        else:
            result = run_job(root=args.root, job_id=args.job_id, initial_prompt=args.prompt, frozen_goals=args.goal, codex_bin=args.codex_bin, max_attempts=args.max_attempts, state_dir=args.state_dir)
    except (OSError, UnicodeError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "failure_layer": "runner", "message": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
