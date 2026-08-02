#!/usr/bin/env python3
"""Run deterministic offline acceptance without contacting a real provider."""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import hashlib
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    import pilot_runtime
    import lab_runner
    import pilot_score
except ModuleNotFoundError:  # Package import from repository tests and tools.
    from teaching import lab_runner, pilot_runtime, pilot_score


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts"
if str(PLUGIN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS))

# The frozen monolith and split Core intentionally expose the same script
# module names. Import the legacy modules under a protected dependency window
# so full unittest discovery cannot substitute whichever Hook loaded first.
_legacy_names = ("ds_lite_hook", "ds_lite_iteration", "ds_lite_protocol", "ds_lite_state", "ds_lite_evidence")
_legacy_saved = {name: sys.modules.pop(name) for name in _legacy_names if name in sys.modules}
try:
    ds_lite_hook = importlib.import_module("ds_lite_hook")
    ds_lite_iteration = importlib.import_module("ds_lite_iteration")
    ds_lite_protocol = importlib.import_module("ds_lite_protocol")
finally:
    for _name, _module in _legacy_saved.items():
        sys.modules[_name] = _module


SCHEMA_VERSION = "ds-lite.offline-protocol-acceptance.v1"
SCENARIOS = (
    "success",
    "auth-failure",
    "rate-limit",
    "network-failure",
    "malformed-response",
    "child-early-exit",
    "ambiguous-transport",
)


class OfflineAcceptanceError(RuntimeError):
    pass


def protocol_status(*checks: bool) -> str:
    return "passed" if checks and all(checks) else "blocked"


class _Provider(ThreadingHTTPServer):
    request_counts: dict[str, int]
    response_facts: dict[str, dict[str, Any]]


