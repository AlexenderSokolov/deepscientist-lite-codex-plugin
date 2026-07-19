from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_hook.py"
AUDIT_SCRIPT = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_communication_audit.py"


class CommunicationHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ds-lite-hook 中文 project "))
        (self.root / "PROJECT.md").write_text("# test\n", encoding="utf-8")
        (self.root / "research" / "state").mkdir(parents=True)
        (self.root / "research" / "work-unit.json").write_text("{}\n", encoding="utf-8")
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
        return result, json.loads(result.stdout)

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
        self.init_audit()
        _, first = self.run_hook("stop", {"cwd": str(self.root), "stop_hook_active": False})
        self.assertEqual(first["decision"], "block")
        self.assertTrue(first["continue_once"])
        _, second = self.run_hook("stop", {"cwd": str(self.root), "stop_hook_active": True})
        self.assertEqual(second["decision"], "block")
        self.assertFalse(second["continue_once"])
        self.assertTrue(second["blocked"])

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
