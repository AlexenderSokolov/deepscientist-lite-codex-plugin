#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SPEC_SCHEMA = "ds-lite.empirical-spec.v1"
RESULT_SCHEMA = "ds-lite.empirical-result.v1"
CORE = {"plugin": "deepscientist-lite", "version": "0.10.0-beta.2"}
BACKEND_STATUSES = {"available", "unavailable", "not-observed"}
RESULT_STATUSES = {"completed", "partial", "blocked"}
CHECK_STATUSES = {"passed", "failed", "warning", "not-observed"}
ROBUSTNESS_STATUSES = {"agrees", "disagrees", "inconclusive", "not-observed"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class EmpiricalProtocolError(ValueError):
    pass


def _safe_ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EmpiricalProtocolError(f"{label} must be a non-empty project-relative reference")
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or PureWindowsPath(value).is_absolute() or ".." in posix.parts:
        raise EmpiricalProtocolError(f"{label} must be project-relative")
    return posix.as_posix()


def _strings(value: Any, label: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value) or not all(isinstance(item, str) and item.strip() for item in value):
        raise EmpiricalProtocolError(f"{label} must be a{' non-empty' if nonempty else ''} string list")
    return value


def _backend(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"name", "status"}:
        raise EmpiricalProtocolError("backend must contain name and status")
    if not isinstance(value["name"], str) or not value["name"] or value["status"] not in BACKEND_STATUSES:
        raise EmpiricalProtocolError("backend is invalid")


def validate_spec(payload: Any) -> dict[str, Any]:
    required = {
        "schema_version", "study_id", "research_question", "estimand", "population", "sample",
        "variables", "identification_strategy", "assumptions", "diagnostics", "robustness_plan",
        "backend", "data_refs", "extensions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise EmpiricalProtocolError("empirical spec fields are invalid")
    if payload["schema_version"] != SPEC_SCHEMA:
        raise EmpiricalProtocolError("empirical spec schema is unsupported")
    if not isinstance(payload["study_id"], str) or not ID_RE.fullmatch(payload["study_id"]):
        raise EmpiricalProtocolError("study_id is invalid")
    for key in ("research_question", "estimand", "population", "identification_strategy"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise EmpiricalProtocolError(f"{key} must be non-empty")
    if not isinstance(payload["sample"], dict) or set(payload["sample"]) != {"inclusion", "exclusion"}:
        raise EmpiricalProtocolError("sample must contain inclusion and exclusion")
    _strings(payload["sample"]["inclusion"], "sample.inclusion")
    _strings(payload["sample"]["exclusion"], "sample.exclusion", nonempty=False)
    if not isinstance(payload["variables"], dict) or set(payload["variables"]) != {"outcome", "treatment", "covariates"}:
        raise EmpiricalProtocolError("variables must contain outcome, treatment, and covariates")
    _strings(payload["variables"]["outcome"], "variables.outcome")
    _strings(payload["variables"]["treatment"], "variables.treatment")
    _strings(payload["variables"]["covariates"], "variables.covariates", nonempty=False)
    for key in ("assumptions", "diagnostics", "robustness_plan", "data_refs"):
        _strings(payload[key], key)
    for ref in payload["data_refs"]:
        _safe_ref(ref, "data_refs")
    _backend(payload["backend"])
    if not isinstance(payload["extensions"], dict):
        raise EmpiricalProtocolError("extensions must be an object")
    return json.loads(json.dumps(payload))


def _check_records(value: Any, label: str, allowed: set[str]) -> None:
    if not isinstance(value, list) or not value:
        raise EmpiricalProtocolError(f"{label} must be non-empty")
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"name", "status", "detail"}:
            raise EmpiricalProtocolError(f"{label}[{index}] fields are invalid")
        if not isinstance(item["name"], str) or not item["name"] or item["status"] not in allowed:
            raise EmpiricalProtocolError(f"{label}[{index}] is invalid")
        if not isinstance(item["detail"], str):
            raise EmpiricalProtocolError(f"{label}[{index}].detail must be a string")


def validate_result(payload: Any) -> dict[str, Any]:
    required = {
        "schema_version", "study_id", "spec_ref", "status", "estimate", "diagnostics", "robustness",
        "conclusion", "negative_result", "evidence_pack_ref", "commands", "artifact_refs", "extensions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise EmpiricalProtocolError("empirical result fields are invalid")
    if payload["schema_version"] != RESULT_SCHEMA:
        raise EmpiricalProtocolError("empirical result schema is unsupported")
    if not isinstance(payload["study_id"], str) or not ID_RE.fullmatch(payload["study_id"]):
        raise EmpiricalProtocolError("study_id is invalid")
    _safe_ref(payload["spec_ref"], "spec_ref")
    if payload["status"] not in RESULT_STATUSES:
        raise EmpiricalProtocolError("result status is invalid")
    if not isinstance(payload["estimate"], dict) or set(payload["estimate"]) != {"value", "uncertainty", "unit"}:
        raise EmpiricalProtocolError("estimate fields are invalid")
    if not isinstance(payload["estimate"]["value"], (int, float)) or isinstance(payload["estimate"]["value"], bool):
        raise EmpiricalProtocolError("estimate.value must be numeric")
    if not all(isinstance(payload["estimate"][key], str) and payload["estimate"][key] for key in ("uncertainty", "unit")):
        raise EmpiricalProtocolError("estimate uncertainty and unit are required")
    _check_records(payload["diagnostics"], "diagnostics", CHECK_STATUSES)
    _check_records(payload["robustness"], "robustness", ROBUSTNESS_STATUSES)
    if not isinstance(payload["conclusion"], str) or not payload["conclusion"].strip():
        raise EmpiricalProtocolError("conclusion must be non-empty")
    lower = payload["conclusion"].casefold()
    if "significant" in lower and any(marker in lower for marker in ("therefore", "proves", "is true")):
        raise EmpiricalProtocolError("statistical significance cannot be the research conclusion")
    if not isinstance(payload["negative_result"], bool):
        raise EmpiricalProtocolError("negative_result must be boolean")
    _safe_ref(payload["evidence_pack_ref"], "evidence_pack_ref")
    _strings(payload["commands"], "commands")
    _strings(payload["artifact_refs"], "artifact_refs")
    for ref in payload["artifact_refs"]:
        _safe_ref(ref, "artifact_refs")
    if not isinstance(payload["extensions"], dict):
        raise EmpiricalProtocolError("extensions must be an object")
    return json.loads(json.dumps(payload))


def doctor(core_root: str | None) -> tuple[dict[str, Any], int]:
    raw = core_root or os.environ.get("DS_LITE_CORE_ROOT", "").strip()
    result = {"schema_version": "ds-lite.pack-doctor.v1", "pack": "deepscientist-lite-empirical", "required": CORE, "status": "blocked"}
    if not raw:
        result["reason"] = "core-root-not-provided"
        return result, 2
    try:
        manifest = json.loads((Path(raw).expanduser().resolve() / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        result["reason"] = "core-manifest-unavailable"
        return result, 2
    observed = {"plugin": manifest.get("name"), "version": manifest.get("version")}
    result["observed"] = observed
    if observed != CORE:
        result["reason"] = "incompatible-core"
        return result, 2
    result.update({"status": "passed", "reason": "compatible-core-observed"})
    return result, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate DS Lite empirical protocols.")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--core-root")
    for command in ("validate-spec", "validate-result"):
        child = sub.add_parser(command)
        child.add_argument("--path", required=True)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        result, code = doctor(args.core_root)
        print(json.dumps(result, ensure_ascii=False))
        return code
    try:
        raw = json.loads(Path(args.path).read_text(encoding="utf-8"))
        validated = validate_spec(raw) if args.command == "validate-spec" else validate_result(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, EmpiricalProtocolError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "passed", "schema_version": validated["schema_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