class _ProviderHandler(BaseHTTPRequestHandler):
    server: _Provider

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        scenario = self.path.strip("/")
        self.server.request_counts[scenario] = self.server.request_counts.get(scenario, 0) + 1
        if scenario == "network-failure":
            self.server.response_facts[scenario] = {
                "http_status": 0,
                "error_object_state": "not-observed",
                "response_shape": "disconnect-before-header",
                "request_id_sha256": "not-observed",
            }
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if scenario == "auth-failure":
            self.server.response_facts[scenario] = {
                "http_status": 401,
                "error_object_state": "observed",
                "error_type": "authentication_error",
                "error_code": "invalid_api_key",
                "response_shape": "json-error",
            }
            self._json_response(401, {"error": {"type": "authentication_error", "code": "invalid_api_key", "message": "FAKE-RESPONSE-SECRET"}})
            return
        if scenario == "rate-limit":
            self.server.response_facts[scenario] = {
                "http_status": 429,
                "error_object_state": "observed",
                "error_type": "rate_limit_exceeded",
                "error_code": "rate_limit_exceeded",
                "response_shape": "json-error",
            }
            self._json_response(429, {"error": {"type": "rate_limit_exceeded", "code": "rate_limit_exceeded", "message": "FAKE-RESPONSE-SECRET"}})
            return
        if scenario == "malformed-response":
            self.server.response_facts[scenario] = {
                "http_status": 200,
                "error_object_state": "not-observed",
                "response_shape": "malformed-json",
            }
            self._response(200, b"{")
            return
        self.server.response_facts[scenario] = {
            "http_status": 200,
            "error_object_state": "not-observed",
            "response_shape": "json-success",
        }
        self._json_response(200, {"status": "ok"})

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        self._response(status, json.dumps(payload).encode("utf-8"))

    def _response(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        request_id = f"fake-request-{self.path.strip('/')}"
        self.send_header("x-request-id", request_id)
        facts = self.server.response_facts.get(self.path.strip("/"), {})
        facts["request_id_sha256"] = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _hook_acceptance(output: Path) -> dict[str, Any]:
    workspace = output / "protocol-workspaces" / "hook"
    state_script = PLUGIN_SCRIPTS / "ds_lite_state.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(state_script),
            "init",
            "--root",
            str(workspace),
            "--title",
            "Offline hook acceptance",
            "--question",
            "Can the fake host exercise the hook protocol without host claims?",
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise OfflineAcceptanceError("failed to initialize the offline Hook workspace")

    secret = "FAKE-HOOK-SECRET"
    context = ds_lite_hook.handle_event(
        "user-prompt-submit", {"cwd": str(workspace), "prompt": f"continue password={secret}"}
    )
    blocked = ds_lite_hook.handle_event(
        "pre-tool-use",
        {
            "cwd": str(workspace),
            "tool_name": "Edit",
            "tool_input": {"file_path": str(workspace / "research" / "state" / "graph.json"), "new_string": secret},
        },
    )
    allowed = ds_lite_hook.handle_event(
        "pre-tool-use",
        {"cwd": str(workspace), "tool_name": "shell_command", "tool_input": {"command": "Get-Content research/state/graph.json"}},
    )
    graph = json.loads((workspace / "research" / "state" / "graph.json").read_text(encoding="utf-8"))
    ds_lite_iteration.initialize_iteration(
        workspace,
        iteration_id="offline-hook-running",
        selected_skill="ds-lite-iterate",
        action={
            "kind": "status-check",
            "summary": "Exercise the fake-host Stop boundary.",
            "prediction": "A running iteration blocks Stop once.",
            "falsification_condition": "Stop is allowed before finalization.",
            "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
            "stop_condition": "Stop after the fake-host check.",
            "extensions": {},
        },
        input_refs=["PROJECT.md", "research/work-unit.json"],
        expected_revision=graph["revision"],
    )
    first_stop = ds_lite_hook.handle_event("stop", {"cwd": str(workspace)})
    guarded_stop = ds_lite_hook.handle_event("stop", {"cwd": str(workspace), "stop_hook_active": True})
    rendered = json.dumps(context, ensure_ascii=False)
    redacted_context = secret not in rendered and str(workspace) not in rendered
    dangerous_write_blocked = blocked.get("decision") == "block"
    read_only_allowed = allowed.get("decision") == "allow"
    stop_reentry_guarded = first_stop.get("decision") == "block" and guarded_stop.get("decision") == "allow"
    return {
        "status": protocol_status(redacted_context, dangerous_write_blocked, read_only_allowed, stop_reentry_guarded),
        "claim": "fake-host-tested",
        "host_loading": "real-host-not-verified",
        "redacted_context": redacted_context,
        "dangerous_write_blocked": dangerous_write_blocked,
        "read_only_allowed": read_only_allowed,
        "stop_reentry_guarded": stop_reentry_guarded,
    }


def _delegation_payload() -> dict[str, Any]:
    def task(task_id: str, path: str) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "objective": f"Inspect {task_id}.",
            "input_refs": ["PROJECT.md"],
            "allowed_paths": [path],
            "expected_output_refs": [path],
            "validation_commands": ["python tools/validation/validate_repo.py"],
            "resource_limits": [{"dimension": "walltime", "unit": "minute", "value": 5}],
            "stop_conditions": ["Stop after one bounded fake result."],
            "status": "authorized",
            "result_ref": "",
            "extensions": {},
        }

    return {
        "schema_version": "ds-lite.delegation.v1",
        "delegation_id": "offline-delegation",
        "parent_work_unit_id": "offline-work-unit",
        "strategy": "parallel",
        "status": "authorized",
        "approval": {"status": "approved", "authority": "user", "approval_ref": "research/artifacts/offline-approval.md", "extensions": {}},
        "integration_owner": "parent-worker",
        "max_children": 2,
        "nested_delegation": False,
        "tasks": [
            task("worker-a", "research/artifacts/worker-a-result.md"),
            task("worker-b", "research/artifacts/worker-b-result.md"),
        ],
        "created_at": "2026-07-20T00:00:00Z",
        "updated_at": "2026-07-20T00:00:00Z",
        "extensions": {"execution_kind": "offline-fake-results"},
    }


