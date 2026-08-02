from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT / "plugins" / "deepscientist-lite-core"
HOOK_SCRIPT = CORE_ROOT / "scripts" / "ds_lite_hook.py"
AUDIT_SCRIPT = CORE_ROOT / "scripts" / "ds_lite_communication_audit.py"
TEST_TEMP_ROOT = Path(os.environ.get("DS_LITE_TEST_ROOT", tempfile.gettempdir()))
sys.path.insert(0, str(CORE_ROOT / "scripts"))
import ds_lite_hook  # noqa: E402


class StopAutonomyExecutionTests(unittest.TestCase):
    def test_pending_autoresearch_job_starts_persistent_watch_with_frozen_prompt(self) -> None:
        root = TEST_TEMP_ROOT / f"hook-controller-pending-{uuid.uuid4().hex[:12]}"
        job = {
            "schema_version": "ds-lite.autoresearch-job.v1",
            "job_id": "pending-job",
            "initial_prompt": "run the approved task",
            "frozen_goals": ["source", "summary"],
            "state_dir": "research/autoresearch/run",
        }
        with (
            mock.patch.object(ds_lite_hook, "_autoresearch_job", return_value=(job, root / "job.json")),
            mock.patch.object(ds_lite_hook, "_autoresearch_state", return_value=({"status": "pending"}, root / "run")),
            mock.patch.object(
                ds_lite_hook.subprocess,
                "run",
                return_value=mock.Mock(returncode=2),
            ) as run,
        ):
            ok, failure = ds_lite_hook._resume_autoresearch_controller(root)
        self.assertFalse(ok)
        self.assertEqual(failure, "autoresearch/controller-needs-resume")
        command = run.call_args.args[0]
        self.assertEqual(command[2], "watch")
        self.assertIn("run the approved task", command)
        self.assertIn("--goal", command)
        self.assertIn("summary", command)
        self.assertEqual(command[-2:], ["--poll-seconds", "0"])

    def test_bounded_autoresearch_mode_remains_available_for_supervised_calls(self) -> None:
        root = TEST_TEMP_ROOT / f"hook-controller-bounded-{uuid.uuid4().hex[:12]}"
        job = {
            "schema_version": "ds-lite.autoresearch-job.v1",
            "job_id": "bounded-job",
            "initial_prompt": "run one bounded call",
            "frozen_goals": ["source"],
            "runner_mode": "bounded",
            "state_dir": "research/autoresearch/run",
        }
        with (
            mock.patch.object(ds_lite_hook, "_autoresearch_job", return_value=(job, root / "job.json")),
            mock.patch.object(ds_lite_hook, "_autoresearch_state", return_value=({"status": "pending"}, root / "run")),
            mock.patch.object(ds_lite_hook.subprocess, "run", return_value=mock.Mock(returncode=2)) as run,
        ):
            ok, failure = ds_lite_hook._resume_autoresearch_controller(root)
        self.assertFalse(ok)
        self.assertEqual(failure, "autoresearch/controller-needs-resume")
        command = run.call_args.args[0]
        self.assertEqual(command[2], "run")
        self.assertIn("run one bounded call", command)

    def test_controller_children_use_project_volume_temp_root(self) -> None:
        root = Path("C:/ds-lite-test")
        with mock.patch.object(ds_lite_hook.Path, "mkdir"):
            env = ds_lite_hook._project_temp_env(root)
        expected = str((root / "research" / ".validation-tmp").resolve())
        self.assertEqual(env["TEMP"], expected)
        self.assertEqual(env["TMP"], expected)
        self.assertEqual(env["TEMP_ROOT"], expected)
        self.assertTrue(env["PYTHONPYCACHEPREFIX"].startswith(expected))

    def test_active_autoresearch_job_requests_external_resume_without_running_it(self) -> None:
        root = Path("C:/ds-lite-test")
        with (
            mock.patch.object(ds_lite_hook, "_workspace_root", return_value=root),
            mock.patch.object(ds_lite_hook, "_autonomy_is_active", return_value=False),
            mock.patch.object(ds_lite_hook, "_autoresearch_stop_gaps", side_effect=[
                ["autoresearch runner is not completed: needs_resume"],
                ["autoresearch runner is not completed: needs_resume"],
            ]),
            mock.patch.object(ds_lite_hook, "_resume_autoresearch_controller", return_value=(False, "autoresearch/controller-needs-resume")) as resume,
            mock.patch.object(ds_lite_hook, "_stop_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_stop_quality_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_user_action_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_audit_stop_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_autonomy_stop_gaps", return_value=[]),
        ):
            result = ds_lite_hook.handle_event("stop", {})
        resume.assert_not_called()
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["controller_action"], "external-controller-required")
        self.assertEqual(result["control_action"], "hook-in-turn-repair")
        self.assertEqual(result["next_automatic_action"], "resume-autoresearch-session")
        self.assertTrue(result["continue_once"])
        self.assertTrue(result["continue"])

    def test_failed_autoresearch_job_receives_only_same_turn_repair(self) -> None:
        root = Path("C:/ds-lite-test")
        with (
            mock.patch.object(ds_lite_hook, "_workspace_root", return_value=root),
            mock.patch.object(ds_lite_hook, "_autonomy_is_active", return_value=False),
            mock.patch.object(ds_lite_hook, "_autoresearch_stop_gaps", side_effect=[
                ["autoresearch runner is not completed: failed"],
                ["autoresearch runner is not completed: failed"],
            ]),
            mock.patch.object(ds_lite_hook, "_resume_autoresearch_controller", return_value=(False, "session-id-not-observed")),
            mock.patch.object(ds_lite_hook, "_stop_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_stop_quality_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_user_action_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_audit_stop_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_autonomy_stop_gaps", return_value=[]),
        ):
            result = ds_lite_hook.handle_event("stop", {})
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["control_action"], "hook-in-turn-repair")
        self.assertTrue(result["continue_once"])
        self.assertEqual(result["failure_layer"], "controller-incomplete")

    def test_user_prompt_only_projects_active_controller_state(self) -> None:
        root = Path("C:/ds-lite-test")
        with (
            mock.patch.object(ds_lite_hook, "_workspace_root", return_value=root),
            mock.patch.object(ds_lite_hook, "_autonomy_is_active", return_value=True),
            mock.patch.object(ds_lite_hook, "_resume_autonomy_controller", return_value=(False, "autonomy/controller-incomplete")) as resume,
            mock.patch.object(ds_lite_hook, "_mission_context", return_value="mission"),
            mock.patch.object(ds_lite_hook, "_autonomy_context", return_value="controller"),
            mock.patch.object(ds_lite_hook.ds_lite_user_action, "load_pending", return_value=None),
            mock.patch.object(ds_lite_hook, "_active_skill", return_value=""),
        ):
            result = ds_lite_hook.handle_event("user-prompt-submit", {})
        resume.assert_not_called()
        self.assertEqual(result["next_automatic_action"], "resume-autonomy-controller")
        self.assertIn("controller", result["additional_context"])

    def test_post_tool_only_projects_active_controller_state(self) -> None:
        root = Path("C:/ds-lite-test")
        with (
            mock.patch.object(ds_lite_hook, "_workspace_root", return_value=root),
            mock.patch.object(ds_lite_hook, "_autonomy_is_active", return_value=True),
            mock.patch.object(ds_lite_hook, "_resume_autonomy_controller", return_value=(False, "autonomy/controller-incomplete")) as resume,
            mock.patch.object(ds_lite_hook, "_audit_post_event"),
            mock.patch.object(ds_lite_hook, "_post_tool_context", return_value="post"),
            mock.patch.object(ds_lite_hook, "_autonomy_context", return_value=""),
            mock.patch.object(ds_lite_hook, "_autonomy_resume_context", return_value=""),
        ):
            result = ds_lite_hook.handle_event("post-tool-use", {})
        resume.assert_not_called()
        self.assertEqual(result["next_automatic_action"], "resume-autonomy-controller")
        self.assertIn("controller", result["additional_context"])

    def test_first_stop_does_not_run_controller_and_requests_same_turn_repair(self) -> None:
        root = Path("C:/ds-lite-test")
        with (
            mock.patch.object(ds_lite_hook, "_workspace_root", return_value=root),
            mock.patch.object(ds_lite_hook, "_autonomy_is_active", return_value=True),
            mock.patch.object(ds_lite_hook, "_resume_autonomy_controller", return_value=(False, "autonomy/controller-incomplete")) as resume,
            mock.patch.object(ds_lite_hook, "_stop_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_stop_quality_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_user_action_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_audit_stop_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_autonomy_stop_gaps", return_value=["autonomy controller summary is missing"]),
        ):
            result = ds_lite_hook.handle_event("stop", {})
        resume.assert_not_called()
        self.assertEqual(result["decision"], "block")
        self.assertTrue(result["continue_once"])
        self.assertEqual(result["next_automatic_action"], "resume-autonomy-controller")
        self.assertEqual(result["control_action"], "hook-in-turn-repair")
        self.assertTrue(result["prompt"].strip())

    def test_terminal_controller_failure_is_not_executed_by_hook(self) -> None:
        root = Path("C:/ds-lite-test")
        with (
            mock.patch.object(ds_lite_hook, "_workspace_root", return_value=root),
            mock.patch.object(ds_lite_hook, "_autonomy_is_active", return_value=True),
            mock.patch.object(
                ds_lite_hook,
                "_resume_autonomy_controller",
                return_value=(False, "autonomy/controller-terminal"),
            ),
            mock.patch.object(ds_lite_hook, "_stop_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_stop_quality_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_user_action_gaps", return_value=[]),
            mock.patch.object(ds_lite_hook, "_audit_stop_gaps", return_value=[]),
            mock.patch.object(
                ds_lite_hook,
                "_autonomy_stop_gaps",
                return_value=["autonomy controller is not terminal: blocked"],
            ),
        ):
            result = ds_lite_hook.handle_event("stop", {})
        self.assertEqual(result["decision"], "block")
        self.assertTrue(result["continue_once"])
        self.assertEqual(result["control_action"], "hook-in-turn-repair")
        self.assertEqual(result["failure_layer"], "controller-incomplete")


