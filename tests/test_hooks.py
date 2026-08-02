from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "deepscientist-lite"
HOOK_SCRIPT = PLUGIN_ROOT / "scripts" / "ds_lite_hook.py"
HOOK_CONFIG = PLUGIN_ROOT / "hooks" / "hooks.json"
STATE_SCRIPT = PLUGIN_ROOT / "scripts" / "ds_lite_state.py"
SCRIPT_DIR = HOOK_SCRIPT.parent

# The split Core and frozen monolith both expose top-level script module names.
# Load this legacy fixture with isolated module identities so unittest discovery
# order cannot silently substitute the Core Hook implementation.
_module_names = ("ds_lite_hook", "ds_lite_iteration", "ds_lite_protocol", "ds_lite_state", "ds_lite_evidence")
_saved_modules = {name: sys.modules.pop(name) for name in _module_names if name in sys.modules}
try:
    sys.path.insert(0, str(SCRIPT_DIR))
    _spec = importlib.util.spec_from_file_location("ds_lite_legacy_hook", HOOK_SCRIPT)
    assert _spec is not None and _spec.loader is not None
    ds_lite_hook = importlib.util.module_from_spec(_spec)
    sys.modules["ds_lite_legacy_hook"] = ds_lite_hook
    _spec.loader.exec_module(ds_lite_hook)
    _iteration_spec = importlib.util.spec_from_file_location("ds_lite_legacy_iteration", SCRIPT_DIR / "ds_lite_iteration.py")
    assert _iteration_spec is not None and _iteration_spec.loader is not None
    ds_lite_iteration = importlib.util.module_from_spec(_iteration_spec)
    sys.modules["ds_lite_legacy_iteration"] = ds_lite_iteration
    _iteration_spec.loader.exec_module(ds_lite_iteration)
finally:
    sys.modules.pop("ds_lite_legacy_hook", None)
    sys.modules.pop("ds_lite_legacy_iteration", None)
    for _name, _module in _saved_modules.items():
        sys.modules[_name] = _module


class HookEntrypointTests(unittest.TestCase):
    def test_hook_helper_and_four_event_config_use_explicit_plugin_root_registration(self) -> None:
        self.assertTrue(HOOK_SCRIPT.is_file(), "missing lightweight hook helper")
        self.assertTrue(HOOK_CONFIG.is_file(), "missing plugin-local hooks.json")

        config = json.loads(HOOK_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(
            set(config.get("hooks", {})),
            {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"},
        )
        commands = [
            hook["command"]
            for registrations in config["hooks"].values()
            for registration in registrations
            for hook in registration["hooks"]
        ]
        self.assertEqual(len(commands), 4)
        self.assertTrue(all("ds_lite_hook.py" in command for command in commands))
        self.assertTrue(all("${PLUGIN_ROOT}" in command for command in commands))
        self.assertTrue(all("./scripts/ds_lite_hook.py" not in command for command in commands))

        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], "0.6.0-beta.1")
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")


class HookBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="ds-lite-hook-test-"))
        completed = subprocess.run(
            [
                sys.executable,
                str(STATE_SCRIPT),
                "init",
                "--root",
                str(cls.root),
                "--title",
                "Hook behavior",
                "--question",
                "Can a hook protect one bounded iteration?",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stdout + completed.stderr)

    def test_non_ds_lite_workspace_is_allowed_without_context(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="not-ds-lite-hook-test-"))
        result = ds_lite_hook.handle_event(
            "user-prompt-submit", {"cwd": str(root), "prompt": "ordinary task"}
        )
        self.assertEqual(result["decision"], "allow")
        self.assertFalse(result["workspace_detected"])
        self.assertNotIn("additional_context", result)

    def test_user_prompt_submit_attaches_only_a_redacted_mission_projection(self) -> None:
        secret_prompt = "continue this project; password=never-echo-this"
        result = ds_lite_hook.handle_event(
            "user-prompt-submit", {"cwd": str(self.root), "prompt": secret_prompt}
        )
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["decision"], "allow")
        self.assertTrue(result["workspace_detected"])
        self.assertIn("Mission Board", result["additional_context"])
        self.assertIn("evidence_strength", result["additional_context"])
        self.assertIn("suggested_skill", result["additional_context"])
        self.assertNotIn(secret_prompt, rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("never-echo-this", rendered)

    def test_pre_tool_use_blocks_direct_graph_edits_without_echoing_tool_input(self) -> None:
        result = ds_lite_hook.handle_event(
            "pre-tool-use",
            {
                "cwd": str(self.root),
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(self.root / "research" / "state" / "graph.json"),
                    "new_string": "api_key=never-echo-this",
                },
            },
        )
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["failure_category"], "state/direct-authority-write")
        self.assertNotIn("never-echo-this", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_pre_tool_use_blocks_destructive_and_tmux_capacity_commands(self) -> None:
        cases = {
            "git reset --hard HEAD~1": "safety/destructive-command",
            "git clean -fd": "safety/destructive-command",
            "rm -rf research": "safety/recursive-delete",
            "Remove-Item -Recurse research": "safety/recursive-delete",
            "tmux -S /tmp/ds.sock new-session -d -s ds": "runtime/tmux-capacity",
            "tmux split-window -h": "runtime/tmux-capacity",
        }
        for command, category in cases.items():
            with self.subTest(command=command):
                result = ds_lite_hook.handle_event(
                    "pre-tool-use",
                    {
                        "cwd": str(self.root),
                        "tool_name": "shell_command",
                        "tool_input": {"command": command},
                    },
                )
                self.assertEqual(result["decision"], "block")
                self.assertEqual(result["failure_category"], category)

    def test_pre_tool_use_allows_read_only_and_revision_aware_state_commands(self) -> None:
        commands = (
            "Get-Content research/state/graph.json",
            "python ./scripts/ds_lite_state.py set-status --root . --node idea-a "
            "--status active --expected-revision 2",
        )
        for command in commands:
            with self.subTest(command=command):
                result = ds_lite_hook.handle_event(
                    "pre-tool-use",
                    {
                        "cwd": str(self.root),
                        "tool_name": "shell_command",
                        "tool_input": {"command": command},
                    },
                )
                self.assertEqual(result["decision"], "allow")

    def test_pre_tool_use_blocks_revision_omission_on_state_mutation(self) -> None:
        result = ds_lite_hook.handle_event(
            "pre-tool-use",
            {
                "cwd": str(self.root),
                "tool_name": "shell_command",
                "tool_input": {
                    "command": "python ./scripts/ds_lite_state.py set-status --root . "
                    "--node idea-a --status active"
                },
            },
        )
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["failure_category"], "state/missing-revision")

    def test_post_tool_use_reports_consistency_without_tool_output(self) -> None:
        result = ds_lite_hook.handle_event(
            "post-tool-use",
            {
                "cwd": str(self.root),
                "tool_name": "shell_command",
                "tool_output": "stderr password=never-echo-this",
            },
        )
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["decision"], "allow")
        self.assertIn("additional_context", result)
        self.assertIn("consistency", result["additional_context"].lower())
        self.assertNotIn("never-echo-this", rendered)

    def test_stop_blocks_running_iteration_once_and_respects_reentry_guard(self) -> None:
        graph = json.loads(
            (self.root / "research" / "state" / "graph.json").read_text(encoding="utf-8")
        )
        ds_lite_iteration.initialize_iteration(
            self.root,
            iteration_id="hook-running-iteration",
            selected_skill="ds-lite-iterate",
            action={
                "kind": "status-check",
                "summary": "Check one bounded state transition.",
                "prediction": "The current state can be verified without mutation.",
                "falsification_condition": "The state cannot be read or is stale.",
                "resource_limits": [
                    {"dimension": "actions", "unit": "count", "value": 1}
                ],
                "stop_condition": "Stop after one status check.",
                "extensions": {},
            },
            input_refs=["PROJECT.md", "research/work-unit.json"],
            expected_revision=graph["revision"],
        )

        first = ds_lite_hook.handle_event("stop", {"cwd": str(self.root)})
        self.assertEqual(first["decision"], "block")
        self.assertTrue(first["continue_once"])
        self.assertIn("running iteration", first["additional_context"])

        guarded = ds_lite_hook.handle_event(
            "stop", {"cwd": str(self.root), "stop_hook_active": True}
        )
        self.assertEqual(guarded["decision"], "allow")
        self.assertFalse(guarded["continue_once"])

    def test_stop_blocks_terminal_iteration_with_missing_reflection_and_report(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-hook-terminal-gap-test-"))
        completed = subprocess.run(
            [
                sys.executable,
                str(STATE_SCRIPT),
                "init",
                "--root",
                str(root),
                "--title",
                "Terminal gap",
                "--question",
                "Will Stop detect an incomplete handoff?",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        graph = json.loads(
            (root / "research" / "state" / "graph.json").read_text(encoding="utf-8")
        )
        iteration = ds_lite_iteration.initialize_iteration(
            root,
            iteration_id="hook-terminal-gap",
            selected_skill="ds-lite-iterate",
            action={
                "kind": "stop",
                "summary": "Stop after one bounded check.",
                "prediction": "The receipt will expose missing handoff fields.",
                "falsification_condition": "The receipt is already complete.",
                "resource_limits": [
                    {"dimension": "actions", "unit": "count", "value": 1}
                ],
                "stop_condition": "Stop after checking the receipt.",
                "extensions": {},
            },
            input_refs=["PROJECT.md"],
            expected_revision=graph["revision"],
        )
        iteration["status"] = "partial"
        iteration["after_revision"] = graph["revision"]
        iteration["stop_reason"] = "incomplete-handoff"
        iteration["completed_at"] = "2026-07-17T12:00:00Z"
        ref = iteration["extensions"]["iteration_ref"]
        (root / ref).write_text(
            json.dumps(iteration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        result = ds_lite_hook.handle_event("stop", {"cwd": str(root)})
        self.assertEqual(result["decision"], "block")
        self.assertIn("reflection is missing", result["additional_context"])
        self.assertIn("user report is missing", result["additional_context"])

    def test_windows_and_bash_style_workspace_paths_are_detected(self) -> None:
        path_forms = (str(self.root), self.root.as_posix())
        for root in path_forms:
            with self.subTest(root=root):
                result = ds_lite_hook.handle_event("post-tool-use", {"cwd": root})
                self.assertTrue(result["workspace_detected"])

    def test_cli_accepts_json_stdin_and_emits_only_reduced_output(self) -> None:
        secret = "prompt token=never-echo-this"
        completed = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT), "user-prompt-submit"],
            cwd=PLUGIN_ROOT,
            input=json.dumps({"cwd": str(self.root), "prompt": secret}),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["workspace_detected"])
        self.assertNotIn(secret, completed.stdout)
        self.assertNotIn(str(self.root), completed.stdout)

    def test_cli_opt_in_host_receipt_contains_only_event_and_decision(self) -> None:
        receipt_dir = Path(tempfile.mkdtemp(prefix="ds-lite-hook-receipt-parent-")) / "events"
        secret = "prompt token=never-write-this"
        env = os.environ.copy()
        env["DS_LITE_HOOK_ACCEPTANCE_DIR"] = str(receipt_dir)
        completed = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT), "user-prompt-submit"],
            cwd=PLUGIN_ROOT,
            input=json.dumps({"cwd": str(self.root), "prompt": secret}),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipts = list(receipt_dir.glob("*.json"))
        self.assertEqual(len(receipts), 1)
        payload = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload),
            {"schema_version", "event_type", "decision"},
        )
        self.assertEqual(payload["schema_version"], "ds-lite.hook-host-event.v1")
        self.assertEqual(payload["event_type"], "user-prompt-submit")
        self.assertEqual(payload["decision"], "allow")
        rendered = receipts[0].read_text(encoding="utf-8")
        self.assertNotIn(secret, rendered)
        self.assertNotIn(str(self.root), rendered)


if __name__ == "__main__":
    unittest.main()