def _delegation_acceptance(output: Path) -> dict[str, Any]:
    payload = _delegation_payload()
    planned = copy.deepcopy(payload)
    planned["status"] = "planned"
    planned["approval"] = {"status": "required", "authority": "none", "approval_ref": "", "extensions": {}}
    plan_only_stopped = ds_lite_protocol.validate_delegation(planned)["status"] == "planned"

    overlapping = copy.deepcopy(payload)
    overlapping["tasks"][1]["allowed_paths"] = [overlapping["tasks"][0]["allowed_paths"][0]]
    try:
        ds_lite_protocol.validate_delegation(overlapping)
        overlap_rejected = False
    except ds_lite_protocol.ProtocolError:
        overlap_rejected = True

    workspace = output / "protocol-workspaces" / "delegation"
    for task in payload["tasks"]:
        task["status"] = "completed"
        task["result_ref"] = task["expected_output_refs"][0]
        result_path = workspace.joinpath(*task["result_ref"].split("/"))
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(f"# {task['task_id']} offline result\n", encoding="utf-8")
    payload["status"] = "completed"
    validated = ds_lite_protocol.validate_delegation(payload)
    parent_integration_verified = (
        validated["integration_owner"] == "parent-worker"
        and all(workspace.joinpath(*task["result_ref"].split("/")).is_file() for task in validated["tasks"])
    )
    return {
        "status": protocol_status(plan_only_stopped, overlap_rejected, parent_integration_verified),
        "claim": "protocol-tested",
        "host_dispatch": "host-dispatch-not-verified",
        "plan_only_stopped": plan_only_stopped,
        "overlap_rejected": overlap_rejected,
        "parent_integration_verified": parent_integration_verified,
        "real_child_agents_started": False,
    }


def _matched_acceptance(output: Path) -> dict[str, Any]:
    workspace = output / "protocol-workspaces" / "matched"
    lab_runner.MatchedPilotBuilder(workspace).build()
    manifest = json.loads((workspace / "pilot-manifest.json").read_text(encoding="utf-8"))
    equal_digests = all(
        len({row["input_digest"] for row in manifest["runs"] if row["case"] == case}) == 1
        for case in manifest["cases"]
    )
    failed = {"call_id": "offline-failed", "status": "failed", "stop_reason": "process-failed", "round": 1, "usage": {"total_tokens": 0}}
    freeze = pilot_runtime.resume_decision([failed])
    score = pilot_score.score_arm(
        "engineering-continuity",
        "plain",
        workspace / "arms" / "engineering-continuity" / "plain",
        [failed],
        baseline_inventory={},
    )
    all_runs_pending = all(row["status"] == "pending" for row in manifest["runs"])
    failed_execution_frozen = freeze["action"] == "stop"
    score_incomplete = score["status"] == "incomplete"
    return {
        "status": protocol_status(equal_digests, all_runs_pending, failed_execution_frozen, score_incomplete),
        "claim": "prepared-and-freeze-tested",
        "effect": "effect-not-measured",
        "run_count": len(manifest["runs"]),
        "all_runs_pending": all_runs_pending,
        "equal_input_digests": equal_digests,
        "failed_execution_frozen": failed_execution_frozen,
        "score_status": score["status"],
        "real_model_calls_started": False,
    }


def _execution(scenario: str) -> dict[str, Any]:
    return {
        "schema_version": "ds-lite.matched-pilot-execution.v1",
        "execution_id": f"execution:offline-{scenario}",
        "pilot_id": "offline-transport-acceptance",
        "call_id": f"offline-{scenario}",
        "case": "engineering-continuity",
        "arm": "plain",
        "round": 1,
        "status": "pending",
        # Keep the fake transport envelope aligned with the active Core pilot identity.
        "source": {"git_commit": "0" * 40, "tree_digest": "0" * 64, "plugin_version": "0.0.0-offline", "skill_count": pilot_runtime.EXPECTED_SKILL_COUNT, "extensions": {}},
        "cli": {"name": "codex", "version": pilot_runtime.CODEX_VERSION, "model": pilot_runtime.MODEL, "reasoning_effort": pilot_runtime.REASONING_EFFORT, "extensions": {"runtime": "fake-codex"}},
        "input": {"workspace_surface": "windows", "workspace_ref": ".", "prompt_ref": "offline/prompt", "input_digest": "1" * 64, "extensions": {}},
        "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "extensions": {}},
        "elapsed_seconds": 0,
        "exit_code": None,
        "session_id": "",
        "final_message": "",
        "wsl": {"status": "not-required", "distribution": "", "proof_ref": "", "extensions": {}},
        "stop_reason": "not-started",
        "result_refs": [f"results/{scenario}.json"],
        "started_at": "",
        "completed_at": "",
        "extensions": {"claim_scope": "fake-provider-and-fake-codex-only"},
    }


