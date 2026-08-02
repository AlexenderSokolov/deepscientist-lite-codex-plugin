#!/usr/bin/env python3
"""Deterministic communication self-audit records for DeepScientist Lite.

The audit is a receipt of observable checks. It is deliberately not a model
judge and never records hidden reasoning or a scientific-truth assertion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable


SCHEMA_VERSION = "ds-lite.communication-audit.v1"
AUDIT_DIR = Path("research/artifacts")
TOP_LEVEL_FIELDS = {
    "schema_version", "audit_id", "skill", "task_class", "profile", "detail_mode",
    "checks", "claims", "protected_content", "handoff", "self_check", "result", "extensions",
}
CHECK_IDS = tuple(f"honor-{index:02d}" for index in range(1, 9))
CHECK_STATUSES = {"pending", "pass", "fail", "not-applicable"}
CLAIM_KINDS = {"read", "changed", "tested", "verified", "fixed", "completed"}
CLAIM_STATUSES = {"supported", "unsupported", "planned", "not-verified"}
RESULT_STATUSES = {"in-progress", "completed", "blocked", "failed"}
PROTECTED_STATUSES = {"unchanged", "changed", "not-applicable"}
HIDDEN_KEYS = {"thought", "chain_of_thought", "hidden_thought", "reasoning_trace", "private_reasoning"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_RE = re.compile(
    r"(?ix)"
    r"(?P<label>\b(?:password|token|secret|api[_-]?key|authorization)\b)"
    r"(?P<separator>\s*[:=]\s*|\s+)"
    r"(?P<value>Bearer\s+(?:\"[^\"]*\"|'[^']*'|[^\s]+)|\"[^\"]*\"|'[^']*'|[^\s]+)"
    r"|(?P<bearer>\bBearer\s+)(?P<bearer_value>\"[^\"]*\"|'[^']*'|[^\s]+)"
)
REDACTED_VALUE_RE = re.compile(
    r"(?ix)(?:\b(?:password|token|secret|api[_-]?key|authorization)\b"
    r"(?:\s*[:=]\s*|\s+)<redacted>|\bBearer\s+<redacted>)"
)


class AuditError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def is_absolute(raw: str) -> bool:
    return Path(raw).expanduser().is_absolute() or PureWindowsPath(raw).is_absolute()


def project_relative(root: Path, raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise AuditError("path must not be empty")
    if is_absolute(value) or value.replace("\\", "/").startswith("external://"):
        raise AuditError(f"absolute or external path is forbidden: {value}")
    normalized = PurePosixPath(value.replace("\\", "/"))
    if not normalized.parts or any(part in {"", ".", ".."} for part in normalized.parts):
        raise AuditError(f"path must be normalized and project-relative: {value}")
    return normalized.as_posix()


def audit_path(root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / value
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise AuditError("audit path must be inside the project") from exc
    if relative.parent.as_posix() != AUDIT_DIR.as_posix() or not relative.name.startswith("communication-audit-"):
        raise AuditError("audit must be research/artifacts/communication-audit-<id>.json")
    return resolved


def load(root: Path, value: str) -> tuple[Path, dict[str, Any]]:
    path = audit_path(root, value)
    if not path.exists():
        raise AuditError(f"audit not found: {path.relative_to(root.resolve()).as_posix()}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read audit JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditError("audit must be a JSON object")
    return path, payload


def relative_display(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def file_sha256(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise AuditError(f"evidence file does not exist: {relative}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_file(root: Path, raw_path: str, supplied_hash: str | None = None) -> dict[str, str]:
    relative = project_relative(root, raw_path)
    observed = file_sha256(root, relative)
    if supplied_hash and supplied_hash.lower() != observed:
        raise AuditError(f"SHA-256 mismatch for {relative}: expected {supplied_hash}, observed {observed}")
    return {"path": relative, "sha256": observed}


def redact_command(command: str) -> str:
    """Keep command shape while removing inline credential values."""
    def replace(match: re.Match[str]) -> str:
        if match.group("bearer"):
            return match.group("bearer") + "<redacted>"
        return match.group("label") + match.group("separator") + "<redacted>"

    return SECRET_RE.sub(replace, command)


def command_evidence(command: str, exit_code: int | None, result: str, observed: bool) -> dict[str, Any]:
    if not command.strip():
        raise AuditError("command evidence requires a command")
    if exit_code is None:
        raise AuditError("command evidence requires --exit-code")
    if not observed:
        raise AuditError("command evidence must be marked observed")
    if result not in {"pass", "fail", "blocked", "not-run"}:
        raise AuditError("command result must be pass, fail, blocked, or not-run")
    redacted = redact_command(command)
    return {
        "command": redacted,
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "redacted_command_sha256": hashlib.sha256(redacted.encode("utf-8")).hexdigest(),
        "exit_code": exit_code,
        "observed": True,
        "result": result,
    }


def blank_audit(audit_id: str, skill: str, task_class: str, profile: str, detail_mode: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_id": audit_id,
        "skill": skill,
        "task_class": task_class,
        "profile": profile,
        "detail_mode": detail_mode,
        "checks": [
            {"id": check_id, "status": "pending", "reason": "", "evidence": [], "test_refs": []}
            for check_id in CHECK_IDS
        ],
        "claims": [],
        "protected_content": [],
        "handoff": {
            "status": "pending", "summary": "", "evidence_paths": [], "verification": [],
            "limitations": [], "next_step": "",
        },
        "self_check": {
            "before": {"status": "pending", "items": []},
            "after": {"status": "pending", "items": []},
            "before_handoff": {"status": "pending", "items": []},
        },
        "result": {"status": "in-progress", "summary": "", "failure_category": ""},
        "extensions": {},
    }


def _check_path_value(key: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, str):
        return
    looks_like_path = key.endswith("path") or key.endswith("paths") or key in {"path", "source_path", "local_refs", "evidence_paths"}
    if looks_like_path and (is_absolute(value) or value.replace("\\", "/").startswith("external://")):
        errors.append(f"absolute or external path in {key}: {value}")


def _walk_for_forbidden(value: Any, errors: list[str], key: str = "") -> None:
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key in HIDDEN_KEYS:
                errors.append(f"hidden reasoning field is forbidden: {item_key}")
            _check_path_value(item_key, item_value, errors)
            _walk_for_forbidden(item_value, errors, item_key)
    elif isinstance(value, list):
        for item in value:
            _walk_for_forbidden(item, errors, key)
    elif isinstance(value, str):
        _check_path_value(key, value, errors)


def _has_passing_evidence(kind: str, evidence: Any) -> bool:
    if not isinstance(evidence, list):
        return False
    for item in evidence:
        if not isinstance(item, dict):
            continue
        if kind in {"read", "changed"} and "path" in item and "sha256" in item:
            return True
        if kind in {"tested", "verified", "fixed", "completed"} and (
            item.get("command")
            and item.get("command_sha256")
            and item.get("observed") is True
            and item.get("exit_code") == 0
            and item.get("result") == "pass"
        ):
            return True
    return False


def _validate_evidence(root: Path, evidence: Any, location: str, errors: list[str]) -> None:
    if not isinstance(evidence, list):
        errors.append(f"{location}.evidence must be a list")
        return
    for index, item in enumerate(evidence):
        where = f"{location}.evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        if "path" in item:
            raw = item.get("path")
            try:
                relative = project_relative(root, raw)
                if not isinstance(item.get("sha256"), str) or not SHA256_RE.fullmatch(item["sha256"].lower()):
                    errors.append(f"{where} file evidence requires a lowercase SHA-256")
                elif Path(root / relative).is_file() and file_sha256(root, relative) != item["sha256"].lower():
                    errors.append(f"{where} SHA-256 does not match {relative}")
                elif not (root / relative).is_file():
                    errors.append(f"{where} file does not exist: {relative}")
            except (AuditError, TypeError) as exc:
                errors.append(f"{where}: {exc}")
        if "command" in item:
            command = item.get("command")
            if not isinstance(command, str) or not command.strip():
                errors.append(f"{where} command is empty")
            raw_hash = item.get("command_sha256")
            if not isinstance(raw_hash, str) or not SHA256_RE.fullmatch(raw_hash.lower()):
                errors.append(f"{where} command_sha256 is missing or invalid")
            elif isinstance(command, str):
                redacted_hash = item.get("redacted_command_sha256")
                if not isinstance(redacted_hash, str) or not SHA256_RE.fullmatch(redacted_hash.lower()):
                    errors.append(f"{where} redacted_command_sha256 is missing or invalid")
                elif redacted_hash.lower() != hashlib.sha256(command.encode("utf-8")).hexdigest():
                    errors.append(f"{where} redacted_command_sha256 does not match the stored command")
                if redact_command(command) != command:
                    errors.append(f"{where} command contains an unredacted secret value")
                elif not REDACTED_VALUE_RE.search(command) and raw_hash.lower() != hashlib.sha256(command.encode("utf-8")).hexdigest():
                    errors.append(f"{where} command_sha256 does not match the stored command")
            if not isinstance(item.get("exit_code"), int):
                errors.append(f"{where} command exit_code is missing or invalid")
            if item.get("observed") is not True:
                errors.append(f"{where} command result is not observed")
            if item.get("result") not in {"pass", "fail", "blocked", "not-run"}:
                errors.append(f"{where} command result is invalid")


def validate_payload(root: Path, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown = set(payload) - TOP_LEVEL_FIELDS
    missing = TOP_LEVEL_FIELDS - set(payload)
    if unknown:
        errors.append("unknown top-level fields: " + ", ".join(sorted(unknown)))
    if missing:
        errors.append("missing top-level fields: " + ", ".join(sorted(missing)))
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(payload.get("audit_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", payload.get("audit_id", "")):
        errors.append("audit_id must be a simple identifier")
    if payload.get("detail_mode") not in {"adaptive", "concise", "deep"}:
        errors.append("detail_mode must be adaptive, concise, or deep")
    if payload.get("result", {}).get("status") not in RESULT_STATUSES if isinstance(payload.get("result"), dict) else True:
        errors.append("result.status is invalid")

    checks = payload.get("checks")
    if not isinstance(checks, list):
        errors.append("checks must be a list")
    else:
        ids = [item.get("id") for item in checks if isinstance(item, dict)]
        if ids != list(CHECK_IDS):
            errors.append("checks must contain honor-01 through honor-08 exactly once and in order")
        for index, item in enumerate(checks):
            if not isinstance(item, dict):
                errors.append(f"checks[{index}] must be an object")
                continue
            if item.get("status") not in CHECK_STATUSES:
                errors.append(f"checks[{index}].status is invalid")
            if not isinstance(item.get("reason"), str):
                errors.append(f"checks[{index}].reason must be a string")
            elif item.get("status") == "not-applicable" and not item.get("reason", "").strip():
                errors.append(f"checks[{index}] not-applicable status requires a reason")
            _validate_evidence(root, item.get("evidence"), f"checks[{index}]", errors)

    claims = payload.get("claims")
    if not isinstance(claims, list):
        errors.append("claims must be a list")
    else:
        claim_ids: set[str] = set()
        for index, item in enumerate(claims):
            where = f"claims[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{where} must be an object")
                continue
            if item.get("id") in claim_ids:
                errors.append(f"duplicate claim id: {item.get('id')}")
            claim_ids.add(str(item.get("id")))
            if item.get("kind") not in CLAIM_KINDS:
                errors.append(f"{where}.kind is invalid")
            if item.get("status") not in CLAIM_STATUSES:
                errors.append(f"{where}.status is invalid")
            if not isinstance(item.get("reason", ""), str):
                errors.append(f"{where}.reason must be a string")
            if "evidence" not in item and item.get("status") in {"unsupported", "planned", "not-verified"}:
                item = {**item, "evidence": []}
            _validate_evidence(root, item.get("evidence"), where, errors)
            if item.get("status") == "supported" and item.get("kind") in CLAIM_KINDS and not _has_passing_evidence(item["kind"], item.get("evidence")):
                expected = "project-relative file evidence" if item["kind"] in {"read", "changed"} else "passing observed command evidence"
                errors.append(f"{where} supported {item.get('kind')} claim requires {expected}")

    protected = payload.get("protected_content")
    if not isinstance(protected, list):
        errors.append("protected_content must be a list")
    else:
        protected_ids: set[str] = set()
        for index, item in enumerate(protected):
            where = f"protected_content[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{where} must be an object")
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                errors.append(f"{where}.id is required")
            elif item_id in protected_ids:
                errors.append(f"duplicate protected content id: {item_id}")
            protected_ids.add(str(item_id))
            if item.get("status") not in PROTECTED_STATUSES:
                errors.append(f"{where}.status is invalid")
            before = item.get("before_sha256")
            after = item.get("after_sha256")
            if item.get("status") != "not-applicable":
                if not isinstance(before, str) or not SHA256_RE.fullmatch(before.lower()):
                    errors.append(f"{where}.before_sha256 is invalid")
                if not isinstance(after, str) or not SHA256_RE.fullmatch(after.lower()):
                    errors.append(f"{where}.after_sha256 is invalid")
            if item.get("status") == "unchanged" and before != after:
                errors.append(f"{where} says unchanged but hashes differ")
            if item.get("status") == "changed" and before == after:
                errors.append(f"{where} says changed but hashes match")

    handoff = payload.get("handoff")
    if not isinstance(handoff, dict):
        errors.append("handoff must be an object")
    else:
        for key in ("summary", "next_step"):
            if not isinstance(handoff.get(key), str):
                errors.append(f"handoff.{key} must be a string")
        for key in ("evidence_paths", "verification", "limitations"):
            if not isinstance(handoff.get(key), list):
                errors.append(f"handoff.{key} must be a list")
            else:
                for value in handoff[key]:
                    if key == "evidence_paths":
                        try:
                            project_relative(root, value)
                        except (AuditError, TypeError) as exc:
                            errors.append(f"handoff.{key}: {exc}")

    self_check = payload.get("self_check")
    if not isinstance(self_check, dict):
        errors.append("self_check must be an object")
    else:
        for phase in ("before", "after", "before_handoff"):
            item = self_check.get(phase)
            if not isinstance(item, dict) or item.get("status") not in {"pending", "recorded"} or not isinstance(item.get("items"), list):
                errors.append(f"self_check.{phase} is invalid")
    _walk_for_forbidden(payload, errors)
    return errors


def require_valid(root: Path, payload: dict[str, Any]) -> None:
    errors = validate_payload(root, payload)
    if errors:
        raise AuditError("; ".join(errors))


def require_open(payload: dict[str, Any]) -> None:
    if payload.get("result", {}).get("status") != "in-progress":
        raise AuditError("communication audit is finalized; initialize a new audit before writing")


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    audit_id = args.id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    path = root / AUDIT_DIR / f"communication-audit-{audit_id}.json"
    if path.exists() and not args.allow_existing:
        raise AuditError(f"audit already exists: {relative_display(root, path)}")
    payload = blank_audit(audit_id, args.skill, args.task_class, args.profile, args.detail_mode)
    atomic_write(path, payload)
    return {"ok": True, "audit_path": relative_display(root, path), "audit_id": audit_id}


def update_self_check(payload: dict[str, Any], phase: str | None, note: str | None) -> None:
    if phase:
        if phase not in {"before", "after", "before_handoff"}:
            raise AuditError("self-check phase must be before, after, or before_handoff")
        item = payload["self_check"][phase]
        item["status"] = "recorded"
        if note:
            item.setdefault("items", []).append(note)


def cmd_record_check(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    path, payload = load(root, args.audit)
    require_valid(root, payload)
    require_open(payload)
    check = next((item for item in payload["checks"] if item["id"] == args.check_id), None)
    if check is None:
        raise AuditError(f"unknown check id: {args.check_id}")
    check["status"] = args.status
    check["reason"] = args.reason or check.get("reason", "")
    if args.evidence_path:
        check.setdefault("evidence", []).append(evidence_file(root, args.evidence_path, args.sha256))
    elif args.sha256:
        raise AuditError("--sha256 requires --evidence-path")
    if args.command_text:
        check.setdefault("evidence", []).append(command_evidence(args.command_text, args.exit_code, args.command_result, args.observed))
    if args.protected_id:
        protected = {
            "id": args.protected_id,
            "kind": args.protected_kind,
            "before_sha256": args.protected_before_sha256 or "",
            "after_sha256": args.protected_after_sha256 or "",
            "status": args.protected_status,
            "reason": args.protected_reason or "",
        }
        existing = next((item for item in payload["protected_content"] if item.get("id") == args.protected_id), None)
        if existing is None:
            payload["protected_content"].append(protected)
        else:
            existing.update(protected)
    update_self_check(payload, args.self_phase, args.self_note)
    require_valid(root, payload)
    atomic_write(path, payload)
    return {"ok": True, "audit_path": relative_display(root, path), "check_id": args.check_id, "status": args.status}


def cmd_record_claim(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    path, payload = load(root, args.audit)
    require_valid(root, payload)
    require_open(payload)
    item = next((claim for claim in payload["claims"] if claim.get("id") == args.claim_id), None)
    if item is None:
        item = {"id": args.claim_id, "kind": args.kind, "status": args.status, "reason": args.reason or "", "evidence": []}
        payload["claims"].append(item)
    else:
        item.update({"kind": args.kind, "status": args.status, "reason": args.reason or item.get("reason", "")})
    if args.evidence_path:
        item.setdefault("evidence", []).append(evidence_file(root, args.evidence_path, args.sha256))
    elif args.sha256:
        raise AuditError("--sha256 requires --evidence-path")
    if args.command_text:
        item.setdefault("evidence", []).append(command_evidence(args.command_text, args.exit_code, args.command_result, args.observed))
    require_valid(root, payload)
    atomic_write(path, payload)
    return {"ok": True, "audit_path": relative_display(root, path), "claim_id": args.claim_id, "status": args.status}


def cmd_finalize(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    path, payload = load(root, args.audit)
    require_valid(root, payload)
    require_open(payload)
    if args.result not in {"completed", "blocked", "failed"}:
        raise AuditError("final result must be completed, blocked, or failed")
    check_statuses = {item["status"] for item in payload["checks"]}
    if "pending" in check_statuses:
        raise AuditError("cannot finalize audit while a check is pending")
    if args.result == "completed" and not check_statuses.issubset({"pass", "not-applicable"}):
        raise AuditError("cannot complete audit while a check is pending or failed")
    if args.result == "completed" and any(claim.get("status") != "supported" for claim in payload["claims"]):
        raise AuditError("cannot complete audit with unsupported or unverified claims")
    protected = payload["protected_content"]
    if args.result == "completed" and any(item.get("status") == "changed" for item in protected):
        raise AuditError("cannot complete audit while protected content changed")
    if args.result == "completed" and payload.get("task_class") == "academic-rewrite" and not protected:
        raise AuditError("academic rewrite requires a protected-content comparison or not-applicable record")
    for phase in ("before", "after", "before_handoff"):
        if payload["self_check"][phase]["status"] != "recorded":
            raise AuditError(f"self_check.{phase} must be recorded before finalize")
        if payload.get("detail_mode") == "deep" and not payload["self_check"][phase].get("items"):
            raise AuditError(f"self_check.{phase} requires an observed item in deep mode")
    handoff = payload["handoff"]
    if args.summary:
        handoff["summary"] = args.summary
    if args.next_step:
        handoff["next_step"] = args.next_step
    if args.limitation:
        handoff.setdefault("limitations", []).extend(args.limitation)
    if args.verification:
        handoff.setdefault("verification", []).extend(args.verification)
    if not handoff.get("summary") or not handoff.get("next_step"):
        raise AuditError("handoff requires summary and next_step")
    high_risk = payload.get("detail_mode") == "deep" or payload.get("task_class") in {
        "repository-change", "diagnosis", "academic-rewrite", "methodological-reflection", "blocked-execution",
    }
    if args.result == "completed" and high_risk and not handoff.get("verification"):
        raise AuditError("completed high-risk handoff requires explicit verification")
    if high_risk and not handoff.get("limitations"):
        raise AuditError("high-risk handoff requires explicit limitations, including an explicit none-observed entry")
    if args.result == "completed" and not any(
        claim.get("kind") == "completed" and claim.get("status") == "supported"
        for claim in payload["claims"]
    ):
        raise AuditError("cannot complete audit without a supported completed claim")
    handoff["status"] = "recorded"
    payload["result"] = {"status": args.result, "summary": handoff["summary"], "failure_category": args.failure_category or ""}
    require_valid(root, payload)
    atomic_write(path, payload)
    return {"ok": True, "audit_path": relative_display(root, path), "result": args.result}


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    path, payload = load(root, args.audit)
    errors = validate_payload(root, payload)
    return {"ok": not errors, "audit_path": relative_display(root, path), "errors": errors}


def render_payload(root: Path, payload: dict[str, Any]) -> str:
    lines = [
        f"# Communication Audit `{payload['audit_id']}`", "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Skill: `{payload['skill']}`",
        f"- Task class: `{payload['task_class']}`",
        f"- Profile/detail: `{payload['profile']}` / `{payload['detail_mode']}`",
        f"- Result: **{payload['result']['status']}**", "", "## Eight checks", "",
    ]
    for item in payload["checks"]:
        lines.append(f"- `{item['id']}`: **{item['status']}** - {item.get('reason') or 'no reason recorded'}")
        for evidence in item.get("evidence", []):
            if "path" in evidence:
                lines.append(f"  - file `{evidence['path']}` sha256 `{evidence['sha256']}`")
            elif "command" in evidence:
                lines.append(f"  - command `{evidence['command']}` exit `{evidence['exit_code']}` result `{evidence['result']}`")
    lines.extend(["", "## Handoff", "", payload["handoff"].get("summary", "(pending)"), ""])
    lines.append(f"- Next step: {payload['handoff'].get('next_step') or '(pending)'}")
    if payload["handoff"].get("limitations"):
        lines.append("- Limitations: " + "; ".join(payload["handoff"]["limitations"]))
    lines.extend(["", "## Claims", ""])
    for claim in payload["claims"]:
        lines.append(f"- `{claim.get('id')}` `{claim.get('kind')}`: **{claim.get('status')}** - {claim.get('reason') or ''}")
    return "\n".join(lines) + "\n"


def cmd_render(args: argparse.Namespace) -> str:
    root = Path(args.root).expanduser().resolve()
    _, payload = load(root, args.audit)
    require_valid(root, payload)
    return render_payload(root, payload)


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage ds-lite.communication-audit.v1 receipts.")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    init = sub.add_parser("init")
    init.add_argument("--root", required=True)
    init.add_argument("--skill", required=True)
    init.add_argument("--task-class", required=True)
    init.add_argument("--profile", default="research-peer")
    init.add_argument("--detail-mode", default="adaptive", choices=("adaptive", "concise", "deep"))
    init.add_argument("--id")
    init.add_argument("--allow-existing", action="store_true")

    for name in ("record-check", "record-claim"):
        command = sub.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--audit", required=True)
        command.add_argument("--reason")
        command.add_argument("--evidence-path")
        command.add_argument("--sha256")
        command.add_argument("--command", dest="command_text")
        command.add_argument("--exit-code", type=int)
        command.add_argument("--command-result", default="pass", choices=("pass", "fail", "blocked", "not-run"))
        command.add_argument("--observed", action="store_true")
        if name == "record-check":
            command.add_argument("--check-id", required=True, choices=CHECK_IDS)
            command.add_argument("--status", required=True, choices=tuple(sorted(CHECK_STATUSES - {"pending"})))
            command.add_argument("--self-phase", choices=("before", "after", "before_handoff"))
            command.add_argument("--self-note")
            command.add_argument("--protected-id")
            command.add_argument("--protected-kind", default="structured-content")
            command.add_argument("--protected-before-sha256")
            command.add_argument("--protected-after-sha256")
            command.add_argument("--protected-status", choices=tuple(sorted(PROTECTED_STATUSES)), default="unchanged")
            command.add_argument("--protected-reason")
        else:
            command.add_argument("--claim-id", required=True)
            command.add_argument("--kind", required=True, choices=tuple(sorted(CLAIM_KINDS)))
            command.add_argument("--status", required=True, choices=tuple(sorted(CLAIM_STATUSES)))

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--root", required=True)
    finalize.add_argument("--audit", required=True)
    finalize.add_argument("--result", required=True, choices=("completed", "blocked", "failed"))
    finalize.add_argument("--summary")
    finalize.add_argument("--next-step")
    finalize.add_argument("--limitation", action="append", default=[])
    finalize.add_argument("--verification", action="append", default=[])
    finalize.add_argument("--failure-category")

    for name in ("validate", "render"):
        command = sub.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--audit", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (AttributeError, OSError):
                pass
    args = parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.subcommand == "init":
            output: Any = cmd_init(args)
        elif args.subcommand == "record-check":
            output = cmd_record_check(args)
        elif args.subcommand == "record-claim":
            output = cmd_record_claim(args)
        elif args.subcommand == "finalize":
            output = cmd_finalize(args)
        elif args.subcommand == "validate":
            output = cmd_validate(args)
        else:
            output = cmd_render(args)
        if isinstance(output, str):
            print(output, end="")
        else:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if not isinstance(output, dict) or output.get("ok", True) else 1
    except (AuditError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
