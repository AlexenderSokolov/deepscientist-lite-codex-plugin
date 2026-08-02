#!/usr/bin/env python3
"""Auditable user-action requests for host capabilities outside Core's authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


REQUEST_SCHEMA = "ds-lite.user-action-request.v1"
RESPONSE_SCHEMA = "ds-lite.user-action-response.v1"
RESOLUTION_SCHEMA = "ds-lite.agent-action-resolution.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SENSITIVE = re.compile(r"(?i)(password|token|secret|api[_-]?key|authorization|cookie|credential|prompt|jsonl)")


class UserActionError(ValueError):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rel(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserActionError(f"{label} must be non-empty")
    if PurePosixPath(value.replace("\\", "/")).is_absolute() or PureWindowsPath(value).is_absolute():
        raise UserActionError(f"{label} must be project-relative")
    path = PurePosixPath(value.replace("\\", "/"))
    if ".." in path.parts:
        raise UserActionError(f"{label} must not escape the project")
    return path.as_posix()


def _safe_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserActionError(f"{label} must be non-empty text")
    if SENSITIVE.search(value):
        raise UserActionError(f"{label} contains a sensitive marker")
    if re.search(r"[A-Za-z]:[\\/]", value) or value.startswith("/"):
        raise UserActionError(f"{label} must not contain an absolute workstation path")
    return value.strip()


def request_dir(root: Path) -> Path:
    return root / "research" / "artifacts"


def request_path(root: Path, request_id: str) -> Path:
    return request_dir(root) / f"user-action-request-{request_id}.json"


def response_path(root: Path, request_id: str) -> Path:
    return request_dir(root) / f"user-action-response-{request_id}.json"


def resolution_path(root: Path, request_id: str) -> Path:
    return request_dir(root) / f"agent-action-resolution-{request_id}.json"


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise UserActionError(f"refusing to overwrite existing artifact: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def validate_request(payload: Any) -> dict[str, Any]:
    required = {
        "schema_version", "request_id", "status", "blocking_reason", "required_user_action",
        "exact_action", "allowed_paths", "budget", "external_boundary", "expected_receipt",
        "expires_at", "forbidden_actions", "next_action", "created_at", "extensions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise UserActionError("request fields do not match ds-lite.user-action-request.v1")
    if payload["schema_version"] != REQUEST_SCHEMA or payload["status"] != "pending":
        raise UserActionError("request is not pending")
    if not ID_RE.fullmatch(str(payload["request_id"])):
        raise UserActionError("request_id is invalid")
    for field in ("blocking_reason", "required_user_action", "exact_action", "external_boundary", "expected_receipt", "next_action"):
        _safe_text(payload[field], field)
    if not isinstance(payload["allowed_paths"], list):
        raise UserActionError("allowed_paths must be a list")
    for index, value in enumerate(payload["allowed_paths"]):
        _rel(value, f"allowed_paths[{index}]")
    if not isinstance(payload["forbidden_actions"], list) or not payload["forbidden_actions"]:
        raise UserActionError("forbidden_actions must be a non-empty list")
    for index, value in enumerate(payload["forbidden_actions"]):
        _safe_text(value, f"forbidden_actions[{index}]")
    if not isinstance(payload["budget"], dict) or not payload["budget"]:
        raise UserActionError("budget must be an object")
    for key, value in payload["budget"].items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", key) or not isinstance(value, (int, float, str)):
            raise UserActionError("budget contains invalid values")
    if not isinstance(payload["extensions"], dict):
        raise UserActionError("extensions must be an object")
    return payload


def validate_response(payload: Any) -> dict[str, Any]:
    required = {"schema_version", "response_id", "request_id", "decision", "scope", "receipt_ref", "recorded_at", "status", "extensions"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise UserActionError("response fields do not match ds-lite.user-action-response.v1")
    if payload["schema_version"] != RESPONSE_SCHEMA or not ID_RE.fullmatch(str(payload["response_id"])) or not ID_RE.fullmatch(str(payload["request_id"])):
        raise UserActionError("response identifiers are invalid")
    if payload["decision"] not in {"allow", "deny"} or payload["status"] not in {"available", "consumed", "denied"}:
        raise UserActionError("response decision or status is invalid")
    _safe_text(payload["scope"], "scope")
    _rel(payload["receipt_ref"], "receipt_ref")
    if not isinstance(payload["extensions"], dict):
        raise UserActionError("extensions must be an object")
    return payload


def validate_resolution(payload: Any) -> dict[str, Any]:
    required = {"schema_version", "resolution_id", "request_id", "status", "reason", "verification", "recorded_at", "extensions"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise UserActionError("resolution fields do not match ds-lite.agent-action-resolution.v1")
    if payload["schema_version"] != RESOLUTION_SCHEMA or payload["status"] != "resolved":
        raise UserActionError("resolution status is invalid")
    if not ID_RE.fullmatch(str(payload["resolution_id"])) or not ID_RE.fullmatch(str(payload["request_id"])):
        raise UserActionError("resolution identifiers are invalid")
    for field in ("reason", "verification"):
        _safe_text(payload[field], field)
    if not isinstance(payload["extensions"], dict):
        raise UserActionError("resolution extensions must be an object")
    return payload


def create_request(root: Path, *, reason: str, action: str, scope: str, expected_receipt: str, allowed_paths: list[str] | None = None, ttl_minutes: int = 30) -> dict[str, Any]:
    root = root.resolve()
    request_id = f"uar-{uuid.uuid4().hex[:16]}"
    created = now()
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "request_id": request_id,
        "status": "pending",
        "blocking_reason": _safe_text(reason, "blocking_reason"),
        "required_user_action": _safe_text(f"请确认一次 {scope} 操作，并回传该请求对应的 response receipt。", "required_user_action"),
        "exact_action": _safe_text(action, "exact_action"),
        "allowed_paths": [_rel(item, "allowed_path") for item in (allowed_paths or [])],
        "budget": {"actions": 1, "ttl_minutes": ttl_minutes},
        "external_boundary": _safe_text("仅限用户明确确认的公开资料或受信任宿主能力；禁止登录态、会话状态、表单、上传和密钥外发。", "external_boundary"),
        "expected_receipt": _safe_text(expected_receipt, "expected_receipt"),
        "expires_at": stamp(created + timedelta(minutes=ttl_minutes)),
        "forbidden_actions": ["不得扩大路径、时间、调用或费用预算", "不得重试或替换请求", "不得记录密钥、原始用户输入或完整事件流"],
        "next_action": _safe_text(f"用户执行：{action}；完成后记录 user-action-response-{request_id}.json。", "next_action"),
        "created_at": stamp(created),
        "extensions": {"scope": scope},
    }
    validate_request(payload)
    _write_once(request_path(root, request_id), payload)
    return payload


def record_response(root: Path, request_id: str, *, decision: str, scope: str, receipt_ref: str) -> dict[str, Any]:
    if not ID_RE.fullmatch(request_id):
        raise UserActionError("request_id is invalid")
    request = validate_request(json.loads(request_path(root, request_id).read_text(encoding="utf-8")))
    if decision not in {"allow", "deny"}:
        raise UserActionError("decision must be allow or deny")
    if scope != request["extensions"].get("scope"):
        raise UserActionError("response scope does not match request")
    payload = {
        "schema_version": RESPONSE_SCHEMA,
        "response_id": f"uar-response-{uuid.uuid4().hex[:16]}",
        "request_id": request_id,
        "decision": decision,
        "scope": _safe_text(scope, "scope"),
        "receipt_ref": _rel(receipt_ref, "receipt_ref"),
        "recorded_at": stamp(now()),
        "status": "available" if decision == "allow" else "denied",
        "extensions": {},
    }
    validate_response(payload)
    _write_once(response_path(root, request_id), payload)
    return payload


def record_resolution(root: Path, request_id: str, *, reason: str, verification: str) -> dict[str, Any]:
    if not ID_RE.fullmatch(request_id):
        raise UserActionError("request_id is invalid")
    request = validate_request(json.loads(request_path(root, request_id).read_text(encoding="utf-8")))
    if response_path(root, request_id).exists() or resolution_path(root, request_id).exists():
        raise UserActionError("request already has a terminal response or resolution")
    payload = {
        "schema_version": RESOLUTION_SCHEMA,
        "resolution_id": f"uar-resolution-{uuid.uuid4().hex[:16]}",
        "request_id": request["request_id"],
        "status": "resolved",
        "reason": _safe_text(reason, "reason"),
        "verification": _safe_text(verification, "verification"),
        "recorded_at": stamp(now()),
        "extensions": {"request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode("utf-8")).hexdigest()},
    }
    validate_resolution(payload)
    _write_once(resolution_path(root, request_id), payload)
    return payload


def load_pending(root: Path) -> tuple[dict[str, Any], Path] | None:
    directory = request_dir(root)
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("user-action-request-*.json")):
        response = response_path(root, path.stem.removeprefix("user-action-request-"))
        resolution = resolution_path(root, path.stem.removeprefix("user-action-request-"))
        try:
            request = validate_request(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, UserActionError):
            continue
        if now() >= datetime.fromisoformat(request["expires_at"].replace("Z", "+00:00")):
            continue
        if response.exists() or resolution.exists():
            continue
        return request, path
    return None


def consume(root: Path, request: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    validate_request(request)
    validate_response(response)
    if response["request_id"] != request["request_id"] or response["status"] != "available":
        raise UserActionError("response is stale, consumed, or mismatched")
    if response["decision"] != "allow":
        raise UserActionError("user denied the requested action")
    receipt = response_path(root, request["request_id"])
    updated = dict(response)
    updated["status"] = "consumed"
    updated["extensions"] = {
        **response["extensions"],
        "consumed_at": stamp(now()),
        "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    validate_response(updated)
    receipt.write_text(json.dumps(updated, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    req = sub.add_parser("request")
    req.add_argument("--root", required=True); req.add_argument("--reason", required=True); req.add_argument("--action", required=True)
    req.add_argument("--scope", required=True); req.add_argument("--expected-receipt", required=True); req.add_argument("--allowed-path", action="append", default=[])
    rsp = sub.add_parser("respond")
    rsp.add_argument("--root", required=True); rsp.add_argument("--request-id", required=True); rsp.add_argument("--decision", required=True); rsp.add_argument("--scope", required=True); rsp.add_argument("--receipt-ref", required=True)
    consume_parser = sub.add_parser("consume")
    consume_parser.add_argument("--root", required=True); consume_parser.add_argument("--request-id", required=True)
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--root", required=True); resolve.add_argument("--request-id", required=True)
    resolve.add_argument("--reason", required=True); resolve.add_argument("--verification", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "request":
            result = create_request(Path(args.root), reason=args.reason, action=args.action, scope=args.scope, expected_receipt=args.expected_receipt, allowed_paths=args.allowed_path)
        elif args.command == "respond":
            result = record_response(Path(args.root), args.request_id, decision=args.decision, scope=args.scope, receipt_ref=args.receipt_ref)
        elif args.command == "resolve":
            result = record_resolution(Path(args.root), args.request_id, reason=args.reason, verification=args.verification)
        else:
            root = Path(args.root)
            request = json.loads(request_path(root, args.request_id).read_text(encoding="utf-8"))
            response = json.loads(response_path(root, args.request_id).read_text(encoding="utf-8"))
            result = consume(root, request, response)
    except (OSError, UnicodeError, json.JSONDecodeError, UserActionError) as exc:
        schema = REQUEST_SCHEMA if args.command == "request" else RESPONSE_SCHEMA if args.command in {"respond", "consume"} else RESOLUTION_SCHEMA
        print(json.dumps({"schema_version": schema, "status": "blocked", "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
