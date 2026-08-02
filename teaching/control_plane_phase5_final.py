#!/usr/bin/env python3
"""Deterministic, write-once Phase 5 final acceptance assembler."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.candidate import (  # noqa: E402
    aggregate_candidate_bound_gates,
    bind_release_candidate,
    build_candidate_manifest,
    build_repository_candidate_manifest,
    write_candidate_manifest,
)


PHASE5_INPUT_SCHEMAS = {
    "runtime-windows": "ds-lite.runtime-compatibility.v1",
    "runtime-linux": "ds-lite.runtime-compatibility.v1",
    "resource-windows": "ds-lite.phase5-resource.v1",
    "resource-linux": "ds-lite.phase5-resource.v1",
    "stable-hook": "ds-lite.trusted-hook-acceptance.v1",
    "stable-v2-action": "ds-lite.phase5-real-codex-action-v2.v1",
    "dbos-upgrade": "ds-lite.phase5-dbos-upgrade.v1",
    "supervisor-windows": "ds-lite.phase5-user-supervisor.v1",
    "supervisor-wsl": "ds-lite.phase5-user-supervisor.v1",
    "real-host-chaos": "ds-lite.phase5-real-host-chaos.v1",
    "network-matrix": "ds-lite.phase5-network-disconnect.v1",
    "synthetic-provider": "ds-lite.phase5-synthetic-provider.v1",
    "fresh-desktop": "ds-lite.fresh-desktop-acceptance.v1",
    "openscience": "ds-lite.openscience-acceptance.v1",
    "matched-effect": "ds-lite.matched-effect-acceptance.v1",
    "backup-restore": "ds-lite.phase4-backup-recovery.v1",
}
REVALIDATION_REQUIRED_INPUTS = set(PHASE5_INPUT_SCHEMAS)
CANDIDATE_EVIDENCE_SCHEMA = "ds-lite.phase5-candidate-evidence.v1"
DECISION_INPUT_SCHEMAS = {
    "legacy-complete": {"ds-lite.formal-release-gate.v2"},
    "control-aggregate": {
        "ds-lite.candidate-bound-aggregate.v1", "ds-lite.release-decision.v1",
    },
    "regressions": {"ds-lite.phase5-regressions.v1"},
    "publication-actions": {"ds-lite.phase5-publication-actions.v1"},
    "phase4-real-gate": {"ds-lite.phase5-candidate-bound-gate.v1"},
    "phase5-real-host-gate": {"ds-lite.phase5-candidate-bound-gate.v1"},
}
PLATFORMS = {
    "runtime-windows": "windows-x86_64",
    "runtime-linux": "linux-x86_64",
    "resource-windows": "windows-x86_64",
    "resource-linux": "linux-x86_64",
}
FORBIDDEN_EVIDENCE_KEYS = {
    "api_key", "credential", "credentials", "hidden_reasoning", "model_text",
    "password", "prompt", "raw_model_text", "raw_prompt", "raw_response",
    "secret", "access_token", "auth_token",
}
BLOCKER_KEYS = (
    "missing_gates", "nonpassing_gates", "duplicate_gates",
    "candidate_mismatch_gates", "invalid_schema_gates",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: Any) -> str:
    content = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not a readable JSON artifact") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    _reject_sensitive(value, label)
    return value


def _reject_sensitive(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_EVIDENCE_KEYS:
                raise ValueError(f"{label} contains a forbidden evidence key")
            _reject_sensitive(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive(nested, label)


def _named_inputs(
    values: Iterable[tuple[str, Path]], required: Iterable[str],
) -> dict[str, Path]:
    required_names = list(required)
    observed: dict[str, Path] = {}
    duplicates: list[str] = []
    unsupported: list[str] = []
    for name, path in values:
        if name not in required_names:
            unsupported.append(name)
        elif name in observed:
            duplicates.append(name)
        else:
            observed[name] = Path(path).resolve()
    if unsupported:
        raise ValueError("unsupported named input: " + ",".join(sorted(set(unsupported))))
    if duplicates:
        raise ValueError("duplicate named input: " + ",".join(sorted(set(duplicates))))
    missing = [name for name in required_names if name not in observed]
    if missing:
        raise ValueError("missing named input: " + ",".join(missing))
    return observed


def _artifact_record(name: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "file": path.name,
        "schema_version": payload["schema_version"],
        "sha256": _sha256(path),
    }


def _validate_checks(payload: dict[str, Any], label: str) -> None:
    checks = payload.get("checks")
    if checks is None:
        return
    if (
        not isinstance(checks, dict) or not checks
        or not all(isinstance(value, bool) and value for value in checks.values())
    ):
        raise ValueError(f"{label} has nonpassing deterministic checks")


def _validate_candidate(payload: dict[str, Any], digest: str, label: str) -> None:
    if payload.get("candidate_digest") != digest:
        raise ValueError(f"{label} candidate digest mismatch")


def build_candidate(
    repository: Path, windows_package: Path, linux_package: Path, output: Path,
) -> dict[str, Any]:
    source = build_repository_candidate_manifest(repository)
    package_paths = {
        "linux-x86_64": Path(linux_package).resolve(),
        "windows-x86_64": Path(windows_package).resolve(),
    }
    packages: dict[str, dict[str, Any]] = {}
    records: dict[str, dict[str, Any]] = {}
    for platform_name, path in package_paths.items():
        payload = _read_object(path, f"{platform_name} package manifest")
        if payload.get("schema_version") != "ds-lite.candidate-manifest.v1":
            raise ValueError(f"{platform_name} package manifest schema mismatch")
        if not _valid_digest(payload.get("candidate_digest")):
            raise ValueError(f"{platform_name} package digest is invalid")
        packages[platform_name] = payload
        records[platform_name] = {
            "file": path.name,
            "manifest_sha256": _sha256(path),
            "candidate_digest": payload["candidate_digest"],
        }
    binding = bind_release_candidate(source, packages)
    receipt = {
        "schema_version": "ds-lite.phase5-release-candidate.v1",
        "source_manifest": source,
        "package_manifests": records,
        "source_digest": binding["source_digest"],
        "candidate_digest": binding["candidate_digest"],
    }
    receipt["receipt_digest"] = _canonical_digest(receipt)
    _write_once(output, receipt)
    return receipt


def build_package_manifest(package_root: Path, output: Path) -> dict[str, Any]:
    root = Path(package_root).resolve()
    if not root.is_dir():
        raise ValueError("package root must be a directory")
    manifest = build_candidate_manifest(root)
    write_candidate_manifest(output, manifest)
    return manifest


def _candidate_evidence_payload(
    input_name: str, candidate_digest: str, path: Path, payload: dict[str, Any],
) -> dict[str, Any]:
    expected_schema = PHASE5_INPUT_SCHEMAS[input_name]
    checks = payload.get("checks")
    deterministic_checks = (
        checks is None or (
            isinstance(checks, dict) and bool(checks)
            and all(isinstance(value, bool) and value for value in checks.values())
        )
    )
    expected_platform = PLATFORMS.get(input_name)
    compatibility_checks = {
        "deterministic_checks_passed": deterministic_checks,
        "original_schema_match": payload.get("schema_version") == expected_schema,
        "original_status_passed": payload.get("status") == "passed",
        "platform_match": expected_platform is None or payload.get("platform") == expected_platform,
        "release_boundary_preserved": payload.get("release_allowed") in (None, False),
    }
    current_revalidated = payload.get("candidate_digest") == candidate_digest
    requires_revalidation = input_name in REVALIDATION_REQUIRED_INPUTS
    compatible = all(compatibility_checks.values())
    passed = compatible and (current_revalidated or not requires_revalidation)
    wrapper = {
        "schema_version": CANDIDATE_EVIDENCE_SCHEMA,
        "input_name": input_name,
        "status": "passed" if passed else "blocked",
        "candidate_digest": candidate_digest,
        "original_receipt": {
            "file": path.name,
            "schema_version": payload.get("schema_version"),
            "sha256": _sha256(path),
        },
        "evidence_class": (
            "current-candidate-real-host" if current_revalidated
            else "historical-compatibility-only"
        ),
        "compatibility_checks": compatibility_checks,
        "current_candidate_revalidated": current_revalidated,
        "requires_current_candidate_revalidation": requires_revalidation,
        "release_allowed": False,
    }
    wrapper["verification_digest"] = _canonical_digest(wrapper)
    return wrapper


def build_candidate_evidence(
    input_name: str, candidate_digest: str, original_receipt: Path, output: Path,
) -> dict[str, Any]:
    """Verify an immutable receipt without claiming that compatibility is a rerun."""
    if input_name not in PHASE5_INPUT_SCHEMAS:
        raise ValueError("unsupported Phase5 evidence input")
    if not _valid_digest(candidate_digest):
        raise ValueError("candidate digest must be a SHA-256 value")
    path = Path(original_receipt).resolve()
    destination = Path(output).resolve()
    if path.parent != destination.parent:
        raise ValueError("candidate wrapper and original receipt must share a directory")
    payload = _read_object(path, input_name)
    wrapper = _candidate_evidence_payload(input_name, candidate_digest, path, payload)
    _write_once(output, wrapper)
    return wrapper


def _validate_candidate_evidence(
    name: str, path: Path, payload: dict[str, Any], candidate_digest: str,
) -> None:
    if payload.get("schema_version") != CANDIDATE_EVIDENCE_SCHEMA:
        raise ValueError(f"{name} must be a candidate evidence wrapper")
    if payload.get("input_name") != name:
        raise ValueError(f"{name} candidate evidence identity mismatch")
    if payload.get("candidate_digest") != candidate_digest:
        raise ValueError(f"{name} candidate digest mismatch")
    original = payload.get("original_receipt")
    if (
        not isinstance(original, dict)
        or original.get("schema_version") != PHASE5_INPUT_SCHEMAS[name]
        or not _valid_digest(original.get("sha256"))
        or not isinstance(original.get("file"), str)
        or not original["file"]
    ):
        raise ValueError(f"{name} original receipt identity is invalid")
    original_name = str(original["file"])
    if Path(original_name).name != original_name:
        raise ValueError(f"{name} original receipt identity is invalid")
    original_path = path.parent / original_name
    original_payload = _read_object(original_path, f"{name} original receipt")
    if _sha256(original_path) != original.get("sha256"):
        raise ValueError(f"{name} original receipt hash mismatch")
    expected_wrapper = _candidate_evidence_payload(
        name, candidate_digest, original_path, original_payload,
    )
    if payload != expected_wrapper:
        raise ValueError(f"{name} candidate wrapper integrity mismatch")
    checks = payload.get("compatibility_checks")
    if (
        not isinstance(checks, dict) or not checks
        or not all(isinstance(value, bool) and value for value in checks.values())
    ):
        raise ValueError(f"{name} compatibility checks did not pass")
    revalidated = payload.get("current_candidate_revalidated") is True
    requires_revalidation = name in REVALIDATION_REQUIRED_INPUTS
    if payload.get("requires_current_candidate_revalidation") is not requires_revalidation:
        raise ValueError(f"{name} revalidation policy mismatch")
    expected_class = (
        "current-candidate-real-host" if revalidated else "historical-compatibility-only"
    )
    if payload.get("evidence_class") != expected_class:
        raise ValueError(f"{name} evidence class mismatch")
    if requires_revalidation and not revalidated:
        raise ValueError(f"{name} was not revalidated on the current candidate")
    if payload.get("status") != "passed":
        raise ValueError(f"{name} status is not passed")
    if payload.get("release_allowed") is not False:
        raise ValueError(f"{name} wrapper cannot claim release_allowed")


def build_gate(
    gate_id: str, candidate_digest: str, inputs: Iterable[tuple[str, Path]],
    output: Path, *, phase4_decision_sha256: str | None = None,
) -> dict[str, Any]:
    if not _valid_digest(candidate_digest):
        raise ValueError("candidate digest must be a SHA-256 value")
    if gate_id == "phase4-real-gate":
        named = _named_inputs(inputs, ("phase4-decision",))
        if not _valid_digest(phase4_decision_sha256):
            raise ValueError("authoritative Phase4 decision hash is required")
        path = named["phase4-decision"]
        payload = _read_object(path, "phase4-decision")
        if _sha256(path) != phase4_decision_sha256:
            raise ValueError("authoritative Phase4 decision hash mismatch")
        if (
            payload.get("schema_version") != "ds-lite.phase4-decision.v1"
            or payload.get("phase4_decision") != "go"
            or payload.get("release_allowed") is not False
        ):
            raise ValueError("authoritative Phase4 decision did not pass")
        _validate_checks(payload, "phase4-decision")
        artifacts = [_artifact_record("phase4-decision", path, payload)]
        evidence_class = "historical-authoritative-prerequisite"
    elif gate_id == "phase5-real-host":
        named = _named_inputs(inputs, PHASE5_INPUT_SCHEMAS)
        artifacts = []
        for name, schema in PHASE5_INPUT_SCHEMAS.items():
            path = named[name]
            payload = _read_object(path, name)
            _validate_candidate_evidence(name, path, payload, candidate_digest)
            artifacts.append(_artifact_record(name, path, payload))
        evidence_class = "current-candidate-acceptance-aggregate"
    else:
        raise ValueError("unsupported gate id")
    receipt = {
        "schema_version": "ds-lite.phase5-candidate-bound-gate.v1",
        "gate_id": gate_id,
        "status": "passed",
        "candidate_digest": candidate_digest,
        "evidence_class": evidence_class,
        "artifacts": artifacts,
    }
    receipt["input_digest"] = _canonical_digest(artifacts)
    _write_once(output, receipt)
    return receipt


def build_control_aggregate(
    candidate_digest: str, inputs: Iterable[tuple[str, Path]], output: Path,
) -> dict[str, Any]:
    if not _valid_digest(candidate_digest):
        raise ValueError("candidate digest must be a SHA-256 value")
    required = ("phase4-real-gate", "phase5-real-host")
    named = _named_inputs(inputs, required)
    receipts: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    expected_classes = {
        "phase4-real-gate": "historical-authoritative-prerequisite",
        "phase5-real-host": "current-candidate-acceptance-aggregate",
    }
    for name in required:
        path = named[name]
        payload = _read_object(path, name)
        if (
            payload.get("schema_version") != "ds-lite.phase5-candidate-bound-gate.v1"
            or payload.get("gate_id") != name
            or payload.get("status") != "passed"
            or payload.get("candidate_digest") != candidate_digest
            or payload.get("evidence_class") != expected_classes[name]
        ):
            raise ValueError(f"{name} is not an accepted candidate-bound gate")
        receipts.append(payload)
        artifacts.append(_artifact_record(name, path, payload))
    aggregate = aggregate_candidate_bound_gates(candidate_digest, required, receipts)
    aggregate["gate_artifacts"] = artifacts
    aggregate["unresolved_integrity_incidents"] = 0
    aggregate["input_digest"] = _canonical_digest(artifacts)
    _write_once(output, aggregate)
    return aggregate


def build_decision(
    candidate_digest: str, inputs: Iterable[tuple[str, Path]], output: Path,
) -> dict[str, Any]:
    if not _valid_digest(candidate_digest):
        raise ValueError("candidate digest must be a SHA-256 value")
    named = _named_inputs(inputs, DECISION_INPUT_SCHEMAS)
    artifacts: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    for name, schemas in DECISION_INPUT_SCHEMAS.items():
        path = named[name]
        payload = _read_object(path, name)
        if payload.get("schema_version") not in schemas:
            raise ValueError(f"{name} schema mismatch")
        _validate_candidate(payload, candidate_digest, name)
        payloads[name] = payload
        artifacts.append(_artifact_record(name, path, payload))
    for name in ("legacy-complete", "control-aggregate"):
        payload = payloads[name]
        if payload.get("release_allowed") is not True or payload.get("status") not in {
            "passed", "allowed",
        }:
            raise ValueError(f"{name} is not release allowed")
        if any(payload.get(key, []) not in ([], None) for key in BLOCKER_KEYS):
            raise ValueError(f"{name} contains a release blocker")
        if payload.get("unresolved_integrity_incidents", 0) != 0:
            raise ValueError(f"{name} contains a release blocker")
    regressions = payloads["regressions"]
    if regressions.get("status") != "passed" or regressions.get("release_allowed") not in (None, False):
        raise ValueError("required regressions did not pass")
    _validate_checks(regressions, "regressions")
    phase5_gate = payloads["phase5-real-host-gate"]
    if (
        phase5_gate.get("gate_id") != "phase5-real-host"
        or phase5_gate.get("status") != "passed"
        or phase5_gate.get("evidence_class") != "current-candidate-acceptance-aggregate"
    ):
        raise ValueError("phase5 real-host gate did not pass on the current candidate")
    phase4_gate = payloads["phase4-real-gate"]
    if (
        phase4_gate.get("gate_id") != "phase4-real-gate"
        or phase4_gate.get("status") != "passed"
        or phase4_gate.get("evidence_class") != "historical-authoritative-prerequisite"
    ):
        raise ValueError("phase4 authoritative gate did not pass")
    expected_gate_artifacts = [
        _artifact_record("phase4-real-gate", named["phase4-real-gate"], phase4_gate),
        _artifact_record("phase5-real-host", named["phase5-real-host-gate"], phase5_gate),
    ]
    if payloads["control-aggregate"].get("gate_artifacts") != expected_gate_artifacts:
        raise ValueError("control aggregate does not bind the exact gate receipts")
    publication = payloads["publication-actions"]
    actions = publication.get("actions")
    expected_actions = {"publish", "push", "submit", "upload"}
    if (
        publication.get("status") != "passed"
        or publication.get("release_allowed") not in (None, False)
        or not isinstance(actions, dict) or set(actions) != expected_actions
        or any(value is not False for value in actions.values())
    ):
        raise ValueError("publication actions must remain false")
    decision = {
        "schema_version": "ds-lite.phase5-decision.v1",
        "phase5_decision": "go",
        "status": "allowed",
        "release_allowed": True,
        "candidate_digest": candidate_digest,
        "publication_actions": dict(sorted(actions.items())),
        "artifacts": artifacts,
        "missing_inputs": [],
        "nonpassing_inputs": [],
        "candidate_mismatch_inputs": [],
        "duplicate_inputs": [],
    }
    decision["input_digest"] = _canonical_digest(artifacts)
    _write_once(output, decision)
    return decision


def _parse_inputs(values: list[str]) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for value in values:
        if "=" not in value:
            raise ValueError("inputs must use NAME=PATH")
        name, raw_path = value.split("=", 1)
        if not name or not raw_path:
            raise ValueError("inputs must use NAME=PATH")
        result.append((name, Path(raw_path)))
    return result


def _candidate_digest(path: Path) -> str:
    payload = _read_object(path.resolve(), "release candidate")
    if payload.get("schema_version") != "ds-lite.phase5-release-candidate.v1":
        raise ValueError("release candidate schema mismatch")
    receipt_digest = payload.get("receipt_digest")
    digest_payload = dict(payload)
    digest_payload.pop("receipt_digest", None)
    if not _valid_digest(receipt_digest) or receipt_digest != _canonical_digest(digest_payload):
        raise ValueError("release candidate receipt digest mismatch")
    digest = payload.get("candidate_digest")
    if not _valid_digest(digest):
        raise ValueError("release candidate digest is invalid")
    return str(digest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    package = sub.add_parser("package-manifest")
    package.add_argument("--package-root", required=True, type=Path)
    package.add_argument("--output", required=True, type=Path)
    candidate = sub.add_parser("candidate")
    candidate.add_argument("--repository", required=True, type=Path)
    candidate.add_argument("--windows-package", required=True, type=Path)
    candidate.add_argument("--linux-package", required=True, type=Path)
    candidate.add_argument("--output", required=True, type=Path)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("--input-name", required=True, choices=tuple(PHASE5_INPUT_SCHEMAS))
    evidence.add_argument("--candidate", required=True, type=Path)
    evidence.add_argument("--original-receipt", required=True, type=Path)
    evidence.add_argument("--output", required=True, type=Path)
    gate = sub.add_parser("gate")
    gate.add_argument("--gate-id", required=True, choices=("phase4-real-gate", "phase5-real-host"))
    gate.add_argument("--candidate", required=True, type=Path)
    gate.add_argument("--input", action="append", default=[])
    gate.add_argument("--phase4-decision-sha256")
    gate.add_argument("--output", required=True, type=Path)
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--candidate", required=True, type=Path)
    aggregate.add_argument("--input", action="append", default=[])
    aggregate.add_argument("--output", required=True, type=Path)
    decision = sub.add_parser("decision")
    decision.add_argument("--candidate", required=True, type=Path)
    decision.add_argument("--input", action="append", default=[])
    decision.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "package-manifest":
            result = build_package_manifest(args.package_root, args.output)
        elif args.command == "candidate":
            result = build_candidate(
                args.repository, args.windows_package, args.linux_package, args.output,
            )
        elif args.command == "evidence":
            result = build_candidate_evidence(
                args.input_name, _candidate_digest(args.candidate),
                args.original_receipt, args.output,
            )
        elif args.command == "gate":
            result = build_gate(
                args.gate_id, _candidate_digest(args.candidate), _parse_inputs(args.input),
                args.output, phase4_decision_sha256=args.phase4_decision_sha256,
            )
        elif args.command == "aggregate":
            result = build_control_aggregate(
                _candidate_digest(args.candidate), _parse_inputs(args.input), args.output,
            )
        else:
            result = build_decision(
                _candidate_digest(args.candidate), _parse_inputs(args.input), args.output,
            )
    except FileExistsError:
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    except (OSError, UnicodeError):
        print(json.dumps({"status": "blocked", "reason": "artifact-io-error"}))
        return 2
    except ValueError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps({
        "status": result["status"] if "status" in result else "created",
        "candidate_digest": result["candidate_digest"],
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
