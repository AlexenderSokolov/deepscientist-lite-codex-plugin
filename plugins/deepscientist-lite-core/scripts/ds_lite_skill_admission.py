#!/usr/bin/env python3
"""Skill Admission Registry and Gate for DS Lite v6.

Manages candidate Skill准入: any candidate must pass the admission gate
before entering the official package. The gate checks source/license,
trigger/anti-trigger, input/output/evidence contract, external effects,
permissions, install mode, tests, and reviewed_at.

Schema: ds-lite.skill-admission.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

ADMISSION_SCHEMA = "ds-lite.skill-admission.v1"
CANDIDATE_SCHEMA = "ds-lite.skill-candidate.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

DECISIONS = frozenset({
    "core-method", "adapter", "on-demand", "reference-only", "rejected",
})

INSTALL_MODES = frozenset({
    "bundled", "explicit", "external",
})

# Admission gate requirements
GATE_REQUIREMENTS = [
    ("source_license_clear", "Source and license must be clear"),
    ("trigger_anti_trigger_clear", "Trigger and anti-trigger must be clear"),
    ("input_output_evidence_contract", "Input/output/evidence contract must be clear"),
    ("external_effects_documented", "External effects must be documented"),
    ("permissions_documented", "Permissions must be documented"),
    ("install_mode_safe", "Install mode must be safe"),
    ("tests_exist", "Tests must exist"),
    ("reviewed_at_set", "Review timestamp must be set"),
]


class SkillAdmissionError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_skill_candidate(candidate: Any) -> dict[str, Any]:
    """Validate a skill candidate against ds-lite.skill-candidate.v1."""
    if not isinstance(candidate, dict):
        raise SkillAdmissionError("candidate must be an object")

    if candidate.get("schema_version") != CANDIDATE_SCHEMA:
        raise SkillAdmissionError(f"schema_version must be {CANDIDATE_SCHEMA}")

    required = {
        "schema_version", "skill_id", "name", "source", "commit_or_version",
        "license", "decision", "capabilities", "triggers", "anti_triggers",
        "dependencies", "external_effects", "permissions", "install_mode",
        "tests", "reviewed_at", "extensions",
    }
    missing = required - set(candidate.keys())
    if missing:
        raise SkillAdmissionError(f"missing required fields: {sorted(missing)}")

    if not ID_RE.fullmatch(candidate["skill_id"]):
        raise SkillAdmissionError("skill_id must match identifier pattern")

    if not isinstance(candidate["name"], str) or not candidate["name"].strip():
        raise SkillAdmissionError("name must be a non-empty string")

    if not isinstance(candidate["source"], str) or not candidate["source"].strip():
        raise SkillAdmissionError("source must be a non-empty string")

    if not isinstance(candidate["commit_or_version"], str) or not candidate["commit_or_version"].strip():
        raise SkillAdmissionError("commit_or_version must be a non-empty string")

    if not isinstance(candidate["license"], str) or not candidate["license"].strip():
        raise SkillAdmissionError("license must be a non-empty string")

    if candidate["decision"] not in DECISIONS:
        raise SkillAdmissionError(f"decision must be one of {sorted(DECISIONS)}")

    if not isinstance(candidate["capabilities"], list) or len(candidate["capabilities"]) == 0:
        raise SkillAdmissionError("capabilities must be a non-empty list")

    if not isinstance(candidate["triggers"], list) or len(candidate["triggers"]) == 0:
        raise SkillAdmissionError("triggers must be a non-empty list")

    if not isinstance(candidate["anti_triggers"], list) or len(candidate["anti_triggers"]) == 0:
        raise SkillAdmissionError("anti_triggers must be a non-empty list")

    if not isinstance(candidate["dependencies"], list):
        raise SkillAdmissionError("dependencies must be a list")

    if not isinstance(candidate["external_effects"], list):
        raise SkillAdmissionError("external_effects must be a list")

    if not isinstance(candidate["permissions"], list):
        raise SkillAdmissionError("permissions must be a list")

    if candidate["install_mode"] not in INSTALL_MODES:
        raise SkillAdmissionError(f"install_mode must be one of {sorted(INSTALL_MODES)}")

    if not isinstance(candidate["tests"], list):
        raise SkillAdmissionError("tests must be a list")

    if not isinstance(candidate["reviewed_at"], str) or not candidate["reviewed_at"].strip():
        raise SkillAdmissionError("reviewed_at must be a non-empty ISO-8601 string")

    return json.loads(json.dumps(candidate))


def check_admission_gate(candidate: Any) -> dict[str, Any]:
    """Check if a skill candidate passes the admission gate.

    Returns a result dict with:
    - verdict: "pass" | "blocked"
    - rule_ids: list of triggered rule IDs
    - gate_results: dict mapping requirement to bool
    - admission_digest: str
    """
    if not isinstance(candidate, dict):
        raise SkillAdmissionError("candidate must be an object")

    rule_ids: list[str] = []
    gate_results: dict[str, bool] = {}
    verdict = "pass"

    # Check 1: Source and license must be clear
    has_source = bool(candidate.get("source", "").strip())
    has_license = bool(candidate.get("license", "").strip())
    source_license_ok = has_source and has_license
    gate_results["source_license_clear"] = source_license_ok
    if not source_license_ok:
        rule_ids.append("source_or_license_unclear")
        verdict = "blocked"

    # Check 2: Trigger and anti-trigger must be clear
    has_triggers = isinstance(candidate.get("triggers"), list) and len(candidate["triggers"]) > 0
    has_anti_triggers = isinstance(candidate.get("anti_triggers"), list) and len(candidate["anti_triggers"]) > 0
    trigger_ok = has_triggers and has_anti_triggers
    gate_results["trigger_anti_trigger_clear"] = trigger_ok
    if not trigger_ok:
        rule_ids.append("trigger_or_anti_trigger_missing")
        verdict = "blocked"

    # Check 3: Input/output/evidence contract must be clear
    has_capabilities = isinstance(candidate.get("capabilities"), list) and len(candidate["capabilities"]) > 0
    has_tests = isinstance(candidate.get("tests"), list) and len(candidate["tests"]) > 0
    contract_ok = has_capabilities and has_tests
    gate_results["input_output_evidence_contract"] = contract_ok
    if not contract_ok:
        rule_ids.append("input_output_or_evidence_contract_unclear")
        verdict = "blocked"

    # Check 4: External effects must be documented
    has_external_effects = isinstance(candidate.get("external_effects"), list)
    gate_results["external_effects_documented"] = has_external_effects
    if not has_external_effects:
        rule_ids.append("external_effects_not_documented")
        verdict = "blocked"

    # Check 5: Permissions must be documented
    has_permissions = isinstance(candidate.get("permissions"), list)
    gate_results["permissions_documented"] = has_permissions
    if not has_permissions:
        rule_ids.append("permissions_not_documented")
        verdict = "blocked"

    # Check 6: Install mode must be safe
    install_mode = candidate.get("install_mode", "")
    install_ok = install_mode in INSTALL_MODES
    gate_results["install_mode_safe"] = install_ok
    if not install_ok:
        rule_ids.append("install_mode_invalid")
        verdict = "blocked"

    # Check 7: Tests must exist
    gate_results["tests_exist"] = has_tests
    if not has_tests:
        rule_ids.append("tests_missing")
        verdict = "blocked"

    # Check 8: Review timestamp must be set
    has_reviewed_at = bool(candidate.get("reviewed_at", "").strip())
    gate_results["reviewed_at_set"] = has_reviewed_at
    if not has_reviewed_at:
        rule_ids.append("reviewed_at_not_set")
        verdict = "blocked"

    # Compute admission digest
    admission_digest = _digest({
        "skill_id": candidate.get("skill_id", "unknown"),
        "source": candidate.get("source", ""),
        "commit_or_version": candidate.get("commit_or_version", ""),
        "license": candidate.get("license", ""),
        "decision": candidate.get("decision", ""),
    })

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "gate_results": gate_results,
        "admission_digest": admission_digest,
    }
    return result


def register_skill(candidate: dict[str, Any]) -> dict[str, Any]:
    """Register a skill candidate.

    The candidate must pass the admission gate before being registered.
    If validation fails, we still run the admission gate to get a full
    diagnostic, then return a failure result.
    """
    try:
        validated = validate_skill_candidate(candidate)
    except SkillAdmissionError:
        gate_result = check_admission_gate(candidate)
        return {
            "registered": False,
            "reason": "admission_gate_failed",
            "gate_result": gate_result,
        }

    gate_result = check_admission_gate(validated)

    if gate_result["verdict"] != "pass":
        return {
            "registered": False,
            "reason": "admission_gate_failed",
            "gate_result": gate_result,
        }

    return {
        "registered": True,
        "skill_id": validated["skill_id"],
        "admission_digest": gate_result["admission_digest"],
        "gate_result": gate_result,
    }


def create_skill_candidate(
    skill_id: str,
    name: str,
    source: str,
    commit_or_version: str,
    license: str,
    decision: str,
    capabilities: list[str],
    triggers: list[str],
    anti_triggers: list[str],
    dependencies: list[str] | None = None,
    external_effects: list[str] | None = None,
    permissions: list[str] | None = None,
    install_mode: str = "explicit",
    tests: list[str] | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    """Create a skill candidate document."""
    if not ID_RE.fullmatch(skill_id):
        raise SkillAdmissionError("skill_id must match identifier pattern")
    if decision not in DECISIONS:
        raise SkillAdmissionError(f"decision must be one of {sorted(DECISIONS)}")
    if install_mode not in INSTALL_MODES:
        raise SkillAdmissionError(f"install_mode must be one of {sorted(INSTALL_MODES)}")

    candidate = {
        "schema_version": CANDIDATE_SCHEMA,
        "skill_id": skill_id,
        "name": name,
        "source": source,
        "commit_or_version": commit_or_version,
        "license": license,
        "decision": decision,
        "capabilities": capabilities,
        "triggers": triggers,
        "anti_triggers": anti_triggers,
        "dependencies": dependencies or [],
        "external_effects": external_effects or [],
        "permissions": permissions or [],
        "install_mode": install_mode,
        "tests": tests or [],
        "reviewed_at": reviewed_at or _now_iso(),
        "extensions": {},
    }
    return candidate


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Skill Admission Registry and Gate for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    check_parser = sub.add_parser("check")
    check_parser.add_argument("--candidate", required=True, help="Path to candidate JSON")

    register_parser = sub.add_parser("register")
    register_parser.add_argument("--candidate", required=True, help="Path to candidate JSON")

    args = parser.parse_args()
    try:
        candidate = json.loads(open(args.candidate, encoding="utf-8").read())
        if args.command == "check":
            result = check_admission_gate(candidate)
        elif args.command == "register":
            result = register_skill(candidate)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (SkillAdmissionError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())