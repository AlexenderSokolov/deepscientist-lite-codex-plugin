"""Run a fresh, fake-only acceptance of the bounded Loop supervisor."""
from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.deepscientist_lite_import_shim import ds_lite_loop


SCHEMA = "ds-lite.offline-loop-acceptance.v1"


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def run(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError("offline Loop output already exists; refusing overwrite")
    output.mkdir(parents=True)
    workspace = output / "workspace"
    evidence = workspace / "evidence"
    plans = workspace / "plans"
    approvals = workspace / "approvals"
    evidence.mkdir(parents=True)
    plans.mkdir()
    approvals.mkdir()
    _write(evidence / "a.txt", "offline evidence a\n")
    _write(evidence / "b.txt", "offline evidence b\n")
    _write(plans / "work.md", "bounded fake Loop plan\n")
    _write(plans / "prompt.md", "perform one bounded offline action\n")
    _write(approvals / "user.md", "explicit offline test approval\n")
    _write(workspace / "goals.json", json.dumps([
        {"id": "goal-a", "evidence_refs": ["evidence/a.txt"]},
        {"id": "goal-b", "evidence_refs": ["evidence/b.txt"]},
    ]))
    _write(output / "fake-sequence.json", json.dumps([
        {"status": "partial", "failure_layer": "none", "session_id": "fake-session"},
        {"status": "completed", "failure_layer": "none", "session_id": "fake-session",
         "completion": True, "completed_goal_ids": ["goal-a", "goal-b"]},
    ]))
    contract_path = output / "fake-contract.json"
    ds_lite_loop.prepare(Namespace(
        loop_id="offline-loop-20260723", goals_file=str(workspace / "goals.json"),
        working_plan_ref="plans/work.md", prompt_ref="plans/prompt.md",
        allowed_path=["evidence"], adapter="fake", max_rounds=3, max_seconds=60,
        authorization="required", authority="none", approval_ref="", sandbox="read-only",
        output=str(contract_path),
    ))
    summary = ds_lite_loop.run_loop(Namespace(
        contract=str(contract_path), root=str(workspace), output_dir=str(workspace / "fake-run"),
        fake_sequence=str(output / "fake-sequence.json"), codex_bin=None,
        autoresearch_bin=None, execute=False,
    ))
    verification = ds_lite_loop.verify(Namespace(
        contract=str(contract_path), summary=str(workspace / "fake-run" / "summary.json"),
    ))
    if summary.get("status") != "completed" or verification.get("status") != "passed":
        raise RuntimeError("fake bounded Loop acceptance did not complete")

    external_contract = output / "external-contract.json"
    ds_lite_loop.prepare(Namespace(
        loop_id="offline-external-20260723", goals_file=str(workspace / "goals.json"),
        working_plan_ref="plans/work.md", prompt_ref="plans/prompt.md",
        allowed_path=["evidence"], adapter="codex-autoresearch", max_rounds=3, max_seconds=60,
        authorization="approved", authority="user", approval_ref="approvals/user.md",
        sandbox="read-only", output=str(external_contract),
    ))
    external_error = ""
    try:
        ds_lite_loop.run_loop(Namespace(
            contract=str(external_contract), root=str(workspace),
            output_dir=str(workspace / "external-run"), fake_sequence=None, codex_bin=None,
            autoresearch_bin=str(output / "missing-autoresearch"), execute=True,
        ))
    except ds_lite_loop.LoopError as exc:
        external_error = str(exc)
    if "external-policy-unverified" not in external_error:
        raise RuntimeError("external adapter was not rejected by policy")
    report = {
        "schema_version": SCHEMA,
        "status": "passed",
        "offline_loop_status": "passed",
        "fake_round_count": summary["round_count"],
        "fake_verification_status": verification["status"],
        "external_adapter_status": "blocked-not-verified",
        "external_process_spawn_observed": False,
        "external_failure_class": "external-policy-unverified",
        "real_provider_verified": False,
        "real_gates_unlocked": False,
        "raw_output_persisted": False,
        "unverified": [
            "real Codex continuation",
            "real Hook host",
            "real child-agent dispatch",
            "matched effect",
            "formal cache",
            "fresh Desktop",
            "release gate",
        ],
        "next_action": "inspect trusted-hook-05 protocol failure before requesting a new real identity",
    }
    _write(output / "offline-loop-acceptance.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fake-only bounded Loop acceptance.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run(args.output)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "offline-loop", "message": str(exc)}))
        return 1
    print(json.dumps({"status": report["status"], "offline_loop_status": report["offline_loop_status"],
                      "external_adapter_status": report["external_adapter_status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
