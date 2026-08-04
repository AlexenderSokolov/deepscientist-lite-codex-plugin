#!/usr/bin/env python3
"""Hook trigger tests for DS Lite v6.

Tests UserPromptSubmit, PreToolUse, PostToolUse, Stop events,
PLUGIN_ROOT expansion, and cross-platform Python resolution.
"""

import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HOOKS_PATH = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "hooks" / "hooks.json"


def _load_hooks():
    return json.loads(HOOKS_PATH.read_text(encoding="utf-8"))


class HookEventsTests(unittest.TestCase):
    """Verify all required hook events are present."""

    def test_all_required_events_present(self):
        """hooks.json should have UserPromptSubmit, PreToolUse, PostToolUse, Stop."""
        hooks = _load_hooks()
        required = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}
        actual = set(hooks.get("hooks", {}).keys())
        self.assertEqual(required, actual, f"Missing events: {required - actual}")

    def test_userpromptsubmit_has_hooks(self):
        """UserPromptSubmit should have at least one hook config."""
        hooks = _load_hooks()
        ups = hooks.get("hooks", {}).get("UserPromptSubmit", [])
        self.assertGreater(len(ups), 0, "UserPromptSubmit has no hook configs")

    def test_pretooluse_has_matcher(self):
        """PreToolUse should have a matcher for Write Edit Bash shell_command apply_patch."""
        hooks = _load_hooks()
        ptu = hooks.get("hooks", {}).get("PreToolUse", [])
        self.assertGreater(len(ptu), 0, "PreToolUse has no hook configs")
        matcher = ptu[0].get("matcher", "")
        for tool in ["Write", "Edit", "Bash", "shell_command", "apply_patch"]:
            self.assertIn(tool, matcher, f"Matcher missing {tool}: {matcher}")

    def test_posttooluse_has_matcher(self):
        """PostToolUse should have a matcher for Write Edit Bash shell_command apply_patch."""
        hooks = _load_hooks()
        ptu = hooks.get("hooks", {}).get("PostToolUse", [])
        self.assertGreater(len(ptu), 0, "PostToolUse has no hook configs")
        matcher = ptu[0].get("matcher", "")
        for tool in ["Write", "Edit", "Bash", "shell_command", "apply_patch"]:
            self.assertIn(tool, matcher, f"Matcher missing {tool}: {matcher}")

    def test_stop_has_hooks(self):
        """Stop should have at least one hook config."""
        hooks = _load_hooks()
        stop = hooks.get("hooks", {}).get("Stop", [])
        self.assertGreater(len(stop), 0, "Stop has no hook configs")


class PluginRootExpansionTests(unittest.TestCase):
    """Verify PLUGIN_ROOT is used in all hook commands."""

    def test_all_hook_commands_use_plugin_root(self):
        """Every hook command should reference PLUGIN_ROOT."""
        hooks = _load_hooks()
        for event, configs in hooks.get("hooks", {}).items():
            for config in configs:
                for hook in config.get("hooks", []):
                    cmd = hook.get("command", "")
                    self.assertIn("${PLUGIN_ROOT}", cmd,
                                 f"Hook command for {event} does not use PLUGIN_ROOT: {cmd}")

    def test_hook_entry_path_resolves(self):
        """The hook entry path should resolve to an existing file."""
        hooks = _load_hooks()
        ups = hooks.get("hooks", {}).get("UserPromptSubmit", [])
        cmd = ups[0]["hooks"][0]["command"]
        self.assertIn("${PLUGIN_ROOT}", cmd)
        entry_path = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook_entry.py"
        self.assertTrue(entry_path.exists(), f"Hook entry script not found: {entry_path}")


class PythonInterpreterResolutionTests(unittest.TestCase):
    """Test cross-platform Python interpreter resolution."""

    def setUp(self):
        self.entry_path = REPO_ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook_entry.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("ds_lite_hook_entry", self.entry_path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_resolve_python_with_ds_lite_python_env(self):
        """DS_LITE_PYTHON env var should be used when set."""
        old = os.environ.get("DS_LITE_PYTHON")
        os.environ["DS_LITE_PYTHON"] = "/usr/bin/python3"
        try:
            result = self.module.resolve_python()
            self.assertEqual(result, "/usr/bin/python3")
        finally:
            if old is not None:
                os.environ["DS_LITE_PYTHON"] = old
            else:
                os.environ.pop("DS_LITE_PYTHON", None)

    def test_resolve_python_with_python_bin_env(self):
        """PYTHON_BIN env var should be used when DS_LITE_PYTHON is not set."""
        old_ds = os.environ.pop("DS_LITE_PYTHON", None)
        old_pb = os.environ.get("PYTHON_BIN")
        os.environ["PYTHON_BIN"] = "/usr/local/bin/python3"
        try:
            result = self.module.resolve_python()
            self.assertEqual(result, "/usr/local/bin/python3")
        finally:
            if old_ds is not None:
                os.environ["DS_LITE_PYTHON"] = old_ds
            if old_pb is not None:
                os.environ["PYTHON_BIN"] = old_pb
            else:
                os.environ.pop("PYTHON_BIN", None)

    def test_resolve_python_fallback_to_sys_executable(self):
        """Without env vars, should fall back to sys.executable."""
        old_ds = os.environ.pop("DS_LITE_PYTHON", None)
        old_pb = os.environ.pop("PYTHON_BIN", None)
        try:
            result = self.module.resolve_python()
            self.assertEqual(result, sys.executable)
        finally:
            if old_ds is not None:
                os.environ["DS_LITE_PYTHON"] = old_ds
            if old_pb is not None:
                os.environ["PYTHON_BIN"] = old_pb

    def test_hook_entry_script_exists(self):
        """The hook entry script should exist."""
        self.assertTrue(self.entry_path.exists())


class HookCommandStructureTests(unittest.TestCase):
    """Verify the structure of hook commands."""

    def test_commands_use_python_not_hardcoded_path(self):
        """Hook commands should use python not a hardcoded Python path."""
        hooks = _load_hooks()
        for event, configs in hooks.get("hooks", {}).items():
            for config in configs:
                for hook in config.get("hooks", []):
                    cmd = hook.get("command", "")
                    self.assertTrue(
                        cmd.startswith("python "),
                        f"Hook command for {event} should start with python: {cmd}"
                    )

    def test_userpromptsubmit_command_has_event_arg(self):
        """UserPromptSubmit command should include the event name."""
        hooks = _load_hooks()
        ups = hooks.get("hooks", {}).get("UserPromptSubmit", [])
        cmd = ups[0]["hooks"][0]["command"]
        self.assertIn("user-prompt-submit", cmd)


if __name__ == "__main__":
    unittest.main()
