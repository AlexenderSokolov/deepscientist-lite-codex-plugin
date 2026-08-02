#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA = "ds-lite.knowledge-proposal.v1"
REVIEW_STATUSES = {"pending", "accepted", "rejected", "withdrawn", "superseded"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SENSITIVE_KEYS = {"authorization", "cookie", "credential", "password", "secret", "token", "api_key"}


class KnowledgeError(ValueError):
    pass


def _safe_ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise KnowledgeError(f"{label} must be a non-empty reference")
    if value.startswith("external://"):
        return value
    posix = PurePosixPath(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts:
        raise KnowledgeError(f"{label} must be project-relative or external://")
    return posix.as_posix()


def _find_sensitive(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in SENSITIVE_KEYS or any(normalized.endswith(f"_{suffix}") for suffix in SENSITIVE_KEYS):
                return str(key)
            nested = _find_sensitive(item)
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _find_sensitive(item)
            if nested:
                return nested
    return None


def validate_proposal(payload: Any) -> dict[str, Any]:
    required = {
        "schema_version", "proposal_id", "target", "source_refs", "summary", "claims",
        "review_status", "review_ref", "created_at", "extensions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise KnowledgeError("knowledge proposal fields do not match ds-lite.knowledge-proposal.v1")
    if payload["schema_version"] != SCHEMA:
        raise KnowledgeError("knowledge proposal schema is unsupported")
    sensitive = _find_sensitive(payload)
    if sensitive:
        raise KnowledgeError(f"sensitive field is forbidden: {sensitive}")
    if not isinstance(payload["proposal_id"], str) or not ID_RE.fullmatch(payload["proposal_id"]):
        raise KnowledgeError("proposal_id is invalid")
    if not isinstance(payload["target"], str) or not ID_RE.fullmatch(payload["target"]):
        raise KnowledgeError("target is invalid")
    if not isinstance(payload["source_refs"], list) or not payload["source_refs"]:
        raise KnowledgeError("source_refs must be non-empty")
    source_refs = [_safe_ref(value, "source_refs") for value in payload["source_refs"]]
    if len(source_refs) != len(set(source_refs)):
        raise KnowledgeError("source_refs contains duplicates")
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise KnowledgeError("summary must be non-empty")
    if not isinstance(payload["claims"], list):
        raise KnowledgeError("claims must be a list")
    for index, claim in enumerate(payload["claims"]):
        if not isinstance(claim, dict) or set(claim) != {"text", "source_refs", "uncertainty"}:
            raise KnowledgeError(f"claims[{index}] has invalid fields")
        if not isinstance(claim["text"], str) or not claim["text"].strip():
            raise KnowledgeError(f"claims[{index}].text must be non-empty")
        if not isinstance(claim["uncertainty"], str):
            raise KnowledgeError(f"claims[{index}].uncertainty must be a string")
        refs = [_safe_ref(value, f"claims[{index}].source_refs") for value in claim["source_refs"]]
        if not refs or not set(refs).issubset(source_refs):
            raise KnowledgeError(f"claims[{index}] must cite proposal source_refs")
    if payload["review_status"] not in REVIEW_STATUSES:
        raise KnowledgeError("review_status is invalid")
    review_ref = payload["review_ref"]
    if review_ref:
        _safe_ref(review_ref, "review_ref")
    if payload["review_status"] == "pending" and review_ref:
        raise KnowledgeError("pending proposals must not claim a review_ref")
    if payload["review_status"] != "pending" and not review_ref:
        raise KnowledgeError("terminal proposals require a review_ref")
    if not isinstance(payload["created_at"], str) or not payload["created_at"].endswith("Z"):
        raise KnowledgeError("created_at must be a UTC timestamp")
    return json.loads(json.dumps(payload))


def _adapt(input_payload: Any, adapter: str, target: str) -> list[dict[str, Any]]:
    if not isinstance(input_payload, dict):
        raise KnowledgeError("adapter input must be an object")
    expected_schema = f"ds-lite.{adapter}-handoff.v1"
    if input_payload.get("schema_version") != expected_schema:
        raise KnowledgeError(f"adapter input must use {expected_schema}")
    item_key = "items" if adapter == "tapestry" else "papers"
    items = input_payload.get(item_key)
    if not isinstance(items, list) or not items:
        raise KnowledgeError(f"{item_key} must be a non-empty list")
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise KnowledgeError(f"{item_key}[{index}] must be an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id):
            raise KnowledgeError(f"{item_key}[{index}].id is invalid")
        refs = item.get("source_refs")
        if not isinstance(refs, list) or not refs:
            raise KnowledgeError(f"{item_key}[{index}].source_refs must be non-empty")
        claims = item.get("claims", [])
        proposal = {
            "schema_version": SCHEMA,
            "proposal_id": f"{adapter}-{item_id}",
            "target": target,
            "source_refs": refs,
            "summary": item.get("summary", ""),
            "claims": claims,
            "review_status": "pending",
            "review_ref": "",
            "created_at": created_at,
            "extensions": {
                "adapter": adapter,
                "upstream_item_id": item_id,
                "upstream_title": item.get("title", ""),
            },
        }
        proposals.append(validate_proposal(proposal))
    return proposals


def _write_fresh(path: Path, payload: Any) -> None:
    package_root = Path(__file__).resolve().parents[1]
    resolved = path.expanduser().resolve()
    if package_root == resolved or package_root in resolved.parents:
        raise KnowledgeError("knowledge output must not be written inside the installed plugin")
    if resolved.exists():
        raise KnowledgeError("output already exists; refusing overwrite")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _external_doctor() -> dict[str, Any]:
    tapestry = shutil.which("tapestry") or shutil.which("tapestry-cli")
    scholar = shutil.which("scholaraio") or shutil.which("scholar-aio")
    return {
        "schema_version": "ds-lite.knowledge-doctor.v1",
        "status": "passed" if tapestry or scholar else "not-observed",
        "backends": {
            "tapestry": {"executable": tapestry, "status": "available" if tapestry else "not-observed"},
            "scholaraio": {"executable": scholar, "status": "available" if scholar else "not-observed"},
        },
        "storage_boundary": "external",
        "review_required": True,
    }


def _pull_export(adapter: str, export_path: str, target: str, output: str) -> dict[str, Any]:
    path = Path(export_path).expanduser().resolve()
    if not path.is_file():
        raise KnowledgeError("external export is unavailable; adapter is not observed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    proposals = _adapt(payload, adapter, target)
    envelope = {"schema_version": "ds-lite.knowledge-proposal-batch.v1", "adapter": adapter, "review_status": "pending", "proposals": proposals}
    _write_fresh(Path(output), envelope)
    return {"status": "passed", "adapter": adapter, "proposal_count": len(proposals), "observed": "external-export"}


def _transition(input_path: str, output_path: str, status: str, review_ref: str) -> dict[str, Any]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    validate_proposal(payload)
    if not review_ref:
        raise KnowledgeError("a target-native review_ref is required for a terminal transition")
    payload["review_status"] = status
    payload["review_ref"] = _safe_ref(review_ref, "review_ref")
    _write_fresh(Path(output_path), payload)
    return {"status": "passed", "review_status": status, "output": str(output_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and adapt review-gated DS Lite knowledge proposals.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--path", required=True)
    for command in ("adapt-tapestry", "adapt-scholaraio"):
        child = sub.add_parser(command)
        child.add_argument("--input", required=True)
        child.add_argument("--target", required=True)
        child.add_argument("--output", required=True)
    sub.add_parser("doctor")
    for command in ("pull-tapestry", "pull-scholaraio"):
        child = sub.add_parser(command)
        child.add_argument("--export")
        child.add_argument("--target", required=True)
        child.add_argument("--output", required=True)
    propose = sub.add_parser("propose")
    propose.add_argument("--input", required=True)
    propose.add_argument("--output", required=True)
    for command in ("withdraw", "supersede"):
        child = sub.add_parser(command)
        child.add_argument("--input", required=True)
        child.add_argument("--output", required=True)
        child.add_argument("--review-ref", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = _external_doctor()
            if result["status"] != "passed":
                print(json.dumps(result, ensure_ascii=False))
                return 2
        elif args.command == "validate":
            validate_proposal(json.loads(Path(args.path).read_text(encoding="utf-8")))
            result = {"status": "passed", "schema_version": SCHEMA}
        elif args.command == "propose":
            payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
            validate_proposal(payload)
            _write_fresh(Path(args.output), payload)
            result = {"status": "passed", "review_status": payload["review_status"]}
        elif args.command in {"withdraw", "supersede"}:
            result = _transition(args.input, args.output, args.command, args.review_ref)
        elif args.command in {"pull-tapestry", "pull-scholaraio"}:
            if not args.export:
                result = {"status": "blocked", "reason": "external-adapter-not-observed", "adapter": args.command.removeprefix("pull-")}
                print(json.dumps(result, ensure_ascii=False))
                return 2
            result = _pull_export(args.command.removeprefix("pull-"), args.export, args.target, args.output)
        else:
            adapter = args.command.removeprefix("adapt-")
            proposals = _adapt(json.loads(Path(args.input).read_text(encoding="utf-8")), adapter, args.target)
            envelope = {
                "schema_version": "ds-lite.knowledge-proposal-batch.v1",
                "adapter": adapter,
                "review_status": "pending",
                "proposals": proposals,
            }
            _write_fresh(Path(args.output), envelope)
            result = {"status": "passed", "adapter": adapter, "proposal_count": len(proposals)}
    except (OSError, UnicodeError, json.JSONDecodeError, KnowledgeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