def run_offline_acceptance(output_root: Path | str) -> dict[str, Any]:
    output = Path(output_root)
    if output.exists():
        raise OfflineAcceptanceError(f"output already exists: {output}")
    output.mkdir(parents=True)
    (output / "workspace").mkdir()
    (output / "home").mkdir()

    server = _Provider(("127.0.0.1", 0), _ProviderHandler)
    server.request_counts = {}
    server.response_facts = {}
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    rows: list[dict[str, Any]] = []
    try:
        provider_url = f"http://127.0.0.1:{server.server_address[1]}"
        fake_codex = Path(__file__).with_name("fake_transport_codex.py")
        for scenario in SCENARIOS:
            receipt_ref = f"results/{scenario}.json"
            record_path = output.joinpath(*receipt_ref.split("/"))
            result = pilot_runtime.run_codex_call(
                codex_bin=fake_codex,
                cwd=output / "workspace",
                codex_home=output / "home",
                prompt="run one offline fake transport scenario",
                record_path=record_path,
                execution=_execution(scenario),
                timeout_seconds=5,
                extra_env={
                    "DS_LITE_FAKE_PROVIDER_URL": provider_url,
                    "DS_LITE_FAKE_SCENARIO": scenario,
                    # The fake provider is loopback-only. Do not let a host
                    # proxy (or Windows semicolon-separated NO_PROXY) alter
                    # deterministic transport classifications.
                    "NO_PROXY": "*",
                    "no_proxy": "*",
                },
                progress_context={"receipt_ref": receipt_ref},
            )
            saved = record_path.read_text(encoding="utf-8")
            diagnostic = result["extensions"]["process_diagnostic"]
            count = server.request_counts.get(scenario, 0)
            rows.append(
                {
                    "scenario": scenario,
                    "status": result["status"],
                    "failure_class": diagnostic["failure_class"],
                    "fake_codex_launch_count": 1,
                    "provider_request_count": count,
                    "provider_response_facts": server.response_facts.get(scenario, {}),
                    "response_event_shape": (
                        ["thread.started"]
                        if scenario == "child-early-exit"
                        else ["thread.started", "item.completed", "turn.completed"]
                        if scenario == "success"
                        else ["thread.started"]
                    ),
                    "automatic_retry_observed": count > 1,
                    "raw_stderr_persisted": "FAKE-STDERR-SECRET" in saved,
                    "receipt_ref": receipt_ref,
                }
            )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    protocols = {
        "hook": _hook_acceptance(output),
        "delegation": _delegation_acceptance(output),
        "matched_comparison": _matched_acceptance(output),
    }
    expected_classes = {
        "success": "none",
        "auth-failure": "auth",
        "rate-limit": "rate-limit",
        "network-failure": "network",
        "malformed-response": "protocol",
        "child-early-exit": "child-process",
        "ambiguous-transport": "ambiguous",
    }
    transport_passed = all(
        row["failure_class"] == expected_classes[row["scenario"]]
        and row["fake_codex_launch_count"] == 1
        and row["provider_request_count"] == (0 if row["scenario"] == "child-early-exit" else 1)
        and not row["automatic_retry_observed"]
        and not row["raw_stderr_persisted"]
        for row in rows
    )
    protocol_passed = all(item["status"] == "passed" for item in protocols.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "claim_scope": "fake-provider-and-fake-codex-only",
        "overall_status": "passed" if transport_passed and protocol_passed else "blocked",
        # Formal release aggregation consumes a uniform top-level status;
        # retain overall_status for v1 readers and expose the same value here.
        "status": "passed" if transport_passed and protocol_passed else "blocked",
        "real_provider_verified": False,
        "real_codex_wire_compatibility_verified": False,
        "real_gates_unlocked": False,
        "transport": {"status": "passed" if transport_passed else "blocked", "scenarios": rows},
        "protocols": protocols,
        "next_gate": "request a separately authorized fresh real pilot only after all offline gates pass",
    }
    (output / "offline-acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fake-only DeepScientist Lite offline acceptance.")
    parser.add_argument("--output", type=Path, required=True, help="Fresh output directory; existing paths are refused.")
    args = parser.parse_args()
    try:
        report = run_offline_acceptance(args.output)
    except (OfflineAcceptanceError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
