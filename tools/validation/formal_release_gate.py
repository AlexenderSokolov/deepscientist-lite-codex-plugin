#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def _active_complete_profile() -> str:
    try:
        package_set = json.loads((REPO_ROOT / "release" / "package-set.json").read_text(encoding="utf-8"))
        version = package_set["release_version"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("active release package set is unavailable") from exc
    if not isinstance(version, str) or not version:
        raise RuntimeError("active release package set has no release version")
    return f"ds-lite-{version}-complete"


REQUIRED_GATES_V1 = (
    "source",
    "offline",
    "cli",
    "hook",
    "delegation",
    "matched_effect",
    "formal_cache",
    "fresh_desktop",
    "docs",
)
REQUIRED_GATES_V2 = REQUIRED_GATES_V1 + ("provider", "openscience")
LEGACY_COMPLETE_PROFILE = "ds-lite-0.8.1-complete"
COMPLETE_PROFILE = _active_complete_profile()
ACCEPTED_COMPLETE_PROFILES = {COMPLETE_PROFILE, LEGACY_COMPLETE_PROFILE}
SCHEMA_V1 = "ds-lite.formal-release-gate.v1"
SCHEMA_V2 = "ds-lite.formal-release-gate.v2"
SCHEMA_V3 = "ds-lite.formal-release-gate.v3"
COMPLETE_RELEASE_GATES_V2 = REQUIRED_GATES_V2 + (
    "hook_in_turn_repair",
    "session_control",
    "web",
    "wsl",
)

# The complete profile is a release boundary, not a generic JSON status
# collector. Keep the older profiles compatible, but reject adjacent receipts
# that happen to say "passed" without proving the requested execution surface.
COMPLETE_GATE_SCHEMAS = {
    "source": "ds-lite.upstream-audit.v1",
    "offline": "ds-lite.offline-protocol-acceptance.v1",
    "cli": "ds-lite.cli-acceptance.v1",
    "hook": "ds-lite.trusted-hook-acceptance.v1",
    "delegation": "ds-lite.real-delegation-acceptance.v1",
    "matched_effect": "ds-lite.matched-effect-acceptance.v1",
    "formal_cache": "ds-lite.formal-cache-acceptance.v1",
    "fresh_desktop": "ds-lite.fresh-desktop-acceptance.v1",
    "docs": "ds-lite.docs-acceptance.v1",
    "provider": "ds-lite.academic-provider-acceptance.v1",
    "openscience": "ds-lite.openscience-acceptance.v1",
    "hook_in_turn_repair": "ds-lite.hook-in-turn-repair.v1",
    "session_control": "ds-lite.app-server-conversation-control.v1",
    "web": "ds-lite.web-benchmark-acceptance.v1",
    "wsl": "ds-lite.wsl-tmux-acceptance.v1",
}


def complete_gate_evidence_is_verifiable(gate: str, payload: dict[str, Any]) -> bool:
    """Reject assertions that lack the deterministic evidence required by a gate."""
    if gate != "hook_in_turn_repair":
        return True
    return (
        payload.get("deterministic_verifier") is True
        and payload.get("release_evidence") is True
        and isinstance(payload.get("verified_turn_id"), str)
        and bool(payload["verified_turn_id"].strip())
    )


def required_gates(schema_version: str, profile: str) -> tuple[str, ...]:
    if schema_version.endswith("v1"):
        if profile != "default":
            raise ValueError("complete profile requires formal-release-gate.v2")
        return REQUIRED_GATES_V1
    if profile == "default":
        return REQUIRED_GATES_V2
    if profile in ACCEPTED_COMPLETE_PROFILES:
        return COMPLETE_RELEASE_GATES_V2
    raise ValueError(f"unsupported release profile: {profile}")


def load_gate(value: str, required_gates: tuple[str, ...]) -> tuple[str, Path, dict[str, Any]]:
    if "=" not in value:
        raise ValueError("evidence must use GATE=PATH")
    gate, raw_path = value.split("=", 1)
    if gate not in required_gates:
        raise ValueError(f"unsupported gate: {gate}")
    path = Path(raw_path).expanduser().resolve()
    # Receipts may come from PowerShell or legacy tooling that emits a UTF-8
    # BOM. Accept it at the ingestion boundary without changing the canonical
    # no-BOM receipt written by this validator.
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{gate} evidence must contain a JSON object")
    return gate, path, payload


def evaluate(
    values: list[str], schema_version: str, profile: str = "default", *,
    candidate_digest: str | None = None,
) -> tuple[dict[str, Any], int]:
    formal_schema_version = schema_version
    if candidate_digest is not None:
        if profile not in ACCEPTED_COMPLETE_PROFILES:
            raise ValueError("candidate digest binding requires the complete profile")
        if len(candidate_digest) != 64 or any(
            character not in "0123456789abcdef" for character in candidate_digest.lower()
        ):
            raise ValueError("candidate digest must be a SHA-256 value")
    required = required_gates(schema_version, profile)
    observed: dict[str, dict[str, Any]] = {}
    duplicate_gates: list[str] = []
    invalid_schema_gates: list[str] = []
    for value in values:
        gate, path, payload = load_gate(value, required)
        if gate in observed:
            duplicate_gates.append(gate)
            continue
        receipt_schema_version = payload.get("schema_version", "not-observed")
        status = payload.get("status", "not-verified")
        if profile in ACCEPTED_COMPLETE_PROFILES and receipt_schema_version != COMPLETE_GATE_SCHEMAS[gate]:
            invalid_schema_gates.append(gate)
            status = "not-verified"
        if profile in ACCEPTED_COMPLETE_PROFILES and not complete_gate_evidence_is_verifiable(gate, payload):
            status = "not-verified"
        observed[gate] = {
            "status": status,
            "schema_version": receipt_schema_version,
            "candidate_digest": payload.get("candidate_digest"),
            "evidence_file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    missing = [gate for gate in required if gate not in observed]
    nonpassing = [gate for gate, item in observed.items() if item["status"] != "passed"]
    candidate_mismatches = [
        gate for gate, item in observed.items()
        if candidate_digest is not None and item.get("candidate_digest") != candidate_digest
    ]
    passed = (
        not missing and not nonpassing and not duplicate_gates
        and not invalid_schema_gates and not candidate_mismatches
    )
    result = {
        "schema_version": formal_schema_version,
        "profile": profile,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "passed" if passed else "blocked",
        "required_gates": list(required),
        "gates": {gate: observed.get(gate, {"status": "not-verified"}) for gate in required},
        "missing_gates": missing,
        "nonpassing_gates": nonpassing,
        "duplicate_gates": sorted(set(duplicate_gates)),
        "invalid_schema_gates": sorted(set(invalid_schema_gates)),
        "candidate_digest": candidate_digest,
        "candidate_mismatch_gates": sorted(set(candidate_mismatches)),
        "adjacent_evidence_inference": False,
        "release_allowed": passed,
    }
    return result, 0 if passed else 2


def evaluate_control_plane(
    control_db: Path,
    job_id: str,
    release_profile: Path,
    receipt_root: Path,
) -> tuple[dict[str, Any], int]:
    """Run the v3 compatibility entry through the Phase 4 aggregate kernel."""
    if not control_db.is_file():
        raise ValueError("v3 control database does not exist")
    if not release_profile.is_file():
        raise ValueError("v3 release profile does not exist")

    repo_root = Path(__file__).resolve().parents[2]
    controller_root = repo_root / "plugins" / "deepscientist-lite-control-plane" / "controller"
    if str(controller_root) not in sys.path:
        sys.path.insert(0, str(controller_root))

    # Keep the optional dependency lazy: ordinary v1/v2 release aggregation
    # remains usable without importing the control-plane extension.
    from ds_lite_control.release import StrictReleaseAggregate
    from ds_lite_control.store import ControlStore

    profile = json.loads(release_profile.read_text(encoding="utf-8-sig"))
    if not isinstance(profile, dict):
        raise ValueError("v3 release profile must contain a JSON object")
    store = ControlStore(control_db)
    try:
        result = StrictReleaseAggregate(store, receipt_root).decide(job_id, profile)
    finally:
        store.close()
    return result, 0 if result["release_allowed"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate independent DS Lite release evidence without inference.")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--schema-version", choices=(SCHEMA_V1, SCHEMA_V2, SCHEMA_V3), default=SCHEMA_V1)
    parser.add_argument("--profile", choices=("default", *sorted(ACCEPTED_COMPLETE_PROFILES)), default="default")
    parser.add_argument("--candidate-digest")
    parser.add_argument("--control-db", type=Path)
    parser.add_argument("--job-id")
    parser.add_argument("--release-profile", type=Path)
    parser.add_argument("--receipt-root", type=Path)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        print(json.dumps({"status": "blocked", "reason": "output-exists"}))
        return 2
    try:
        if args.schema_version == SCHEMA_V3:
            if args.evidence:
                raise ValueError("v3 does not accept legacy --evidence receipts")
            if args.profile != "default":
                raise ValueError("v3 requires --release-profile instead of legacy --profile")
            required = {
                "--control-db": args.control_db,
                "--job-id": args.job_id,
                "--release-profile": args.release_profile,
                "--receipt-root": args.receipt_root,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError("v3 requires " + ", ".join(missing))
            result, returncode = evaluate_control_plane(
                args.control_db.resolve(), args.job_id,
                args.release_profile.resolve(), args.receipt_root.resolve(),
            )
        else:
            if any((args.control_db, args.job_id, args.release_profile, args.receipt_root)):
                raise ValueError("control-plane arguments require formal-release-gate.v3")
            result, returncode = evaluate(
                args.evidence, args.schema_version, args.profile,
                candidate_digest=args.candidate_digest,
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result["status"], "release_allowed": result["release_allowed"]}))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
