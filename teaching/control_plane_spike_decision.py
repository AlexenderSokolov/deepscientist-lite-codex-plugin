"""Aggregate write-once Phase 0.5 evidence into a fail-closed decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"receipt-not-object:{path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observed_methods(receipt: dict, names: tuple[str, ...]) -> bool:
    methods = receipt.get("methods")
    return isinstance(methods, dict) and all(methods.get(name) == "observed" for name in names)


def build(*, repo_root: Path, evidence_root: Path, paths: dict[str, Path]) -> dict:
    receipts = {name: _load(path) for name, path in paths.items()}
    canonical = receipts["canonical"]
    hook = receipts["hook"]
    dbos = receipts["dbos"]
    fault = receipts["fault"]
    resource = receipts["resource"]
    phase_tests = receipts["phase_tests"]
    core = receipts["core"]
    required_lifecycle = (
        "thread/start", "turn/start", "thread/list", "thread/read", "thread/archive",
        "thread/unarchive", "thread/resume", "thread/final-archive",
    )
    cases = fault.get("cases") if isinstance(fault.get("cases"), dict) else {}
    gate_checks = {
        "canonical_thread": (
            canonical.get("status") == "passed"
            and canonical.get("evidence_class") == "real-app-server"
            and _observed_methods(canonical, required_lifecycle)
            and canonical.get("controller_turn_start_count") == 1
            and canonical.get("used_last") is False
            and canonical.get("implicit_thread_start_after_resume_failure") is False
        ),
        "hook_in_turn_repair": (
            hook.get("status") == "passed"
            and hook.get("evidence_class") == "real-host"
            and hook.get("observation", {}).get("controller_turn_start_count") == 1
            and hook.get("observation", {}).get("exact_hook_turn_identity") is True
            and hook.get("verifier", {}).get("deterministic_verifier") is True
            and hook.get("verifier", {}).get("release_allowed") is False
        ),
        "dbos_sqlite_recovery": (
            dbos.get("status") == "passed"
            and dbos.get("evidence_class") == "real-dbos-sqlite"
            and dbos.get("dbos_version") == "2.29.0"
            and dbos.get("same_action_workflow_identity") is True
            and dbos.get("workflow_row_count") == 1
            and dbos.get("old_fence_mutation_rejected") is True
            and dbos.get("new_fence_mutation_persisted") is True
        ),
        "fault_harness": (
            fault.get("status") == "passed"
            and fault.get("evidence_class") == "fake-host"
            and fault.get("seed") == 20260731
            and fault.get("trials") == 100
            and set(cases) == {f"K{number}" for number in range(1, 7)}
            and all(case.get("passed") == 100 and case.get("failed") == 0 for case in cases.values())
        ),
        "windows_resource": resource.get("status") == "observed" and resource.get("platform") == "win32",
        "phase_tests": phase_tests.get("status") == "passed",
        "core_package": core.get("status") == "passed" and core.get("scope") == "core",
    }
    success_evidence = []
    for name, path in paths.items():
        success_evidence.append({
            "kind": name,
            "path": path.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": _sha256(path),
        })
    selected = {path.resolve() for path in paths.values()}
    failure_evidence = []
    for path in sorted(evidence_root.glob("*.json")):
        if path.resolve() in selected or path.name.startswith("spike-decision-"):
            continue
        try:
            receipt = _load(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            continue
        if receipt.get("status") in {"blocked", "failed", "timeout"} or "incident" in receipt.get("schema_version", ""):
            failure_evidence.append({
                "path": path.resolve().relative_to(repo_root.resolve()).as_posix(),
                "sha256": _sha256(path),
                "status": receipt.get("status", "integrity-incident"),
                "failure_layer": receipt.get("failure_layer", receipt.get("incident", "recorded")),
            })
    decision = "go" if all(gate_checks.values()) else "no-go"
    hook_script = repo_root / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook.py"
    hooks_manifest = repo_root / "plugins" / "deepscientist-lite-core" / "hooks" / "hooks.json"
    return {
        "schema_version": "ds-lite.control-plane-spike-decision.v2",
        "spike_decision": decision,
        "phase1_goal_allowed": decision == "go",
        "release_allowed": False,
        "scope": "Phase 0 and Phase 0.5 only",
        "versions": {
            "codex_cli": canonical.get("cli_version", hook.get("cli_version", "0.128.0")),
            "python": dbos.get("python_version"),
            "dbos": dbos.get("dbos_version"),
        },
        "digests": {
            "schema_sha256": canonical.get("schema_sha256"),
            "hooks_manifest_sha256": _sha256(hooks_manifest),
            "hook_script_sha256": _sha256(hook_script),
        },
        "gate_checks": gate_checks,
        "identities": {
            "canonical_thread_sha256": canonical.get("thread_id_sha256"),
            "canonical_turn_sha256": canonical.get("turn_id_sha256"),
            "hook_thread_sha256": hook.get("thread_id_sha256"),
            "hook_turn_sha256": hook.get("turn_id_sha256"),
            "dbos_action_sha256": dbos.get("action_id_sha256"),
            "dbos_workflow_sha256": dbos.get("workflow_id_sha256"),
        },
        "fault_matrix": {"seed": fault.get("seed"), "trials_per_cut": fault.get("trials"), "evidence_class": "fake-host"},
        "resource": resource,
        "other_platform": {
            "platform": "wsl-ds-lite-ubuntu-24.04",
            "python_version": "3.12.3",
            "status": "not-observed",
            "reason": "dbos-and-pip-not-available; no installation performed",
            "release_prerequisite": True,
        },
        "success_evidence": success_evidence,
        "failure_evidence": failure_evidence,
        "integrity": {
            "write_once": True,
            "raw_host_responses_persisted": False,
            "excluded_receipts": [
                "research/.validation-tmp/control-plane-evidence-20260731/dbos-sqlite-recovery-02.json"
            ],
            "excluded_reason": "known false-success verifier; superseded by recovery-03 and recovery-05",
        },
        "residual_risks": [
            "plugin_hooks is enabled only for the isolated 0.128.0 acceptance process and is disabled by default",
            "Hook acceptance used protocol-specific developer instructions; autonomous repair quality is not claimed",
            "non-Windows resource measurements remain a release prerequisite",
            "go permits a separate Phase 1 goal only; it is not a release decision",
        ],
        "decision_reason": (
            "all preregistered Phase 0.5 gates have evidence"
            if decision == "go" else "one or more preregistered Phase 0.5 gates lack evidence"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    for name in ("canonical", "hook", "dbos", "fault", "resource", "phase-tests", "core"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("refusing to overwrite spike decision")
    paths = {
        "canonical": args.canonical,
        "hook": args.hook,
        "dbos": args.dbos,
        "fault": args.fault,
        "resource": args.resource,
        "phase_tests": args.phase_tests,
        "core": args.core,
    }
    receipt = build(repo_root=args.repo_root, evidence_root=args.evidence_root, paths=paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"spike_decision": receipt["spike_decision"], "release_allowed": False}))
    return 0 if receipt["spike_decision"] == "go" else 2


if __name__ == "__main__":
    raise SystemExit(main())