class CommunicationHookTests(unittest.TestCase):
    def test_host_output_uses_the_strict_codex_user_prompt_envelope(self) -> None:
        payload = ds_lite_hook._host_output("user-prompt-submit", {
            "decision": "allow", "additional_context": "continue the controller",
        })
        self.assertEqual(payload, {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "continue the controller",
            }
        })

    def test_host_output_uses_block_reason_without_internal_fields(self) -> None:
        payload = ds_lite_hook._host_output("stop", {
            "decision": "block", "prompt": "resume the controller", "continue": True,
        })
        self.assertEqual(payload, {"decision": "block", "reason": "resume the controller"})

    def setUp(self) -> None:
        self.root = TEST_TEMP_ROOT / f"ds-lite-hook 中文 project {uuid.uuid4().hex[:12]}"
        self.root.mkdir(parents=True, exist_ok=False)
        (self.root / "PROJECT.md").write_text("# test\n", encoding="utf-8")
        (self.root / "research" / "state").mkdir(parents=True)
        (self.root / "research" / "work-unit.json").write_text(
            json.dumps(
                {
                    "schema_version": "ds-lite.work-unit.v1",
                    "work_unit_id": "hook-test",
                    "title": "Hook test",
                    "goal": "Validate hook behavior",
                    "execution_mode": "none",
                    "profile_id": "core-planning",
                    "state": "active",
                    "prerequisites": [],
                    "required_capabilities": ["read"],
                    "evidence_requirements": [],
                    "evidence_refs": [],
                    "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
                    "subjects": [{"kind": "artifact", "id": "project", "query_ref": "PROJECT.md"}],
                    "active_iteration_ref": "",
                    "extensions": {},
                }
            ) + "\n",
            encoding="utf-8",
        )
        (self.root / "research" / "state" / "graph.json").write_text("{}\n", encoding="utf-8")

    def run_hook(self, event: str, payload: dict[str, object]) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT), event],
            cwd=REPO_ROOT,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        # The CLI intentionally emits Codex's strict host envelope. Unit tests
        # below exercise the richer internal decision object directly; the
        # envelope itself is covered by the tests above and app-server tests.
        return result, ds_lite_hook.handle_event(event, payload)

    def run_audit(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def init_audit(self) -> Path:
        result = self.run_audit(
            "init", "--root", str(self.root), "--skill", "ds-lite-intake",
            "--task-class", "repository-change", "--id", "hook-test",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        return self.root / payload["audit_path"]

    def test_no_ds_lite_project_is_allowed(self) -> None:
        result, payload = self.run_hook("pre-tool-use", {"cwd": str(self.root.parent), "tool_name": "Write"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["decision"], "allow")
        self.assertFalse(payload["workspace_detected"])

    def test_prompt_injects_profile_detail_and_audit_checklist_without_creating_state(self) -> None:
        result, payload = self.run_hook("user-prompt-submit", {"cwd": str(self.root), "task_class": "repository-change"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["decision"], "allow")
        self.assertIn("audit_required", payload)
        self.assertTrue(payload["audit_required"])
        self.assertIn("profile: research-peer", payload["additional_context"])
        self.assertIn("detail: adaptive", payload["additional_context"])
        self.assertIn("honor-01", payload["additional_context"])

    def test_pretool_blocks_state_write_without_audit_and_allows_after_init(self) -> None:
        _, blocked = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"path": "notes.md"}})
        self.assertEqual(blocked["decision"], "block")
        self.assertEqual(blocked["failure_category"], "audit/missing")
        self.assertEqual(blocked["control_action"], "blocked")
        self.assertEqual(blocked["failure_layer"], "audit/missing")
        self.init_audit()
        _, allowed = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"path": "notes.md"}})
        self.assertEqual(allowed["decision"], "allow")

    def test_posttool_records_observed_success_or_failure_without_command_text(self) -> None:
        audit_path = self.init_audit()
        _, payload = self.run_hook("post-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "command": "pytest secret-token=do-not-store", "exit_code": 1})
        self.assertEqual(payload["decision"], "allow")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        events = audit["extensions"]["post_tool_events"]
        self.assertEqual(events[-1]["exit_code"], 1)
        self.assertNotIn("secret-token", json.dumps(audit))

    def test_pretool_blocks_explicit_privilege_escalation(self) -> None:
        self.init_audit()
        _, blocked = self.run_hook(
            "pre-tool-use",
            {"cwd": str(self.root), "tool_name": "Bash", "command": "sudo python run.py"},
        )
        self.assertEqual(blocked["decision"], "block")
        self.assertEqual(blocked["failure_category"], "safety/privilege-escalation")
        self.assertEqual(blocked["control_action"], "blocked")

    def test_finalized_audit_is_closed_for_new_writes(self) -> None:
        audit_path = self.init_audit()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in audit["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in audit["self_check"].values():
            phase.update({"status": "recorded", "items": ["observed"]})
        audit["handoff"].update({"status": "recorded", "summary": "done", "next_step": "new task"})
        audit["result"].update({"status": "completed", "summary": "done"})
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        _, blocked = self.run_hook("pre-tool-use", {"cwd": str(self.root), "tool_name": "Write", "tool_input": {"path": "next.md"}})
        self.assertEqual(blocked["decision"], "block")
        self.assertEqual(blocked["failure_category"], "audit/closed")
        _, prompt = self.run_hook("user-prompt-submit", {"cwd": str(self.root)})
        self.assertTrue(prompt["audit_required"])

    def test_stop_blocks_completed_result_without_supported_completion_claim(self) -> None:
        audit_path = self.init_audit()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in audit["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in audit["self_check"].values():
            phase.update({"status": "recorded", "items": ["observed"]})
        audit["handoff"].update({"status": "recorded", "summary": "done", "next_step": "review"})
        audit["result"].update({"status": "completed", "summary": "done"})
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        _, result = self.run_hook("stop", {"cwd": str(self.root)})
        self.assertEqual(result["decision"], "block")
        self.assertIn("claim/unsupported-completion", result["additional_context"])

    def test_stop_never_turns_failed_audit_into_success(self) -> None:
        audit_path = self.init_audit()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["result"].update({"status": "failed", "summary": "test failure"})
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        _, first = self.run_hook("stop", {"cwd": str(self.root), "stop_hook_active": False})
        self.assertEqual(first["decision"], "block")
        self.assertTrue(first["continue_once"])
        self.assertTrue(first["continue"])
        _, second = self.run_hook("stop", {"cwd": str(self.root), "stop_hook_active": True})
        self.assertEqual(second["decision"], "allow")
        self.assertFalse(second["continue_once"])
        self.assertFalse(second["continue"])
        self.assertTrue(second["hook_handoff"])

    def test_stop_blocks_when_an_autonomy_contract_has_not_reached_a_terminal_summary(self) -> None:
        self.init_audit()
        autonomy = self.root / "research" / "autonomy"
        autonomy.mkdir(parents=True)
        (autonomy / "contract.json").write_text(
            json.dumps({"schema_version": "ds-lite.autonomy-contract.v1", "autonomy_id": "release-081"}),
            encoding="utf-8",
        )
        _, result = self.run_hook("stop", {"cwd": str(self.root)})
        self.assertEqual(result["decision"], "block")
        self.assertIn("autonomy controller summary is missing", result["additional_context"])
        self.assertIn("run_autonomy", result["additional_context"])
        self.assertEqual(result["next_automatic_action"], "resume-autonomy-controller")
        self.assertIn("run_autonomy", result["prompt"])

    def test_stop_first_protocol_defers_controller_until_stop(self) -> None:
        self.init_audit()
        autonomy = self.root / "research" / "autonomy"
        autonomy.mkdir(parents=True)
        (autonomy / "contract.json").write_text(
            json.dumps({"schema_version": "ds-lite.autonomy-contract.v1", "autonomy_id": "release-081"}),
            encoding="utf-8",
        )
        (autonomy / "stop-first.json").write_text(
            json.dumps({"schema_version": "ds-lite.stop-first-protocol.v1", "status": "prepared"}),
            encoding="utf-8",
        )
        _, prompt = self.run_hook("user-prompt-submit", {"cwd": str(self.root)})
        self.assertEqual(prompt["next_automatic_action"], "resume-autonomy-controller")
        _, stop = self.run_hook("stop", {"cwd": str(self.root), "stop_hook_active": True})
        self.assertEqual(stop["decision"], "allow")

    def test_prompt_projects_active_autonomy_progress_without_raw_command(self) -> None:
        autonomy = self.root / "research" / "autonomy" / "run"
        autonomy.mkdir(parents=True)
        (self.root / "research" / "autonomy" / "contract.json").write_text(
            json.dumps({"schema_version": "ds-lite.autonomy-contract.v1", "autonomy_id": "release-081"}),
            encoding="utf-8",
        )
        (autonomy / "progress-001.json").write_text(
            json.dumps({"active_gate": "matched-effect", "status": "partial", "next_action": "run-next-ready-gate"}),
            encoding="utf-8",
        )
        _, result = self.run_hook("user-prompt-submit", {"cwd": str(self.root)})
        self.assertIn("Autonomy controller", result["additional_context"])
        self.assertIn("matched-effect", result["additional_context"])
        self.assertIn("run_autonomy", result["additional_context"])
        self.assertEqual(result["next_automatic_action"], "resume-autonomy-controller")

    def test_post_tool_projects_active_autonomy_resume_action(self) -> None:
        self.init_audit()
        autonomy = self.root / "research" / "autonomy" / "run"
        autonomy.mkdir(parents=True)
        (self.root / "research" / "autonomy" / "contract.json").write_text(
            json.dumps({"schema_version": "ds-lite.autonomy-contract.v1", "autonomy_id": "release-081"}),
            encoding="utf-8",
        )
        (autonomy / "progress-001.json").write_text(
            json.dumps({"active_gate": "web", "status": "blocked", "next_action": "run-independent-ready-gate"}),
            encoding="utf-8",
        )
        _, result = self.run_hook("post-tool-use", {"cwd": str(self.root), "tool_name": "Bash", "exit_code": 0})
        self.assertEqual(result["decision"], "allow")
        self.assertIn("Autonomy controller", result["additional_context"])
        self.assertIn("run_autonomy", result["additional_context"])
        self.assertEqual(result["next_automatic_action"], "resume-autonomy-controller")

    def test_stop_allows_a_completed_autonomy_summary(self) -> None:
        self.init_audit()
        autonomy = self.root / "research" / "autonomy" / "run"
        autonomy.mkdir(parents=True)
        (self.root / "research" / "autonomy" / "contract.json").write_text(
            json.dumps({"schema_version": "ds-lite.autonomy-contract.v1", "autonomy_id": "release-081"}),
            encoding="utf-8",
        )
        (autonomy / "progress-001.json").write_text(
            json.dumps({"active_gate": "web", "status": "passed", "next_action": "final-report"}),
            encoding="utf-8",
        )
        (autonomy / "summary.json").write_text(
            json.dumps({"schema_version": "ds-lite.autonomy-summary.v1", "status": "completed"}),
            encoding="utf-8",
        )
        _, result = self.run_hook("stop", {"cwd": str(self.root)})
        self.assertEqual(result["decision"], "allow")

    def test_stop_blocks_iteration_missing_reflection_and_user_report(self) -> None:
        audit_path = self.init_audit()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        for item in audit["checks"]:
            item.update({"status": "pass", "reason": "observed"})
        for phase in audit["self_check"].values():
            phase.update({"status": "recorded", "items": ["observed"]})
        audit["handoff"].update({"status": "recorded", "summary": "done", "next_step": "review"})
        audit["result"].update({"status": "completed", "summary": "done"})
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        work_unit = {
            "schema_version": "ds-lite.work-unit.v1", "work_unit_id": "work-test", "title": "Test",
            "goal": "Test reflection", "execution_mode": "none", "profile_id": "core-planning", "state": "active",
            "prerequisites": [], "required_capabilities": ["read"], "evidence_requirements": [], "evidence_refs": [],
            "resource_limits": [{"dimension": "actions", "unit": "count", "value": 1}],
            "subjects": [{"kind": "artifact", "id": "project", "query_ref": "PROJECT.md"}],
            "active_iteration_ref": "research/artifacts/iteration-gap.json", "extensions": {},
        }
        (self.root / "research" / "work-unit.json").write_text(json.dumps(work_unit, indent=2) + "\n", encoding="utf-8")
        (self.root / "research" / "artifacts").mkdir(exist_ok=True)
        (self.root / "research" / "artifacts" / "iteration-gap.json").write_text(
            json.dumps({"status": "partial", "reflection": {}, "user_report": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
        _, result = self.run_hook("stop", {"cwd": str(self.root)})
        self.assertEqual(result["decision"], "block")
        self.assertIn("iteration reflection is missing", result["additional_context"])
        self.assertIn("user report is missing", result["additional_context"])
        self.assertIn("Finalize", result["prompt"])

    def test_installer_only_reports_unsupported_host_and_does_not_write_config(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT), "install", "--root", str(self.root), "--show"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["host_supported"])
        self.assertFalse((self.root / ".codex" / "config.toml").exists())
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT), "install", "--root", str(self.root), "--apply"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.root / ".codex" / "config.toml").exists())

    def test_installer_never_overwrites_existing_config_bytes(self) -> None:
        config = self.root / ".codex" / "config.toml"
        config.parent.mkdir()
        original = b"[hooks]\nlegacy = true\n"
        config.write_bytes(original)
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT), "install", "--root", str(self.root), "--apply"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
